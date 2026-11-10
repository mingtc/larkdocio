"""The comments surface's TRUTH ROWS and its ZERO-DRIFT promise.

Two unrelated-looking things, in one file because both are about the surface's edges rather
than its behaviour.

**Zero drift.** Comments are a separate read. Adding them must not move one byte of the
Markdown a document converts to — the whole golden corpus is re-rendered here and compared,
and the new package is proved to touch neither the renderer nor the parser.

**Truth rows.** The capability registry, the shipped guide and the spreadsheet matrix each
have to know about this surface, and every consumer-reaching string it emits has to be free of
this repo's internal shorthand — a consumer has only the wheel, so an issue id or a criterion
reference in a message resolves to nothing for them.
"""
import ast
import inspect
import json
import pathlib

import consumer_text
import pytest

import larkdocio
from larkdocio import capabilities
from larkdocio.comments import (
    REVERSE_JOIN_NOTE,
    SHEETS_NO_CELL_ANCHOR_NOTE,
    SHEETS_READ_ACCEPTED_CREATE_REJECTED_NOTE,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
COMMENTS_PKG = REPO_ROOT / "src" / "larkdocio" / "comments"


# --------------------------------------------------------------------------- #
# AC11 — ZERO reader-output drift.                                              #
# --------------------------------------------------------------------------- #

def test_the_whole_golden_corpus_still_renders_byte_identically():
    """The strongest available in-suite form: every fixture through the shipped pipeline,
    compared against its committed expectation."""
    from harness import FIXTURES_DIR, render

    pairs = sorted(FIXTURES_DIR.glob("*.input.json"))
    assert pairs, "the golden corpus is empty — this assertion would prove nothing"

    checked = 0
    for input_path in pairs:
        expected_path = input_path.with_name(
            input_path.name.replace(".input.json", ".expected.md"))
        if not expected_path.exists():
            continue
        got = render(json.loads(input_path.read_text(encoding="utf-8")))
        assert got == expected_path.read_text(encoding="utf-8"), (
            f"{input_path.name} no longer renders to its golden output")
        checked += 1
    assert checked == len(pairs), "a fixture lost its expected output"


def test_the_comments_package_touches_NEITHER_the_renderer_NOR_the_parser():
    """Structural: the read cannot drift the Markdown if it never reaches the code that
    produces it. The package may READ the model's nodes; it may not import the serializer or
    the parser."""
    forbidden = ("larkdocio.model.renderer", "larkdocio.read.parser", "MarkdownRenderer")
    for path in sorted(COMMENTS_PKG.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                statement = ast.unparse(node)
                for name in forbidden:
                    assert name not in statement, (
                        f"{path.relative_to(REPO_ROOT)} imports {name}: {statement}")


def test_nothing_in_the_reader_or_the_model_imports_the_comments_package():
    """The dependency arrow points one way. If the reader reached for comments, converting a
    document could start making comment calls — which is the drift this pins shut."""
    offenders = []
    for part in ("read", "blocks", "model"):
        for path in sorted((REPO_ROOT / "src" / "larkdocio" / part).rglob("*.py")):
            if "larkdocio.comments" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, offenders


def test_the_model_gained_no_node_type_and_the_renderer_no_branch():
    from larkdocio import model
    from larkdocio.model import renderer

    # Counted over the exported NODE TYPES, which is what this guard is about. The model
    # package also exports plain functions (the tree-reading helpers, the block-identity
    # projection and its inverse) and two classes that are not nodes (the renderer and the
    # projection's result value), so a raw ``len(__all__)`` — or even a count of every
    # exported class — would report one of those as a new node type.
    types = [
        n for n in model.__all__
        if isinstance(getattr(model, n), type)
        and issubclass(getattr(model, n), (model.Node, model.Inline))
    ]
    assert len(types) == 43, types
    assert not [n for n in model.__all__ if "omment" in n]
    # The precise invariant, not a word ban: the serializer never READS the anchor field and
    # has no comment-shaped branch. (Its prose uses the ordinary English word, which is fine.)
    source = inspect.getsource(renderer)
    assert "comment_ids" not in source
    assert "Comment" not in source


# --------------------------------------------------------------------------- #
# AC13 — the truth rows.                                                        #
# --------------------------------------------------------------------------- #

def test_the_capability_registry_carries_the_comments_surface_with_real_gate_coverage():
    surface = capabilities(full=True)["surfaces"]["docx-comments-read"]

    assert surface["mode"] == "read"
    assert surface["credentials"]["app"] == "read"
    assert "docx:document:readonly" in surface["credentials"]["scopes"]
    # The scope that is deliberately NOT requested is stated, so "why are authors ids?" is
    # answerable from the registry alone.
    assert "NOT requested" in surface["credentials"]["note"]
    assert "raw ids" in surface["credentials"]["note"]
    assert surface["gate_coverage"]["members"], "a read surface claiming a gate must name it"

    names = {op["name"] for op in surface["operations"]}
    assert {"comments", "list_comments", "batch_query_comments", "list_replies"} == names


def test_the_registry_still_round_trips_through_json():
    caps = capabilities(full=True)
    assert json.loads(json.dumps(caps)) == caps


def test_the_shipped_guide_carries_a_comments_recipe_that_teaches_the_four_traps():
    guide = larkdocio.guide(full=True)
    assert "### Recipe: read the comments on a document" in guide

    from guide_recipes import recipe_preamble

    preamble = recipe_preamble("read-the-comments-on-a-document")
    for phrase in (
        "raw ids, not names",              # authorship
        "three values, not two",           # the tri-state scope
        "before you believe an empty list",  # the never-silent posture
        "no API call",                     # the zero-anchor cost
    ):
        assert phrase in preamble, f"the recipe's preamble does not teach: {phrase!r}"


def test_the_guide_discloses_the_spreadsheet_asymmetry_and_the_missing_cell_anchor():
    """**Transformed by LD-541; the claim is unchanged and the mechanism is corrected.**

    This used to slice the section by hand — from its own heading to *the heading that happened
    to follow it in the document*. The claim it makes is about the comments-read recipe, but the
    slice it made that claim over was defined by an unrelated recipe's title, so the guide's
    restructure (which grouped the recipes by task and moved the style-fidelity recipe two
    sections earlier) turned a true assertion into a ``ValueError``. The library's own resolver
    answers the same question and cannot be moved out from under: ``guide(section=…)`` returns
    the section's own bytes and stops at the next heading of the same or higher level, whatever
    that heading happens to be.
    """
    section = larkdocio.guide(section="recipe-read-the-comments-on-a-document")
    assert 'file_type="sheet"' in section
    assert "refusing to **create** one there at all" in section
    assert "no structured cell reference" in section
    assert "not a coordinate" in section


def test_the_guide_states_the_reverse_join_is_not_implemented_with_its_reason():
    guide = larkdocio.guide(full=True)
    assert "not implemented" in guide and "not claimed" in guide
    assert "cannot be created through the API at all" in guide


def test_the_spreadsheet_matrix_records_the_leg_and_the_asymmetry():
    sheets_md = (REPO_ROOT / "SHEETS.md").read_text(encoding="utf-8")
    row = [line for line in sheets_md.splitlines()
           if line.startswith("| comments read (spreadsheet leg)")]
    assert len(row) == 1, "SHEETS.md must carry exactly one comments-read row"
    row = row[0]

    assert "`shipped-LD-159`" in row
    assert "larkdocio.comments.read.comments" in row
    # Both halves of the asymmetry, with the server's own words.
    assert "READ** on a spreadsheet token is ACCEPTED" in row
    assert "99992402" in row and "options: [doc,docx]" in row
    assert "1069307" in row, "the wrong-file-type control belongs in the row"
    # And the anchoring disclosure.
    assert "NO STRUCTURED CELL ANCHOR" in row
    assert "never** presents a spreadsheet comment as" in row
    # The status vocabulary must define the slug it uses.
    assert "| **shipped-LD-159** |" in sheets_md


@pytest.mark.parametrize("note", [
    REVERSE_JOIN_NOTE,
    SHEETS_NO_CELL_ANCHOR_NOTE,
    SHEETS_READ_ACCEPTED_CREATE_REJECTED_NOTE,
])
def test_every_disclosure_string_is_dialect_free(note):
    """A consumer has only the wheel. These strings are handed to them verbatim, so an issue
    id, a criterion reference or an internal role name in one resolves to nothing."""
    assert consumer_text.dialect_hits(note) == []


def test_every_string_the_comments_package_emits_is_dialect_free():
    """The whole package, not only the named notes — the repo-wide guard's own corpus, narrowed
    to this surface so a failure names it directly."""
    report = [(label, name, matched) for label, name, matched, _snippet
              in consumer_text.corpus_dialect_report()
              if "comments" in label]
    assert report == [], report


def test_the_package_docstrings_reach_a_consumer_and_say_the_four_refusals():
    """The module's own documentation is a consumer surface (they can ``help()`` it), and it is
    where the four things this surface will not do are stated."""
    doc = larkdocio.comments.__doc__
    for phrase in (
        "never guesses an author's name",
        "never infers a location",
        "never renders comments into the document's Markdown",
        'never reports "no comments" when it does not know',
    ):
        assert phrase in doc, f"the package documentation does not state: {phrase!r}"
