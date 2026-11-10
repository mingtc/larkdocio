"""LD-568 — the two tables a consumer reads BEFORE authoring anything into a docx.

Four silences, one guard file:

1. **AC1/AC2** — the `todo` row of the dialect table said nothing while `mermaid` in the same
   table carried a loud CREATE-ONLY banner, so three shipped doors read as *"a checkbox is
   editable"* and the reconciler compiled a no-op and reported APPLIED. The fix is **not** a
   second hand-typed absence: the whole docx-write absence register is projected into the guide
   as a **generated, byte-identical region** (the CONFIG-SCHEMA precedent), and the `todo` row
   carries a **pointer** to it plus the verdict — *an open defect, not a designed limit* — and
   nothing else. A pointer is not a second statement; a mechanism sentence would be.
2. **AC3** — `BLOCKS.md`'s type-17 **notes cell** says the same thing. Its Projection cell is
   DERIVED and correct (a todo block's *text* is editable; only the `done` bit is not), so the
   fact can only live in the free text.
3. **AC4** — *a table cell cannot carry an anchor* stops being findable only under the
   file-upload recipe. It is authored ONCE, as a ``not_creatable`` entry with its own head
   term, which the head-term guard then forces into the guide's capability-matrix cell.
4. **AC5** — the real remaining gap in the lossiness table: the word **colour**, and what
   happens to emphasis on a read / round trip. Both in existing rows' cell text or in prose;
   `colour` is NOT in ``NOT_EXPRESSIBLE_CONSTRUCTS`` and a phantom row would redden
   ``tests/test_authoring_discovery.py``.
"""
import pathlib
import re

import pytest

from larkdocio import capabilities, guide
from larkdocio.write.absences import (
    ABSENCE_REGENERATE,
    ABSENCE_REGION_BEGIN,
    ABSENCE_REGION_END,
    DOCX_WRITE_ABSENCES,
    docx_write_absences_markdown,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BLOCKS_MD = REPO_ROOT / "BLOCKS.md"

#: The verdict AC1 mandated for the OPEN DEFECT this file was written about — *"an open
#: defect, not a designed limit"*, in pure consumer language.
#:
#: **SUPERSEDED by LD-574, reason preserved.** LD-568's reason for demanding this exact phrase
#: was that a silent no-op must never read as a designed boundary, and that reason stands in
#: full: it is why the successor row records a typed REFUSAL rather than a banner. Only the
#: conclusion moved — the defect is fixed (the checkbox now moves), so a shipped surface
#: calling it an open defect would itself be the stale claim. The constant is kept, unused as
#: an assertion, so a reader of this file meets the argument rather than a deleted line.
OPEN_DEFECT_VERDICT = "an open defect, not a designed limit"

#: The register row this file was written about, and the row that took its slot when the bit
#: shipped (LD-574 — the whole reason is preserved inside the successor's ``evidence``).
RETIRED_TODO_ROW_ID = "todo-done-bit-is-not-editable"
TODO_ROW_ID = "no-block-property-edit-beyond-text"

#: AC4's head term. ``tests/test_guide.py``'s ``_floor_key`` splits a floor entry on the first
#: ``" — "`` or ``"("``, so this is the part the guide's cell must repeat.
#:
#: **SUPERSEDED IN PART by LD-619, reason preserved.** AC4's reason for authoring this fact
#: once, under its own head term, was that a limit findable only under a file-upload recipe is
#: a limit a consumer planning a table never meets — and that reason stands in full: it is why
#: the successor entry below is a **narrowing** under its own head term rather than a deleted
#: row. Only the conclusion moved, and it moved because the platform was **measured**: Lark
#: accepts and stores a link-carrying run inside a docx table cell on both of the routes this
#: library creates cells by (LD-517), so *"an anchored link inside a table cell"* is now
#: **creatable** and a floor entry still saying otherwise would be the stale claim.
RETIRED_ANCHOR_CELL_HEAD = "an anchored link inside a table cell"

#: The narrowed head term: the link came out, every other run styling in a cell stayed in.
ANCHOR_CELL_HEAD = "a styled run other than a link inside a table cell"


def _guide() -> str:
    return guide(full=True)


def region_of(text: str, begin: str, end: str) -> str:
    start = text.find(begin)
    if start == -1:
        return ""
    stop = text.find(end, start)
    return "" if stop == -1 else text[start: stop + len(end)]


def _dialect_table_row(kind: str) -> str:
    """One row of the guide's ``Kind | The Markdown you write | Creates`` dialect table."""
    for line in _guide().splitlines():
        if line.startswith(f"| `{kind}` |"):
            return line
    raise AssertionError(f"the guide's dialect table has no `{kind}` row")


def _blocks_md_row(block_type: int) -> str:
    for line in BLOCKS_MD.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"| {block_type} |"):
            return line
    raise AssertionError(f"BLOCKS.md has no type-{block_type} row")


# --------------------------------------------------------------------------- #
# AC2 — the register is projected, once, as generated bytes.                    #
# --------------------------------------------------------------------------- #

def test_ac2_the_render_carries_every_register_row_verbatim():
    """The projection is the register, not a summary of it: every row's id, statement,
    verification label, evidence and ``instead`` appear in the rendered bytes."""
    rendered = docx_write_absences_markdown()
    for row in DOCX_WRITE_ABSENCES:
        assert f"`{row['id']}`" in rendered, row["id"]
        for field in ("statement", "verification", "evidence", "instead"):
            assert row[field] in rendered, f"{row['id']}: {field} is not projected verbatim"


def test_ac2_the_render_keeps_the_registers_own_order():
    """A consumer's stored index into the list must not move for a non-capability reason —
    the register says so, and the projection is what would break it."""
    rendered = docx_write_absences_markdown()
    positions = [rendered.find(f"**`{r['id']}`**") for r in DOCX_WRITE_ABSENCES]
    assert positions == sorted(positions) and -1 not in positions


def test_ac2_the_region_is_self_describing_and_names_its_own_regeneration_command():
    rendered = docx_write_absences_markdown()
    assert rendered.startswith(ABSENCE_REGION_BEGIN)
    assert rendered.endswith(ABSENCE_REGION_END)
    assert ABSENCE_REGENERATE in rendered


def test_ac2_the_GUIDE_carries_the_generated_region_byte_identically():
    """The CONFIG-SCHEMA precedent, and the only guard shape that actually prevents drift."""
    region = region_of(_guide(), ABSENCE_REGION_BEGIN, ABSENCE_REGION_END)
    assert region, "the shipped guide carries no generated docx-write absence region"
    assert region == docx_write_absences_markdown(), (
        f"the guide's absence region is stale — regenerate with: {ABSENCE_REGENERATE}"
    )


def test_ac2_a_changed_REGISTER_ROW_moves_the_render_so_the_guide_goes_red(monkeypatch):
    """Red-then-green on the coupling itself: the region is held against the register rather
    than typed twice, so a row that moves in code leaves the shipped bytes disagreeing."""
    import larkdocio.write.absences as mod

    before = docx_write_absences_markdown()
    mutated = dict(DOCX_WRITE_ABSENCES[0], statement="a statement nobody authored")
    monkeypatch.setattr(mod, "DOCX_WRITE_ABSENCES", (mutated,) + DOCX_WRITE_ABSENCES[1:])
    after = docx_write_absences_markdown()
    assert before != after and "a statement nobody authored" in after
    assert region_of(_guide(), ABSENCE_REGION_BEGIN, ABSENCE_REGION_END) != after


def test_ac2_the_generated_region_is_BELOW_the_lossiness_table():
    """PLACEMENT: the dialect section's refused-construct lookup takes the FIRST table whose
    headers carry ``construct``. A generated block above the lossiness table hijacks it."""
    text = _guide()
    lossiness = text.find("| Construct | Why it cannot be composed |")
    region = text.find(ABSENCE_REGION_BEGIN)
    assert lossiness != -1 and region != -1
    assert lossiness < region, "the absence region must sit BELOW the lossiness table"


def test_ac2_the_region_does_not_hijack_either_dialect_table_lookup():
    """The two lookups in ``tests/test_authoring_discovery.py`` still find the hand-authored
    tables, not the generated region — proved by calling them."""
    from test_authoring_discovery import _guide_creatable_kinds, _guide_refused_constructs

    from larkdocio.write.compose import NOT_EXPRESSIBLE_CONSTRUCTS

    floor = capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]
    assert set(_guide_creatable_kinds()) == set(floor["creatable_kinds"])
    assert _guide_refused_constructs() == set(NOT_EXPRESSIBLE_CONSTRUCTS)


def test_ac2_there_is_exactly_ONE_authored_statement_of_the_todo_absence_in_the_guide():
    """The hard constraint: outside the generated region, no second copy of the register's
    own mechanism sentence exists in the shipped guide."""
    text = _guide()
    region = region_of(text, ABSENCE_REGION_BEGIN, ABSENCE_REGION_END)
    outside = text.replace(region, "")
    row = next(r for r in DOCX_WRITE_ABSENCES if r["id"] == TODO_ROW_ID)
    for sentence in (row["statement"], row["evidence"], row["instead"]):
        assert sentence not in outside, (
            "the guide carries a second, hand-kept copy of the todo absence's own prose"
        )


# --------------------------------------------------------------------------- #
# AC1 — the `todo` dialect row: no longer a silent kind, and no longer a defect. #
# --------------------------------------------------------------------------- #

def test_ac1_the_todo_row_no_longer_reads_as_a_plain_creatable_kind():
    """LD-568's actual requirement, and it survives LD-574 unchanged: the row may not be
    silent about the checkbox while ``mermaid`` beside it carries a loud banner. What the row
    must SAY moved with the behaviour — it named an open defect while one existed, and it now
    names the route and the boundary — but a bare ``todo (17)`` is still the failure."""
    row = _dialect_table_row("todo")
    assert "todo (17)" in row
    assert TODO_ROW_ID in row, (
        "the todo row must still point at the register row that governs it, in consumer "
        "language, rather than reading as a kind with nothing to know about it")


def test_ac1_the_todo_row_no_longer_calls_a_FIXED_defect_open():
    """LD-568's rule, applied to the state LD-574 left behind. The reason is unchanged — a
    shipped row may not present a silent no-op as a designed boundary — and the row now has
    no no-op to present: the bit moves. So the words that named the defect must go with it,
    or the guide claims a hole where a capability is (the register's own failure mode,
    inverted)."""
    row = _dialect_table_row("todo").lower()
    assert "open defect" not in row
    assert "write-once" not in row
    for forbidden in ("by design", "deliberate", "designed absence", "capability boundary"):
        assert forbidden not in row, f"the todo row presents an absence as {forbidden!r}"


def test_ac1_the_todo_row_says_the_CHECKBOX_IS_EDITABLE_IN_PLACE():
    """The half a consumer must know before reaching for a workaround: the gated route does
    this now, so nobody derives a raw field mask by source-diving again."""
    row = _dialect_table_row("todo").lower()
    assert "editable in place" in row
    assert "- [x]" in row


def test_ac1_the_todo_row_is_a_POINTER_not_a_second_statement_of_the_MECHANISM():
    """AC2's other direction. The row may carry the verdict and an address; the *mechanism*
    (which encoder, which request type, which field) is authored only in the register."""
    row = _dialect_table_row("todo")
    assert TODO_ROW_ID in row, "the todo row must address the register row by its own id"
    assert RETIRED_TODO_ROW_ID not in row, (
        "the retired row's id resolves to nothing in the register — a pointer at a row that "
        "is not there is worse than no pointer")
    for mechanism in ("EditRequest", "replacement", "todo.style.done", "encode"):
        assert mechanism not in row, (
            f"{mechanism!r} in the todo row is a second statement of the register's mechanism"
        )


def test_ac1_the_wording_carries_no_internal_dialect():
    """AC1's binding constraint, checked directly rather than trusted to the corpus guard:
    no role name, no issue id, no finding id, no internal machinery."""
    import consumer_text

    row = _dialect_table_row("todo")
    for name, pattern, _ in consumer_text.DIALECT_PATTERNS:
        assert not pattern.findall(row), f"the todo row carries {name} dialect"


def test_ac1_the_todo_banner_is_as_loud_as_the_mermaid_one_beside_it():
    """The defect was an ASYMMETRY inside one table: `mermaid` shouted, `todo` was silent."""
    assert "**CREATE-ONLY:**" in _dialect_table_row("mermaid")
    assert re.search(r"\*\*[^*]*:\*\*", _dialect_table_row("todo")), (
        "the todo row needs a bolded banner label, like the mermaid row beside it"
    )


# --------------------------------------------------------------------------- #
# AC3 — BLOCKS.md type 17 agrees, in the NOTES cell only.                       #
# --------------------------------------------------------------------------- #

def test_ac3_the_type_17_notes_cell_carries_the_same_verdict_as_the_guide():
    """Still one verdict on both sides — the verdict just changed. LD-568 required the matrix
    and the guide to agree that the bit was an open defect; they now have to agree that it is
    writable, and that the matrix addresses the register row that is actually there."""
    from guard_kit import md_table_cells

    notes = md_table_cells(_blocks_md_row(17))[8]
    assert OPEN_DEFECT_VERDICT not in notes, (
        "BLOCKS.md's type-17 notes cell still calls a fixed defect open")
    assert TODO_ROW_ID in notes, "the notes cell must address the register row"
    assert "open defect" in notes.lower(), (
        "the supersession keeps the reason: the cell says what the old clause was and why, "
        "so a rationale-free strike cannot get the argument re-litigated")


def test_ac3_the_notes_cell_says_which_HALVES_of_a_todo_are_editable():
    """The precision that keeps the DERIVED Projection cell honest: both the text and the
    bit edit now, and every OTHER property refuses. Flipping the Projection cell would redden
    ``tests/test_blocks_md_matrix.py``."""
    from guard_kit import md_table_cells

    notes = md_table_cells(_blocks_md_row(17))[8].lower()
    assert "done" in notes and "text" in notes
    assert "change-not-expressible" in notes


def test_ac3_the_DERIVED_projection_and_write_cells_did_NOT_move():
    from guard_kit import md_table_cells

    cells = md_table_cells(_blocks_md_row(17))
    assert cells[3].replace("*", "").strip() == "creatable"
    assert cells[5].replace("*", "").strip() == "editable"


# --------------------------------------------------------------------------- #
# AC4 — a table cell cannot carry an anchor: one authoring site, projected.      #
# --------------------------------------------------------------------------- #

def _not_creatable() -> list:
    return capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"][
        "not_creatable"]


def _anchor_cell_entry() -> str:
    for entry in _not_creatable():
        if entry.lower().startswith(ANCHOR_CELL_HEAD):
            return entry
    raise AssertionError(
        f"the docx-write not_creatable floor has no {ANCHOR_CELL_HEAD!r} entry")


def test_ac4_the_fact_is_authored_as_a_not_creatable_entry_with_its_OWN_head_term():
    """The only mechanism that satisfies "one authoring site, projected": extending an
    existing entry's tail would not propagate, because the pin is on the HEAD TERM."""
    from test_guide import _floor_key

    entry = _anchor_cell_entry()
    keys = [_floor_key(e) for e in _not_creatable()]
    assert _floor_key(entry) == ANCHOR_CELL_HEAD
    assert len(set(keys)) == len(keys), f"two floor entries share a head term: {keys}"


def test_ac4_the_RETIRED_head_term_is_gone_from_the_floor_because_the_link_now_SHIPS():
    """The other half of the narrowing, and the arm that would catch a silent re-widening:
    the retired head term must not still be claiming a limit this library no longer has."""
    keys = [entry.lower() for entry in _not_creatable()]
    assert not [k for k in keys if k.startswith(RETIRED_ANCHOR_CELL_HEAD)], (
        "the floor still refuses an anchored link inside a table cell, which ships")
    # and the successor carries the retired claim's own words, so the supersession is readable
    assert RETIRED_ANCHOR_CELL_HEAD in _anchor_cell_entry()


def test_ac4_the_entry_is_DERIVED_from_the_real_shapes_it_describes():
    """AC8: no unlabelled claim. The entry names the two types that make it true, and both
    really have the shape it reports.

    **The two shapes are unchanged and so is this arm** — they are the EDIT path, and the
    in-cell anchor is a CREATE-time capability. What the entry may no longer say is that
    creating the table cannot reach an anchor either; the third assertion below is what holds
    it to the new truth.
    """
    from larkdocio.write.model.anchors import Anchor, AnchorById, TableLocator
    from larkdocio.write.model.requests import EditRequest, SubSpanEditRequest

    entry = _anchor_cell_entry()
    assert "EditRequest" in entry and "SubSpanEditRequest" in entry
    # The whole-cell path: a plain string, so it cannot carry a span at all.
    assert EditRequest.__dataclass_fields__["replacement"].type in ("str", str)
    # The span-level path: narrative anchors only — a TableLocator cannot even be passed.
    subspan_anchor = SubSpanEditRequest.__dataclass_fields__["anchor"].type
    assert set(getattr(subspan_anchor, "__args__", ())) == {Anchor, AnchorById}
    assert TableLocator not in getattr(subspan_anchor, "__args__", ())
    assert "table\ncell* is out of scope" in SubSpanEditRequest.__doc__.replace(" ", " ") or (
        "table" in SubSpanEditRequest.__doc__ and "out of scope" in SubSpanEditRequest.__doc__)
    # LD-619 — and the CREATE side is now the other way round: a cell really does take spans.
    from larkdocio.write.model.requests import NewBlock, TextSpan
    assert "IS creatable" in entry
    cell = NewBlock.table([["a", (TextSpan("x", link_url="https://example.com"),)]]).rows[0][1]
    assert cell == (TextSpan("x", link_url="https://example.com"),)


def test_ac4_the_head_term_guard_forced_it_into_the_guides_capability_matrix_cell():
    """The pin at ``tests/test_guide.py`` is what carries the fact into the cell a consumer
    planning a table actually reads. Asserted here from the other side too."""
    from test_guide import _floor_keys

    assert ANCHOR_CELL_HEAD in _floor_keys("not creatable")


def test_ac4_the_fact_is_also_where_a_consumer_planning_a_TABLE_reads_it():
    """The authoring/lossiness table — the second place named by the AC."""
    from test_authoring_discovery import _dialect_section

    section = _dialect_section()
    assert "anchor" in section.lower()
    assert "table cell" in section.lower()


def test_ac4_the_file_link_recipe_KEEPS_the_fact_and_cross_references_the_floor():
    """"Cross-referenced rather than deleted from it" — the recipe's own reader still needs the
    fact, so the shipped statement stays where it was.

    **TRANSFORMED by LD-619, reason preserved.** This used to require the words *"CANNOT CARRY
    THE ANCHOR"*, and the reason was that the consumer who met the refusal on a real document
    reads THIS section — which is exactly why the correction has to land here rather than only
    in the floor. Only the conclusion moved: the section must now say the cell **does** carry
    the anchor, and must keep the superseded claim visible so the consumer who remembers the
    old sentence can see it was answered rather than quietly dropped.
    """
    text = _guide()
    assert "A TABLE CELL CARRIES THE ANCHOR TOO" in text, (
        "the file-link recipe must state the shipped capability where the refusal was met")
    assert "cannot carry the anchor" in text.lower(), (
        "the superseded claim must stay visible as superseded, not be deleted")
    # LD-700 (T3): the observation stays cited, without its date. LD-715 (owner ruling
    # 2026-11-07): and without saying who observed it — the observation is still cited, as an
    # observation on a disposable document, which is the reason this assertion exists.
    assert "observed on a disposable" in text, "the observation that motivated it stays cited"


def test_ac4_the_fact_is_not_PARAPHRASED_a_third_time():
    """One authoring site: the guide's floor cell repeats only the HEAD TERM, and every other
    appearance of the head term is the generated/pinned projection or the original recipe.

    **The head term this counts is the NARROWED one (LD-619)**; the rule is unchanged and so
    is its reason — a fact stated twice is a fact that can disagree with itself.
    """
    text = _guide()
    occurrences = len(re.findall(re.escape(ANCHOR_CELL_HEAD.removeprefix("a ")), text,
                                 flags=re.IGNORECASE))
    assert occurrences == 1, (
        f"the head term appears {occurrences} times in the guide — it is projected once"
    )


# --------------------------------------------------------------------------- #
# AC5 — the real gap: COLOUR, and what a read / round trip does to emphasis.     #
# --------------------------------------------------------------------------- #

def test_ac5_the_lossiness_table_names_COLOUR_without_inventing_a_row():
    """``colour`` is not in ``NOT_EXPRESSIBLE_CONSTRUCTS``, so a row keyed `colour` would be
    a phantom. The word lands in an existing row's cell text or in prose."""
    from test_authoring_discovery import _dialect_section, _guide_refused_constructs

    section = _dialect_section()
    assert re.search(r"\bcolour\b", section), "the dialect section never says 'colour'"
    refused = _guide_refused_constructs()
    assert "colour" not in refused and "color" not in refused


def test_ac5_the_dialect_section_says_what_a_READ_does_to_emphasis():
    """Derived from the renderer: emphasis IS emitted (``**`` / ``_`` / ``~~`` / backticks /
    ``<u>``), which is why a consumer sees it in the Markdown and then cannot re-compose it."""
    from test_authoring_discovery import _dialect_section

    section = _dialect_section()
    for marker in ("`**x**`", "`_x_`", "`~~x~~`", "`<u>x</u>`"):
        assert marker in section, f"the dialect section does not say the reader emits {marker}"


def test_ac5_the_read_claim_is_TRUE_of_the_renderer_it_describes():
    """AC8: the sentence is derived from code, and this is the derivation."""
    from larkdocio.model.nodes import StyledText
    from larkdocio.model.renderer import MarkdownRenderer

    r = MarkdownRenderer()
    assert r._styled(StyledText(content="x", bold=True)) == "**x**"
    assert r._styled(StyledText(content="x", italic=True)) == "_x_"
    assert r._styled(StyledText(content="x", strikethrough=True)) == "~~x~~"
    assert r._styled(StyledText(content="x", underline=True)) == "<u>x</u>"
    assert r._styled(StyledText(content="x", inline_code=True)) == "`x`"


def test_ac5_the_colour_claim_is_TRUE_of_the_renderer_it_describes():
    """Colour is CAPTURED and never EMITTED — which is why it is not a refusal at all."""
    from larkdocio.model.nodes import StyledText
    from larkdocio.model.renderer import MarkdownRenderer

    coloured = StyledText(content="x", text_color=5, background_color=2)
    assert MarkdownRenderer()._styled(coloured) == "x"
    assert coloured.text_color == 5 and coloured.background_color == 2


def test_ac5_the_dialect_section_says_a_coloured_run_reads_back_as_PLAIN_TEXT():
    from test_authoring_discovery import _dialect_section

    section = _dialect_section().lower()
    assert "never emitted" in section or "reads back as plain text" in section


def test_ac5_the_dialect_section_says_what_a_ROUND_TRIP_does():
    from test_authoring_discovery import _dialect_section

    section = _dialect_section().lower()
    assert "round trip" in section or "round-trip" in section
    assert "refuse" in section


@pytest.mark.parametrize("construct", ("bold", "italic", "strikethrough", "inline-code"))
def test_ac5_the_four_shipped_emphasis_rows_are_KEPT_not_replaced(construct):
    """Supersession: the shipped statement's reason stays. AC5 is a narrowing, not a rewrite."""
    assert "A styled run" in _dialect_table_row(construct)
