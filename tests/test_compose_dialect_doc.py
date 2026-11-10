"""The shipped dialect + lossiness documentation must tell the TRUTH
(LD-136: *lossiness is DOCUMENTED, not discovered*).

The doc lives in the **shipped** `larkdocio/write/README.md` (packaged as package-data, so a
consumer reading the vendored wheel gets it) under § "The composable Markdown dialect".
These tests bind it to the code both ways — a construct the compiler can refuse with no row
in the table reddens, and a phantom row for a construct the code does not have reddens too.

They also pin the *other* half of AC4: the D2 exclusions (images/media, boards, embedded
surfaces, callouts, grids, colors) named as **not expressible**, with what `compose()` really
does when handed the reader's own emission for one — which is the honest end of the
round-trip, and the only way "not creatable" can be checked rather than claimed.
"""
import re
from pathlib import Path

import pytest

from larkdocio.write import NOT_EXPRESSIBLE_CONSTRUCTS, compose
from larkdocio.write.model import (
    MAX_CHILDREN_PER_CALL,
    MAX_NEST_DEPTH,
    MAX_TABLE_CELLS,
    NewBlockKind,
    RefusalReason,
    RefusedError,
)

_README = Path(__file__).resolve().parents[1] / "src" / "larkdocio" / "write" / "README.md"
_SECTION_HEADING = "## The composable Markdown dialect (`compose`)"


def _dialect_section() -> str:
    text = _README.read_text(encoding="utf-8")
    start = text.find(_SECTION_HEADING)
    assert start != -1, f"write/README.md has no {_SECTION_HEADING!r} section"
    rest = text[start + len(_SECTION_HEADING):]
    nxt = re.search(r"^## ", rest, flags=re.MULTILINE)
    return _SECTION_HEADING + (rest[: nxt.start()] if nxt else rest)


def _refusal_table_constructs() -> set:
    """The first-column code spans of the '(a) Constructs that REFUSE' table."""
    section = _dialect_section()
    start = section.index("**(a) Constructs that REFUSE.**")
    end = section.index("**(b)", start)
    return set(re.findall(r"^\| `([a-z-]+)` \|", section[start:end], flags=re.MULTILINE))


# =========================================================================== #
# AC4 — the lossiness table is bound to the code, both ways                     #
# =========================================================================== #

def test_ac4_the_dialect_section_ships_in_the_write_readme():
    section = _dialect_section()
    for expected in (
        "What composes", "Lossiness — documented, not discovered",
        "Constructs that REFUSE", "Not creatable in this rung",
        "Normalizations", "asymmetries",
    ):
        assert expected in section


def test_ac4_every_refusable_construct_has_a_documented_row():
    documented = _refusal_table_constructs()
    missing = sorted(set(NOT_EXPRESSIBLE_CONSTRUCTS) - documented)
    assert not missing, (
        f"the compiler can refuse {missing} but the shipped lossiness table has no row for "
        f"them — a refusal a consumer cannot look up is undocumented lossiness"
    )


def test_ac4_the_table_has_no_phantom_construct():
    documented = _refusal_table_constructs()
    phantom = sorted(documented - set(NOT_EXPRESSIBLE_CONSTRUCTS))
    assert not phantom, (
        f"the shipped lossiness table documents {phantom}, which the compiler cannot "
        f"actually refuse — a phantom claim is worse than a gap"
    )


def test_ac4_the_guard_bites_red_then_green():
    """Red-then-green, the LD-133 discipline: the same bidirectional check that guards the
    table reports drift on a dropped row and on a phantom row, and is clean on the truth."""
    truth = set(NOT_EXPRESSIBLE_CONSTRUCTS)
    documented = _refusal_table_constructs()
    assert not (truth - documented) and not (documented - truth)

    dropped = documented - {"image"}
    assert truth - dropped == {"image"}
    phantomed = documented | {"blink-tag"}
    assert phantomed - truth == {"blink-tag"}


def test_ac4_the_documented_caps_are_the_real_ones():
    """A doc that names a cap must name the code's cap."""
    section = _dialect_section()
    assert "MAX_NEST_DEPTH" in section and "MAX_TABLE_CELLS" in section
    md = "".join("\t" * d + f"- L{d + 1}\n" for d in range(MAX_NEST_DEPTH + 1))
    with pytest.raises(RefusedError) as exc:
        compose(md)
    assert str(MAX_NEST_DEPTH) in exc.value.refusal.detail
    # LD-481 superseded the value 200 → 500 (the per-cell fill it budgeted for is batched
    # now); the assertion is TRANSFORMED, not struck — what it holds is that the doc's
    # rationale describes the number the code actually carries.
    assert MAX_TABLE_CELLS == 500            # the number the doc's rationale describes


def test_ac2_the_call_cap_is_disclosed_in_the_dialect_section_too():
    """The bug this pins: ``compose()`` accepted 51+ top-level blocks silently while the
    50-per-call cap was already exported — validate-late on the door a consumer reaches
    for first. The dialect section is that door's shipped doc; it must name the cap, say
    the count is ``len(compose(...))``, and disambiguate the exception TYPE (a plain
    ``ValueError`` from ``InsertRequest``'s constructor — never the ``RefusedError`` the
    "Constructs that REFUSE" table above documents for every OTHER cap)."""
    section = _dialect_section()
    assert "MAX_CHILDREN_PER_CALL" in section
    assert str(MAX_CHILDREN_PER_CALL) in section
    assert MAX_CHILDREN_PER_CALL == 50       # the number the doc's prose describes
    assert "len(compose(" in section, "the section never shows the len(...) check"
    assert "InsertRequest" in section, "the section never says WHERE the cap fires"
    assert "ValueError" in section, "the section never names the exception TYPE"
    # This cap is NOT one of compose()'s own RefusedError refusals — the disambiguation
    # must be explicit, not merely absent (round 4's STALE_SHEET shape, inverted).
    assert "not a `RefusedError`" in section or "not a RefusedError" in section


def test_ac4_the_merged_cell_lossiness_is_named_in_the_table():
    """AC4 names merged cells explicitly (carried from S2)."""
    section = _dialect_section()
    assert "Merged cells are not expressible" in section
    assert "colspan" in section and "ragged" in section


@pytest.mark.parametrize("excluded", [
    "images / media", "boards", "embedded surfaces", "callouts", "grids", "colors",
])
def test_ac4_every_d2_exclusion_is_named_as_not_creatable(excluded):
    """AC4's checklist: each D2 exclusion is named in the 'not creatable in this rung'
    table, with what ``compose()`` does instead."""
    assert excluded in _dialect_section()


# =========================================================================== #
# AC4 — the exclusions are CHECKED, not claimed: composing the reader's own      #
#       emission for a non-creatable block refuses (or lands where documented).   #
# =========================================================================== #

@pytest.mark.parametrize("name,reader_output,construct", [
    ("image", "![a caption](boxcnimgtoken)\n", "image"),
    ("board", "![Whiteboard](whiteboardtoken)\n", "image"),
    ("file-attachment",
     "\U0001F4CE **File Attachment:** spec.pdf (token: `filetoken`)\n", "bold"),
    ("embedded-sheet",
     "> \U0001F4CA **Embedded Sheet** — not fetched. token: `shttoken`.\n", "bold"),
    ("embedded-base",
     "> \U0001F4CA **Embedded Base** (bitable) — not fetched. token: `bastoken`.\n", "bold"),
    ("synced-block",
     "> \U0001F517 **Synced content** referenced from document `doc` (block `b`).\n", "bold"),
    ("divider", "---\n", "thematic-break"),
    ("underline-run", "<u>underlined</u>\n", "html"),
    ("merged-table", "<table>\n<tr><th>a</th></tr>\n</table>\n", "merged-table"),
    ("doc-mention", "[Example Document](https://example.com/docx/abc)\n", "link"),
])
def test_ac4_the_readers_emission_for_a_non_creatable_block_refuses(
    name, reader_output, construct,
):
    """The reader emits a marker (or HTML) for every block this rung cannot create.
    Composing that emission **refuses naming the construct** — so a consumer cannot
    accidentally author a flattened stand-in for a board, an embed or a merge."""
    with pytest.raises(RefusedError) as exc:
        compose(reader_output)
    assert construct in exc.value.refusal.detail
    assert exc.value.refusal.reason in (
        RefusalReason.NOT_IN_DIALECT, RefusalReason.MERGE_NOT_EXPRESSIBLE,
    )


def test_ac4_a_callout_composes_to_a_quote_because_the_reader_already_collapsed_it():
    """Documented, not silent: a callout is emitted as ``> `` lines, which IS a quote in
    Markdown — the projection happened in the *reader*, and compose is faithful to the
    dialect it is given."""
    content = compose("> callout line one\n> callout line two\n")
    assert [b.kind for b in content] == [NewBlockKind.QUOTE]


def test_ac4_an_equation_block_composes_as_literal_text():
    """``$$…$$`` is not a CommonMark construct, so it is literal text — the equation
    *rendering* is what is lost, and the text survives verbatim."""
    content = compose("$$\nE = mc^2\n$$\n")
    assert [b.kind for b in content] == [NewBlockKind.PARAGRAPH]
    assert content[0].text == "$$\nE = mc^2\n$$"


def test_ac4_a_heading_deeper_than_h6_composes_as_literal_text():
    """Markdown has no H7+: a 7-``#`` line is a paragraph in CommonMark and composes as
    one. Since **LD-145** the *reader* no longer emits that line — it caps its marker at
    ``######``, so its own H7–H9 output composes back to a real **H6** heading (the
    documented lossiness; asserted in ``tests/test_heading_level_cap.py``). This case is
    the hand-authored-fragment half, unchanged: ``compose()`` never learned a
    non-standard shape."""
    content = compose("####### Heading 7\n")
    assert [b.kind for b in content] == [NewBlockKind.PARAGRAPH]
    assert content[0].text == "####### Heading 7"


def test_ac4_an_iframe_emission_composes_to_its_url_as_text():
    """The reader emits ``[url](url)`` for an iframe — byte-identical to what its own
    linkify pass emits for a bare URL in prose — so composing it yields the paragraph.
    Named in the lossiness table as the reader-side ambiguity it is."""
    content = compose("[https://example.com/embed](https://example.com/embed)\n")
    assert [b.kind for b in content] == [NewBlockKind.PARAGRAPH]
    assert content[0].text == "https://example.com/embed"
