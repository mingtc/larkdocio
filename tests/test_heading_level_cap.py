"""LD-145 — the Markdown heading marker is CAPPED at ``######``; the tree keeps the level.

Dogfood round 2, finding **T17**: Lark stores heading levels 1–9, and the Markdown
serializer built its marker as ``"#" * level`` with no clamp — so a heading7 came out as
``####### text``. Seven ``#`` is **not a heading in CommonMark** (the ATX marker is 1–6),
so the emission was doubly wrong:

* **invalid** — every conforming parser reads the line as a *paragraph* whose literal text
  begins with seven ``#`` (verified below against the reference parser), so the heading was
  not merely mis-levelled, it stopped being a heading at all;
* **not round-trippable** — feeding that line back to ``compose()`` yielded a
  ``PARAGRAPH``, contradicting the guide's round-trip-symmetry claim (the Markdown-authoring spec § D4).

The model was never wrong (``parse_docx_tree`` reports ``HeadingNode(level=7)``) and Lark's
own UI renders H7–H9 correctly, so this was **read-side serialization only**.

**The fix (maintainer-consented output change):** the marker is clamped to
``renderer.MAX_HEADING_LEVEL`` (6) at the serializer, and ``HeadingNode.level`` is left
alone. H7–H9 therefore read back as **H6** — valid and honest, recorded as documented
lossiness in the dialect table — instead of invalid and lossy.

**The cross-seam doctrine (carried forward from LD-144).** Two serializers now face a
heading whose level exceeds their dialect's ceiling, and they resolve it **differently on
purpose**:

* the **Markdown** path caps to ``######`` — Markdown's *only* heading vocabulary is the
  ``#`` marker, so the choice is between "a heading at the wrong level" and "not a heading
  at all". A heading's structural role (outline entry / TOC / anchor) survives the first
  and is destroyed by the second, so the level is what gives way;
* the **merged-cell HTML** path (LD-144) degrades to ``<p><strong>…</strong></p>`` — there
  the heading sits inside a ``<td>``, where it is **no consumer's outline entry**, so
  there is no structural role left to save and emitting ``<h6>`` would only assert a level
  the tree does not have. With nothing to preserve but visual weight, it refuses to lie
  about the level.

One shared rule underneath: **no serializer ever invents a marker outside its dialect**
(never ``#######``, never ``<h7>``), and the true level lives in the tree either way. Both
halves are asserted together below so a future change to either seam has to face the pair.
"""
from pathlib import Path

import pytest

import builders
from builders import cell, page, table
from compose_roundtrip import reader_markdown
from doc_prose import missing_phrases
from harness import FIXTURES_DIR, build_blocks, render

from larkdocio.model import HeadingNode
from larkdocio.model.renderer import MAX_HEADING_LEVEL
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import NewBlock, NewBlockKind, compose

MarkdownIt = pytest.importorskip("markdown_it").MarkdownIt

#: The reference parser — CommonMark plus the two GFM extensions the renderer emits. The
#: point of a *reference* parser is that the assertion is not this library's own opinion
#: of what its output means.
def _md():
    return MarkdownIt("commonmark").enable("table").enable("strikethrough")


def _tokens(markdown):
    return [(t.type, t.tag, t.content) for t in _md().parse(markdown)]


def _heading_block(bid, level, content, child_ids=()):
    """A heading{level} block (docx type ``level + 2``) carrying one plain run."""
    return {
        "block_id": bid,
        "parent_id": "root",
        "block_type": level + 2,
        f"heading{level}": {"elements": [{"text_run": {"content": content}}]},
        "children": list(child_ids),
    }


def _one_heading(level, content="Heading", child_ids=(), extra=()):
    blocks = [builders.page(*(["h", *[b["block_id"] for b in extra]])),
              _heading_block("h", level, content, child_ids)]
    blocks.extend(extra)
    return blocks


def _render_one_heading(level, content="Heading", child_ids=(), extra=()):
    return render(_one_heading(level, content, child_ids, extra), doc_id="root")


def _heading_line(level, content="Heading"):
    """The single emitted heading line for a lone heading{level} block."""
    out = _render_one_heading(level, content)
    lines = [ln for ln in out.split("\n") if ln.startswith("#") and content in ln]
    assert len(lines) == 1, f"expected exactly one heading line in:\n{out!r}"
    return lines[0]


# =========================================================================== #
# AC1 — the marker is capped at six ``#`` for levels 7, 8 and 9               #
# =========================================================================== #

@pytest.mark.parametrize("level", [7, 8, 9])
def test_ac1_level_7_8_9_render_with_exactly_six_hashes(level):
    """Each deep level asserted separately (maintainer: "go a bit nuts") — not one sample
    standing in for three registered block types (9 / 10 / 11)."""
    assert _heading_line(level, f"Heading {level}") == f"###### Heading {level}"


@pytest.mark.parametrize("level", [7, 8, 9])
def test_ac1_no_seven_hash_marker_survives_anywhere_in_the_output(level):
    """The regression in its own words: the pre-fix emission for these levels contained a
    7+ ``#`` run at line start. Nothing in the document may."""
    out = _render_one_heading(level, f"Heading {level}")
    offenders = [ln for ln in out.split("\n") if ln.lstrip().startswith("#######")]
    assert offenders == [], f"invalid ATX marker emitted: {offenders!r}\n{out!r}"


@pytest.mark.parametrize("level", list(range(1, 7)))
def test_ac1_levels_1_to_6_are_untouched_by_the_cap(level):
    """The boundary in both directions — H6 is exactly ``###### `` (the cap must not
    shave the level it is clamping *to*), and H1–H5 keep their own marker."""
    assert _heading_line(level, f"Heading {level}") == f"{'#' * level} Heading {level}"


def test_ac1_the_cap_constant_is_the_commonmark_atx_ceiling():
    """The clamp is a named constant, not a literal buried in a serializer — and its
    value is the ceiling the reference parser actually enforces."""
    assert MAX_HEADING_LEVEL == 6
    assert _tokens("#" * MAX_HEADING_LEVEL + " x")[0][:2] == ("heading_open", "h6")
    too_deep = "#" * (MAX_HEADING_LEVEL + 1) + " x"
    assert _tokens(too_deep)[0][0] == "paragraph_open"


def test_ac1_a_heading_with_no_sdk_payload_still_caps():
    """The ``content is None`` branch (the SDK heading attr absent) builds the marker on
    its own path — it is capped too, not just the text-carrying branch."""
    blocks = [builders.page("h"),
              {"block_id": "h", "parent_id": "root", "block_type": 9, "children": []}]
    out = render(blocks, doc_id="root")
    assert "#######" not in out, out
    assert "######" in out, out


# =========================================================================== #
# AC2 — the TREE keeps the true level; the cap is render-time only            #
# =========================================================================== #

@pytest.mark.parametrize("level", [7, 8, 9])
def test_ac2_the_tree_keeps_the_true_level_while_the_markdown_is_capped(level):
    """The workaround the bug report named ("read the tree") must keep working: the cap
    is a *serializer* concern and ``HeadingNode.level`` is untouched."""
    blocks = build_blocks(_one_heading(level, f"Heading {level}"))
    root = Parser(Config()).parse_docx_tree("root", blocks)
    headings = [n for n in root.children if isinstance(n, HeadingNode)]
    assert [n.level for n in headings] == [level]
    assert _heading_line(level, f"Heading {level}") == f"###### Heading {level}"


@pytest.mark.parametrize("level", [7, 8, 9])
def test_ac2_rendering_does_not_mutate_the_node_even_twice(level):
    """A cap implemented by *writing* ``node.level = 6`` would satisfy AC1 and quietly
    break every tree consumer. Render the SAME node twice and assert the level survives
    both passes (a mutating cap is idempotent, so one pass would not catch it)."""
    from larkdocio.model.renderer import MarkdownRenderer

    node = HeadingNode(level=level, content=None, children=[])
    renderer = MarkdownRenderer()
    first = renderer.render(node, 0)
    assert node.level == level
    second = renderer.render(node, 0)
    assert node.level == level
    assert first == second == "###### "


def test_ac2_the_write_side_still_authors_the_true_level():
    """Out of scope by design: authoring keeps levels 1–9 (heading7 → docx type 9). The
    cap must not leak into the encoder."""
    from larkdocio.write.encode import block_type_for

    for level in (7, 8, 9):
        nb = NewBlock.heading(level, "Section")
        assert nb.level == level
        assert block_type_for(nb) == level + 2


# =========================================================================== #
# AC3 — the reference parser reads the capped output AS A HEADING             #
# =========================================================================== #

@pytest.mark.parametrize("level", [7, 8, 9])
def test_ac3_the_capped_output_parses_as_a_level_6_heading(level):
    """THE assertion the old output failed. ``markdown-it-py`` (the same reference parser
    ``compose()`` is built on) must see a heading token, not a paragraph."""
    toks = _tokens(_heading_line(level, f"Heading {level}"))
    assert toks == [
        ("heading_open", "h6", ""),
        ("inline", "", f"Heading {level}"),
        ("heading_close", "h6", ""),
    ], toks


@pytest.mark.parametrize("level", [7, 8, 9])
def test_ac3_the_pre_fix_emission_would_have_been_a_paragraph(level):
    """The defect characterized, so the *reason* for the cap cannot rot: the exact string
    the reader used to emit is not a heading to a conforming parser."""
    pre_fix = f"{'#' * level} Heading {level}"
    toks = _tokens(pre_fix)
    assert [t[0] for t in toks] == ["paragraph_open", "inline", "paragraph_close"]
    assert toks[1][2] == pre_fix, "the excess #s arrive as literal text"


def test_ac3_a_whole_h1_h9_document_parses_as_nine_headings():
    """Ordering pinned end to end: a document mixing every level yields nine heading
    tokens in source order, levels 1–6 exact and 7–9 all h6."""
    blocks = [builders.page(*[f"h{n}" for n in range(1, 10)])]
    blocks += [dict(_heading_block(f"h{n}", n, f"Heading {n}"), parent_id="root")
               for n in range(1, 10)]
    out = render(blocks, doc_id="root")
    tags = [t[1] for t in _tokens(out) if t[0] == "heading_open"]
    # The page title renders as an H1 of its own ("# T"), hence the leading h1.
    assert tags == ["h1", "h1", "h2", "h3", "h4", "h5", "h6", "h6", "h6", "h6"], tags


# =========================================================================== #
# AC4 — the compose round-trip and the documented asymmetry                   #
# =========================================================================== #

@pytest.mark.parametrize("level", [7, 8, 9])
def test_ac4_the_readers_own_h7_9_output_composes_back_to_a_heading(level):
    """The round-trip the guide promises: authoring H7 keeps level 7 on the write side,
    the reader emits the capped line, and composing THAT line yields a real **H6**
    heading (the documented lossiness) — never a paragraph."""
    emitted = reader_markdown([NewBlock.heading(level, f"Heading {level}")])
    assert emitted == f"###### Heading {level}\n"

    recomposed = compose(emitted)
    assert [b.kind for b in recomposed] == [NewBlockKind.HEADING]
    assert recomposed[0].level == 6
    assert recomposed[0].text == f"Heading {level}"


@pytest.mark.parametrize("level", [7, 8, 9])
def test_ac4_the_capped_emission_is_a_fixed_point(level):
    """One more turn of the crank: the H6 that came back re-emits the SAME Markdown, so
    the lossiness is a single documented step down, not a drift that keeps moving."""
    emitted = reader_markdown([NewBlock.heading(level, f"Heading {level}")])
    assert reader_markdown(compose(emitted)) == emitted


@pytest.mark.parametrize("level", list(range(1, 7)))
def test_ac4_levels_1_to_6_remain_exactly_symmetric(level):
    """The guide's symmetry claim holds unchanged for the levels Markdown can express —
    same level in, same level out."""
    emitted = reader_markdown([NewBlock.heading(level, "Section")])
    assert emitted == f"{'#' * level} Section\n"
    recomposed = compose(emitted)
    assert [b.kind for b in recomposed] == [NewBlockKind.HEADING]
    assert recomposed[0].level == level


def test_ac4_a_stray_seven_hash_fragment_still_composes_as_literal_text():
    """Unchanged on the compose side: a hand-authored 7-``#`` line is a paragraph in
    CommonMark and stays one. The fix is that the *reader* no longer produces that line —
    ``compose()`` did not have to learn a non-standard shape."""
    content = compose("####### Heading 7\n")
    assert [b.kind for b in content] == [NewBlockKind.PARAGRAPH]
    assert content[0].text == "####### Heading 7"


# =========================================================================== #
# Amplifier — escaping interplay and children                                #
# =========================================================================== #

def test_amplifier_an_h7_whose_text_contains_hashes_stays_one_capped_heading():
    """LD-130 interplay: a ``#`` inside heading *text* is content. It must not be
    backslash-escaped (LD-130's no-backslash pin) and must not be mistaken for part of the
    marker — the reference parser sees one h6 whose content is the text verbatim."""
    line = _heading_line(7, "C# vs #hashtag")
    assert line == "###### C# vs #hashtag"
    assert "\\" not in line, line
    assert _tokens(line) == [
        ("heading_open", "h6", ""),
        ("inline", "", "C# vs #hashtag"),
        ("heading_close", "h6", ""),
    ]


def test_amplifier_an_h9_whose_text_starts_with_a_hash_marker():
    """The adversarial shape: capping brings the marker to six, and the text's own
    leading ``#`` sits right behind it. ATX consumes only the leading run, so the text
    survives intact rather than deepening the marker to seven."""
    line = _heading_line(9, "# not a marker")
    assert line == "###### # not a marker"
    assert _tokens(line)[1][2] == "# not a marker"


def test_amplifier_an_h8_with_children_keeps_its_blank_line_separation():
    """The child branch of the heading serializer is on the same code path as the marker;
    capping must not disturb the blank-line separation it emits."""
    out = render(
        [builders.page("h"),
         _heading_block("h", 8, "Deep section", ["c1"]),
         builders.text_block("c1", "h", "child body")],
        doc_id="root",
    )
    assert "###### Deep section\n\nchild body" in out, out
    assert "#######" not in out, out


def test_amplifier_the_all_headings_golden_shows_the_cap_and_only_the_cap():
    """AC5's consented move, asserted against the golden itself: H1–H6 byte-unchanged,
    H7–H9 all six ``#``, no 7-``#`` run anywhere."""
    golden = (FIXTURES_DIR / "all_headings.expected.md").read_text(encoding="utf-8")
    for level in range(1, 7):
        assert f"\n{'#' * level} Heading {level}\n" in golden, level
    for level in (7, 8, 9):
        assert f"\n###### Heading {level}\n" in golden, level
    assert "#######" not in golden


# =========================================================================== #
# AC4 / AC6 — the docs record the cap, and no longer claim the old behavior   #
# =========================================================================== #

_ROOT = Path(__file__).resolve().parents[1]
_WRITE_README = _ROOT / "src" / "larkdocio" / "write" / "README.md"
_GUIDE = _ROOT / "src" / "larkdocio" / "GUIDE.md"
_BLOCKS_MD = _ROOT / "BLOCKS.md"

#: The claims that must be gone from every shipped doc: the pre-LD-145 behavior was
#: documented as *deliberate* ("H7–H9 emit 7–9 `#` literally"), which is exactly how a
#: defect survives two releases. Matched on prose so a reflow cannot fake compliance —
#: and quoted with the **en-dashes the docs really use** (an ASCII-hyphen spelling would
#: match nothing and the guard would pass vacuously, which is the trap the bite test below
#: exists to close).
_RETIRED_CLAIMS = (
    "emit 7–9 # literally",
    "7–9 literal #",
    "most renderers show the excess",
)

#: The exact pre-LD-145 sentences, lifted from the three docs at ``develop``. Each retired
#: claim must be detectable in the text it came from — otherwise the "no longer claimed"
#: assertions above are vacuous.
_PRE_FIX_DOC_TEXT = {
    "BLOCKS.md": (
        "| 9 | heading7 | rendered | creatable | `headings.py` | `####### ` (7×`#`) + text "
        "| Markdown defines only H1–H6; H7–H9 emit 7–9 `#` literally (most renderers show "
        "the excess `#` as text). Faithful to the source's heading depth. |"
    ),
    "write/README.md": (
        "| heading levels **7–9** | 7–9 literal `#` (Markdown has no H7+) | composes as a "
        "**paragraph** of literal text; H7–H9 are creatable via `NewBlock.heading()` but "
        "not expressible in Markdown |"
    ),
}


def _row_for(path, needle):
    """The single matrix/table row of ``path`` containing ``needle``."""
    rows = [ln for ln in path.read_text(encoding="utf-8").split("\n")
            if ln.startswith("|") and needle in ln]
    assert len(rows) == 1, f"expected exactly one row with {needle!r} in {path.name}: {rows}"
    return rows[0]


def _assert_documents_the_cap(row):
    """``row`` states the six-``#`` cap and shows no 7+ ``#`` run.

    The no-7-run half is what makes the six-run half mean anything: ``########`` (the
    pre-fix H8 cell) *contains* ``######`` as a substring, so a bare "mentions ######"
    check passes the very text it is meant to catch.
    """
    assert "#######" not in row, f"a 7+ #-run is still documented as output: {row}"
    assert not missing_phrases(row, ["######", "capped"]), row


def test_ac4_the_lossiness_table_records_the_h7_9_readback_as_h6():
    """The dialect lossiness table (write/README.md § (b)) is where a consumer looks up
    what happens to a level it authored. It must now say ``######`` / H6, not 7 ``#``."""
    row = _row_for(_WRITE_README, "heading levels **7–9**")
    _assert_documents_the_cap(row)
    assert not missing_phrases(row, ["heading level 6"]), row
    assert not missing_phrases(row, ["newblock.heading()"]), (
        "the row must still say H7–H9 remain authorable at their true level", row)
    assert missing_phrases(row, _RETIRED_CLAIMS) == list(_RETIRED_CLAIMS), row


def test_ac4_the_shipped_guide_records_the_same_asymmetry():
    """The in-wheel guide (`larkdocio.guide()`) carries its own heading row — the two docs
    must not disagree about the round-trip a consumer will observe."""
    row = _row_for(_GUIDE, "| `heading` |")
    _assert_documents_the_cap(row)
    assert not missing_phrases(row, ["read back", "h6"]), row
    assert missing_phrases(row, _RETIRED_CLAIMS) == list(_RETIRED_CLAIMS), row


@pytest.mark.parametrize("doc", sorted(_PRE_FIX_DOC_TEXT))
def test_ac4_the_docs_guard_bites_on_the_real_pre_fix_text(doc):
    """The guard is only worth its line count if it fails on the text it replaced. Fed the
    **verbatim** pre-LD-145 row from each doc it must redden on the cap check *and* find at
    least one retired claim — the LD-138 red-then-green discipline for a prose guard, and
    the check that keeps ``_RETIRED_CLAIMS`` honest (a phrase spelled with the wrong dash
    would match nothing and pass every doc vacuously)."""
    stale = _PRE_FIX_DOC_TEXT[doc]
    with pytest.raises(AssertionError):
        _assert_documents_the_cap(stale)
    caught = [c for c in _RETIRED_CLAIMS if not missing_phrases(stale, [c])]
    assert caught, f"no retired claim matches the real pre-fix {doc} text: {stale!r}"


def test_ac4_every_retired_claim_is_detectable_somewhere_in_the_pre_fix_text():
    """No dead entry in ``_RETIRED_CLAIMS``: each one must really appear in one of the
    pre-fix rows, so the tuple cannot silently become decoration."""
    for claim in _RETIRED_CLAIMS:
        assert any(not missing_phrases(t, [claim]) for t in _PRE_FIX_DOC_TEXT.values()), (
            f"{claim!r} matches none of the pre-fix rows — it guards nothing")


def test_ac4_the_cap_guard_is_not_fooled_by_a_longer_hash_run():
    """The substring trap the H8 row would have walked into: eight ``#`` *contains* six, so
    a bare "mentions ``######``" check passes the exact text it must reject."""
    with pytest.raises(AssertionError):
        _assert_documents_the_cap("| 10 | heading8 | `########` (8×`#`) + text | capped |")
    _assert_documents_the_cap(_row_for(_WRITE_README, "heading levels **7–9**"))


@pytest.mark.parametrize("block_type,level", [(9, 7), (10, 8), (11, 9)])
def test_ac6_the_blocks_md_heading_rows_record_the_cap_and_the_true_level(block_type, level):
    """AC6: BLOCKS.md is the capability source of truth for the docx block surface, and
    types 9/10/11 are the three rows whose documented output just changed. Each must state
    the render cap **and** that the tree keeps the true level."""
    row = _row_for(_BLOCKS_MD, f"| {block_type} | heading{level} |")
    _assert_documents_the_cap(row)
    assert missing_phrases(row, _RETIRED_CLAIMS) == list(_RETIRED_CLAIMS), row


def test_ac6_the_blocks_md_heading_family_states_the_true_level_survives():
    """Stated once for the family (the H7 row carries the note the H8/H9 rows point at):
    the cap is render-time and ``HeadingNode.level`` is untouched."""
    row = _row_for(_BLOCKS_MD, "| 9 | heading7 |")
    assert not missing_phrases(row, [
        "capped", "true level", "headingnode", "ld-145",
    ]), row


# =========================================================================== #
# The cross-seam pair (LD-144 carry-forward) — one doctrine, two dialects     #
# =========================================================================== #

#: A 2x2 merged table (cell 0 anchors a rowspan of 2, ``header_row`` false so cell 0 is a
#: ``<td>``) — the shape that takes the reader's HTML-``<table>`` path.
_ROWSPAN2 = [{"row_span": 2, "col_span": 1}, {"row_span": 1, "col_span": 1},
             {"row_span": 1, "col_span": 1}, {"row_span": 1, "col_span": 1}]


def _doc_with_heading_at_both_seams(level):
    """One document carrying heading{level} **twice**: once at top level (Markdown seam)
    and once inside a merged table cell (HTML seam)."""
    blocks = [
        page("top", "tbl"),
        _heading_block("top", level, f"Top {level}"),
        table("tbl", "root", 2, ["c0", "c1", "c2", "c3"],
              {"row_size": 2, "merge_info": _ROWSPAN2, "header_row": False}),
        cell("c0", "tbl", ["ch"]),
        dict(_heading_block("ch", level, f"Cell {level}"), parent_id="c0"),
    ]
    for i, txt in enumerate(("B", "C", "D"), start=1):
        blocks.append(cell(f"c{i}", "tbl", [f"c{i}t"]))
        blocks.append(builders.text_block(f"c{i}t", f"c{i}", txt))
    return render(blocks, doc_id="root")


@pytest.mark.parametrize("level", [7, 8, 9])
def test_cross_seam_h7_9_caps_in_markdown_and_degrades_in_a_merged_cell(level):
    """The carry-forward pair asserted **together** (LD-144's QA raised it): the same
    over-deep heading resolves to ``######`` at the Markdown seam and to
    ``<p><strong>…</strong></p>`` inside a merged cell. Both are valid output; the
    divergence is deliberate (module docstring) and neither invents a marker its dialect
    does not have."""
    out = _doc_with_heading_at_both_seams(level)
    assert f"###### Top {level}" in out, out
    assert f"<p><strong>Cell {level}</strong></p>" in out, out
    assert f"<h{level}>" not in out, out
    assert "#######" not in out, out


def test_cross_seam_an_h6_still_reaches_both_seams_at_its_true_level():
    """The control: at level 6 both dialects can say what the tree says, and both do —
    which is what makes the level-7 divergence a *ceiling* behavior and not two
    unrelated rules."""
    out = _doc_with_heading_at_both_seams(6)
    assert "###### Top 6" in out, out
    assert "<h6>Cell 6</h6>" in out, out


@pytest.mark.parametrize("level", [7, 8, 9])
def test_cross_seam_no_dialect_ever_invents_a_marker_it_does_not_have(level):
    """The one shared rule: no ``#######`` in the Markdown, no ``<h7>``/``<h8>``/``<h9>``
    in the HTML — the true level lives in the tree, and only there."""
    out = _doc_with_heading_at_both_seams(level)
    for tag in (f"<h{level}>", f"</h{level}>"):
        assert tag not in out, out
    assert not any(ln.lstrip().startswith("#######") for ln in out.split("\n")), out

    blocks = build_blocks(_one_heading(level, f"Heading {level}"))
    root = Parser(Config()).parse_docx_tree("root", blocks)
    assert [n.level for n in root.children if isinstance(n, HeadingNode)] == [level]
