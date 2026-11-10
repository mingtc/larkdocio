"""The public tree helpers — ``model.walk`` + ``model.plain_text`` (LD-171 / round-3 F1+F10+F17).

**The defect these tests pin.** The guide handed a consumer a pasted ``walk()`` docstringed
"Every block in the document, outermost first" that followed only ``.children``. Two of the
model's container shapes do not use that attribute — ``TableNode`` holds its cells on
``.cells`` and ``GridNode`` holds its columns on ``.columns`` — so the walker silently reached
only part of a document: every table cell was missed, so every figure in a table was too
(the proposal-shaped example below is the shape). Its paired ``text_of()`` read ``.content``
off each run, so a ``MentionUser`` (which carries ``.user_id``) contributed nothing: "@alice
please own this" reduced to "".

So the helpers become real, tested, public functions and the guide pastes THOSE. The load-bearing
subtlety is the last section: ``write.block_plain_text`` must NOT be reused for reading — it
excludes mentions *deliberately*, because it backs anchor quote-matching, and a mention is not
text a user can literally quote. A test pins that the two MUST DIFFER.
"""
import gc

import pytest
from harness import build_blocks

from larkdocio.model import (
    GridNode,
    HeadingNode,
    Inline,
    InlineEquation,
    MentionDoc,
    MentionUser,
    PageNode,
    RawInline,
    StyledText,
    TableCellNode,
    TableNode,
    Text,
    TextNode,
    UnsupportedInline,
    plain_text,
    walk,
)
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write.resolve import block_plain_text


# --------------------------------------------------------------------------- #
# Fixtures — real SDK block payloads, parsed by the real parser.                #
# --------------------------------------------------------------------------- #

def _tree(block_dicts, doc_id="root"):
    """The node tree the shipped reader builds from ``block_dicts``."""
    return Parser(Config()).parse_docx_tree(doc_id, build_blocks(block_dicts))


def _text(bid, parent, content, block_type=2, key="text", children=()):
    return {
        "block_id": bid, "parent_id": parent, "block_type": block_type,
        key: {"elements": [{"text_run": {"content": content}}]},
        "children": list(children),
    }


#: A document holding EVERY container shape the model has: a table (``.cells``), a grid
#: (``.columns``), nested lists (``.children`` that deepen), and a callout. The table is the
#: shape the pasted walker missed, and its cells carry the figures. Example text, not taken
#: from any document.
BUSINESS_CASE_DOC = [
    {"block_id": "root", "parent_id": "doc", "block_type": 1,
     "page": {"elements": [{"text_run": {"content": "Q3 Proposal"}}]},
     "children": ["h1", "tbl", "grid", "b1", "callout", "div"]},
    _text("h1", "root", "Business Case", block_type=3, key="heading1"),
    # the table: 2x2, holding the figures.
    {"block_id": "tbl", "parent_id": "root", "block_type": 31,
     "table": {"property": {"column_size": 2}},
     "children": ["c1", "c2", "c3", "c4"]},
    {"block_id": "c1", "parent_id": "tbl", "block_type": 32, "table_cell": {},
     "children": ["c1t"]},
    {"block_id": "c2", "parent_id": "tbl", "block_type": 32, "table_cell": {},
     "children": ["c2t"]},
    {"block_id": "c3", "parent_id": "tbl", "block_type": 32, "table_cell": {},
     "children": ["c3t"]},
    {"block_id": "c4", "parent_id": "tbl", "block_type": 32, "table_cell": {},
     "children": ["c4t"]},
    _text("c1t", "c1", "Cost"),
    _text("c2t", "c2", "240 units"),
    _text("c3t", "c3", "Revenue"),
    _text("c4t", "c4", "1,150 units"),
    # the grid: two columns, each with a paragraph.
    {"block_id": "grid", "parent_id": "root", "block_type": 24,
     "grid": {"column_size": 2}, "children": ["gc1", "gc2"]},
    {"block_id": "gc1", "parent_id": "grid", "block_type": 25, "grid_column": {},
     "children": ["g1t"]},
    {"block_id": "gc2", "parent_id": "grid", "block_type": 25, "grid_column": {},
     "children": ["g2t"]},
    _text("g1t", "gc1", "left column"),
    _text("g2t", "gc2", "right column"),
    # a nested list.
    _text("b1", "root", "outer bullet", block_type=12, key="bullet", children=["b2"]),
    _text("b2", "b1", "inner bullet", block_type=12, key="bullet", children=["o1"]),
    _text("o1", "b2", "an ordered item", block_type=13, key="ordered"),
    # a callout, and a divider (a childless leaf).
    {"block_id": "callout", "parent_id": "root", "block_type": 19,
     "callout": {"emoji_id": "bulb"}, "children": ["cot"]},
    _text("cot", "callout", "mind the deadline"),
    {"block_id": "div", "parent_id": "root", "block_type": 22, "divider": {},
     "children": []},
]

#: The deepest container nesting the model allows: a TABLE inside a CELL inside a GRID.
#: Every level uses a different attribute, so a walker that knows only one of them stops.
DEEPEST_NESTING_DOC = [
    {"block_id": "root", "parent_id": "doc", "block_type": 1,
     "page": {"elements": [{"text_run": {"content": "Deep"}}]},
     "children": ["grid"]},
    {"block_id": "grid", "parent_id": "root", "block_type": 24,
     "grid": {"column_size": 1}, "children": ["gc1"]},
    {"block_id": "gc1", "parent_id": "grid", "block_type": 25, "grid_column": {},
     "children": ["outer"]},
    {"block_id": "outer", "parent_id": "gc1", "block_type": 31,
     "table": {"property": {"column_size": 1}}, "children": ["ocell"]},
    {"block_id": "ocell", "parent_id": "outer", "block_type": 32, "table_cell": {},
     "children": ["inner"]},
    {"block_id": "inner", "parent_id": "ocell", "block_type": 31,
     "table": {"property": {"column_size": 1}}, "children": ["icell"]},
    {"block_id": "icell", "parent_id": "inner", "block_type": 32, "table_cell": {},
     "children": ["deep"]},
    _text("deep", "icell", "the buried figure: 42 units"),
]


def _children_only(node):
    """The guide's SHIPPED-AND-BROKEN walker, verbatim, kept as the test's oracle.

    This is the traversal the guide pasted twice. It exists here so the fix is proven
    against the actual defect rather than against a paraphrase of it.
    """
    yield node
    for child in getattr(node, "children", None) or ():
        yield from _children_only(child)


def _every_node_by_hand(node):
    """An INDEPENDENT enumeration of the tree, written against the node classes by hand.

    Deliberately typed (``isinstance``) rather than duck-typed, so it shares no code and no
    attribute-lookup assumption with :func:`walk`: if the two agree, they agree for real.
    """
    out = [node]
    if isinstance(node, TableNode):
        kids = list(node.cells)
    elif isinstance(node, GridNode):
        kids = [kid for column in node.columns for kid in column]
    else:
        kids = list(getattr(node, "children", None) or ())
    for kid in kids:
        out.extend(_every_node_by_hand(kid))
    return out


# --------------------------------------------------------------------------- #
# AC1 — walk() follows .children + .cells + .columns, completely.               #
# --------------------------------------------------------------------------- #

def test_walk_visits_every_node_of_every_container_shape():
    """AC1: a document with a table, a grid, nested lists and a callout is walked
    COMPLETELY — the count matches an independent by-hand enumeration of the tree."""
    root = _tree(BUSINESS_CASE_DOC)
    walked = list(walk(root))
    by_hand = _every_node_by_hand(root)
    assert [id(n) for n in walked] == [id(n) for n in by_hand], (
        f"walk() visited {len(walked)} nodes; the tree has {len(by_hand)}"
    )


def test_walk_reaches_the_table_cells_and_the_grid_columns_by_name():
    """AC1: the two attributes the pasted helper never followed are named in the assertion,
    so a regression says WHICH shape was dropped."""
    root = _tree(BUSINESS_CASE_DOC)
    walked = list(walk(root))
    cells = [n for n in walked if isinstance(n, TableCellNode)]
    assert len(cells) == 4, f"walk() reached {len(cells)} of the table's 4 cells (.cells)"
    texts = {plain_text(n) for n in walked}
    assert "1,150 units" in texts, "a figure inside a table cell was not reached"
    assert {"left column", "right column"} <= texts, (
        "a paragraph inside a grid column was not reached (.columns)"
    )


def test_walk_is_document_order_outermost_first():
    """AC1: the documented contract — a node is yielded before its own children, and
    siblings in payload order."""
    root = _tree(BUSINESS_CASE_DOC)
    ids = [n.block_id for n in walk(root)]
    assert ids[:3] == ["root", "h1", "tbl"]
    assert ids.index("tbl") < ids.index("c1") < ids.index("c1t")
    assert ids.index("c1") < ids.index("c2") < ids.index("c3") < ids.index("c4")


def test_walk_is_a_generator_and_is_safe_to_consume_twice_by_re_calling():
    """Rigor: ``walk`` is lazy (a generator, so a caller may stop early on a huge document),
    and re-calling it yields the same tree again — a consumed generator is not a trap."""
    import inspect

    root = _tree(BUSINESS_CASE_DOC)
    assert inspect.isgenerator(walk(root)), "walk() must be lazy, not a materialized list"
    first = [n.block_id for n in walk(root)]
    second = [n.block_id for n in walk(root)]
    assert first == second and len(first) > 1
    # laziness is observable: taking one node must not have walked the whole tree.
    gen = walk(root)
    assert next(gen) is root


def test_walk_visits_the_deepest_container_nesting_exactly_once_each():
    """Rigor: a TABLE inside a CELL inside a GRID — the deepest nesting the model allows —
    is walked completely and with NO node visited twice (a naive union of ``.children`` and
    ``.cells`` would double-count a container that grew both)."""
    root = _tree(DEEPEST_NESTING_DOC)
    walked = list(walk(root))
    seen = [id(n) for n in walked]
    assert len(seen) == len(set(seen)), "walk() visited a node more than once"
    assert [n.block_id for n in walked] == [
        "root", "grid", "outer", "ocell", "inner", "icell", "deep",
    ], [n.block_id for n in walked]
    assert "the buried figure: 42 units" in {plain_text(n) for n in walked}


def test_walk_of_a_childless_leaf_yields_only_itself():
    assert [n.block_id for n in walk(TextNode(content=[Text("x")], block_id="only"))] == ["only"]


# --------------------------------------------------------------------------- #
# AC2 — the reported miss, red-then-green, with both counts in the message.      #
# --------------------------------------------------------------------------- #

def test_ac2_the_children_only_traversal_misses_the_cells_and_walk_does_not():
    """AC2: the reported reproduction, on a fixture. The shipped-and-broken
    ``.children``-only traversal reaches a fraction of the tree; ``walk`` reaches all of it.
    Both counts are quoted in the assertion message.
    """
    root = _tree(BUSINESS_CASE_DOC)
    broken = list(_children_only(root))
    fixed = list(walk(root))

    missed = [n for n in fixed if id(n) not in {id(b) for b in broken}]
    kinds = {}
    for node in missed:
        kinds[type(node).__name__] = kinds.get(type(node).__name__, 0) + 1

    assert len(broken) < len(fixed), (
        f"the .children-only traversal reached {len(broken)} of {len(fixed)} nodes "
        f"({len(broken) * 100 // len(fixed)}%), missing {len(missed)}: {kinds}"
    )
    assert kinds.get("TableCellNode") == 4, (
        f"the reproduction must show the cells being missed; missed instead: {kinds}"
    )
    # …and the figures with them — the whole point of the finding.
    assert "1,150 units" not in {plain_text(n) for n in broken}, (
        "the broken traversal must be shown REACHING the table's figures for this "
        "reproduction to be about the real defect"
    )
    assert "1,150 units" in {plain_text(n) for n in fixed}


def test_ac2_the_report_s_own_ask_end_to_end_headings_with_their_bodies():
    """AC2 / the amplifier: re-run the ask that surfaced the finding — extract each heading
    and the body beneath it — and assert the table's figures APPEAR in the extracted body.
    This is the assertion whose absence WAS the finding (an empty body for the costs section).
    """
    root = _tree(BUSINESS_CASE_DOC)
    sections, current = {}, None
    for node in walk(root):
        if isinstance(node, HeadingNode):
            current = plain_text(node)
            sections[current] = []
        elif current is not None:
            text = plain_text(node)
            if text:
                sections[current].append(text)

    body = " ".join(sections["Business Case"])
    assert body, "the heading extractor produced an EMPTY body — the reported symptom"
    for figure in ("240 units", "1,150 units"):
        assert figure in body, f"{figure!r} missing from the extracted body: {body!r}"


# --------------------------------------------------------------------------- #
# AC3 — plain_text handles EVERY Inline subclass.                               #
# --------------------------------------------------------------------------- #

#: One representative per ``Inline`` subclass, with the datum its plain text MUST carry.
#: A subclass added to the model and not added here reddens
#: :func:`test_ac3_every_inline_subclass_is_handled_and_contributes`.
INLINE_REPRESENTATIVES = {
    "Text": (Text("a literal run"), "a literal run"),
    "StyledText": (StyledText("bold words", bold=True), "bold words"),
    "MentionUser": (MentionUser("ou_exampleowner00000000000000000001"),
                    "@ou_exampleowner00000000000000000001"),
    "MentionDoc": (MentionDoc("The Spec", "https://example.larksuite.com/docx/tok"),
                   "The Spec"),
    "InlineEquation": (InlineEquation("a^2+b^2"), "a^2+b^2"),
    "RawInline": (RawInline("<u>already formatted</u>"), "<u>already formatted</u>"),
    "UnsupportedInline": (UnsupportedInline("reminder"), "reminder"),
}


def _unhandled_inline_subclasses():
    """Every ``Inline`` subclass with no representative above — the completeness guard's
    finding. Returned rather than asserted so the guard can be shown to BITE."""
    return sorted(
        cls.__name__ for cls in Inline.__subclasses__()
        if cls.__name__ not in INLINE_REPRESENTATIVES
    )


def test_ac3_every_inline_subclass_is_handled_and_contributes():
    """AC3: enumerate ``Inline.__subclasses__()`` — every one has a representative, and
    every one CONTRIBUTES its own datum to the plain text. A future inline type cannot be
    silently dropped: it is either handled here or this test names it."""
    assert not _unhandled_inline_subclasses(), (
        f"these Inline subclasses are not handled by plain_text: "
        f"{_unhandled_inline_subclasses()}"
    )
    for name, (inline, datum) in INLINE_REPRESENTATIVES.items():
        out = plain_text(inline)
        assert out, f"{name} contributed NOTHING to the plain text"
        assert datum in out, f"{name}: {datum!r} not in {out!r}"
        # …and inside a block, which is how a consumer actually meets it.
        assert datum in plain_text(TextNode(content=[Text("before "), inline])), name


def test_ac3_the_subclass_enumeration_guard_bites():
    """AC3 (the guard is not vacuous): a throwaway subclass is REPORTED as unhandled, and
    ``plain_text`` refuses it loudly rather than returning a silent empty string — the
    behavior of the one serializer this mirrors."""
    class ThrowawayInline(Inline):
        pass

    assert "ThrowawayInline" in _unhandled_inline_subclasses()
    with pytest.raises(TypeError, match="ThrowawayInline"):
        plain_text(ThrowawayInline())

    # leave the process-wide subclass registry as it was found.
    del ThrowawayInline
    gc.collect()
    assert "ThrowawayInline" not in _unhandled_inline_subclasses()


def test_ac3_all_seven_inline_kinds_in_one_block():
    """AC3 / the amplifier: a run sequence mixing ALL the inline kinds in one block —
    every datum is present, in order, and nothing is dropped between them."""
    runs = [inline for inline, _datum in INLINE_REPRESENTATIVES.values()]
    out = plain_text(TextNode(content=runs))
    position = -1
    for inline, datum in INLINE_REPRESENTATIVES.values():
        found = out.find(datum)
        assert found > position, f"{datum!r} missing or out of order in {out!r}"
        position = found


def test_ac3_plain_text_reads_a_blocks_own_text_never_its_children():
    """AC3: ``plain_text`` is the block's OWN text — ``walk`` is what descends. A container
    holding text only in its children reports ``''``, so the pair composes without
    double-counting."""
    cell = TableCellNode(children=[TextNode(content=[Text("inside")], block_id="t")])
    assert plain_text(cell) == ""
    assert "inside" in " ".join(plain_text(n) for n in walk(cell))
    # a page's own text is its title.
    assert plain_text(PageNode(title=[Text("Q3 Proposal")])) == "Q3 Proposal"


def test_ac3_plain_text_survives_the_absent_content_sentinel():
    """AC3: ``None`` content (the SDK attribute absent) is ``''``, not a crash."""
    assert plain_text(TextNode(content=None)) == ""
    assert plain_text(HeadingNode(level=2, content=None)) == ""


# --------------------------------------------------------------------------- #
# AC4 — it is NOT block_plain_text, and the two MUST DIFFER.                     #
# --------------------------------------------------------------------------- #

def _mention_only_block():
    return TextNode(content=[MentionUser("ou_examplebot0000000000000000000001")])


def _mention_plus_text_block():
    return TextNode(content=[
        MentionUser("ou_examplebot0000000000000000000001"),
        Text(" please own this"),
    ])


def _equation_bearing_block():
    return TextNode(content=[Text("we solve "), InlineEquation("a^2+b^2")])


@pytest.mark.parametrize("shape,block", [
    ("mention-only", _mention_only_block()),
    ("mention-plus-text", _mention_plus_text_block()),
    ("equation-bearing", _equation_bearing_block()),
])
def test_ac4_the_read_helper_and_the_anchor_helper_MUST_DIFFER(shape, block):
    """AC4 — the load-bearing test of this issue.

    ``write.block_plain_text`` excludes a mention on purpose: it backs anchor
    quote-matching, and an anchor must match text a user can literally quote. That contract
    is CORRECT for its purpose and must not be reused for reading, because reusing it
    re-introduces the silent-mention-drop one layer down. So the two functions differ, and
    this test is what stops a future "simplification" from merging them.
    """
    read = plain_text(block)
    anchor = block_plain_text(block)
    assert read != anchor, (
        f"{shape}: the read helper and the anchor helper agree ({read!r}) — one of them is "
        f"now wrong for its own purpose"
    )


def test_ac4_the_read_helper_includes_the_mention_the_anchor_helper_omits():
    """AC4, stated as the two contracts rather than as inequality: the read helper carries
    the mention token; the anchor helper carries none of it."""
    block = _mention_plus_text_block()
    token = "ou_examplebot0000000000000000000001"
    assert token in plain_text(block)
    assert token not in block_plain_text(block)
    # the anchor helper still sees the quotable words — it is not broken, it is different.
    assert block_plain_text(block) == " please own this"


def test_ac4_both_docstrings_cross_reference_each_other():
    """AC4: each function's docstring names the other and states the different semantics, so
    a reader who lands on either one learns there are two."""
    read, anchor = plain_text.__doc__, block_plain_text.__doc__
    assert "block_plain_text" in read, read
    assert "plain_text" in anchor and "larkdocio.model" in anchor, anchor
    for doc in (read, anchor):
        assert "mention" in doc.lower(), doc
    assert "quote" in anchor.lower(), anchor


def test_ac4_block_plain_texts_own_contract_is_unchanged():
    """AC4 / Out of Scope: ``block_plain_text`` keeps EXACTLY the semantics it had — this
    issue adds a second function, it does not retune the first."""
    assert block_plain_text(_mention_only_block()) == ""
    assert block_plain_text(TextNode(content=[Text("Revenue grew 12.4% in Q3.")])) == (
        "Revenue grew 12.4% in Q3."
    )
    assert block_plain_text(TableCellNode(children=[TextNode(content=[Text("x")])])) == ""


# --------------------------------------------------------------------------- #
# AC5 — the guide pastes the public functions; the false-docstring locals are gone.#
# --------------------------------------------------------------------------- #

def _guide_text():
    import larkdocio

    return larkdocio.guide(full=True)


def test_ac5_the_guide_defines_no_local_tree_helper_anywhere():
    """AC5: every pasted copy is DELETED. A locally-defined ``walk`` / ``text_of`` in the
    guide is the defect itself — a consumer pastes it and gets the incomplete traversal back.
    """
    import re

    text = _guide_text()
    offenders = re.findall(r"^\s*def\s+(walk|text_of)\s*\(", text, flags=re.MULTILINE)
    assert not offenders, (
        f"the guide still defines its own tree helper(s) {sorted(set(offenders))} — the "
        f"pasted copies are what silently lost a consumer's table cells and mentions"
    )


def test_ac5_every_recipe_that_walks_the_tree_imports_the_public_functions():
    """AC5: the recipes that walk a document import the public functions from
    ``larkdocio.model`` rather than re-deriving them, and **no recipe reaches for a container
    attribute by hand** — that hand-rolled lookup is exactly what missed ``cells`` and
    ``columns``.

    (A recipe may still read ``content`` off a node with ``getattr`` to reach the
    **word-level** review anchors on its runs: that is a per-run anchor lookup, not a
    traversal, and it loses nothing.)
    """
    import guide_recipes as gr

    for slug in ("read-the-comments-on-a-document",
                 "change-a-document-at-the-object-level-no-markdown-anywhere"):
        source = gr.recipe_source(slug)
        assert "from larkdocio.model import" in source, slug
        assert "walk(" in source, slug
        for attribute in ('"children"', '"cells"', '"columns"',
                          "'children'", "'cells'", "'columns'"):
            assert attribute not in source, (
                f"recipe {slug!r} still reaches for the container attribute {attribute} by "
                f"hand — that hand-rolled traversal is the defect:\n{source}"
            )
    # the recipe that needs a block's WORDS uses the shipped reduction, not its own.
    text_recipe = gr.recipe_source(
        "change-a-document-at-the-object-level-no-markdown-anywhere")
    assert "plain_text(" in text_recipe, text_recipe


def test_ac5_the_public_functions_do_what_the_recipes_claim_on_the_recipes_own_fixture():
    """AC5: the imported functions are the ones under test above — asserted on the same
    document the guide's harness serves, so the recipe's claim and this file's tests are about
    one behavior."""
    import guide_recipes as gr

    root = _tree(gr.fixture_block_dicts("doctok"), doc_id="doctok")
    texts = [plain_text(n) for n in walk(root)]
    assert "Revenue grew 12.4% in Q3." in texts
    assert "Overview" in texts


# --------------------------------------------------------------------------- #
# AC6 — the guide names the node model.                                          #
# --------------------------------------------------------------------------- #

def test_ac6_the_guide_names_the_node_model_and_answers_the_heading_question():
    """AC6: the guide points at ``larkdocio.model.nodes`` and answers "which node is a
    heading, at what level" with a real ``isinstance`` example. Verified at mint: the count of
    these terms in the shipped guide was ZERO, so a consumer could not discover the typed
    alternative that avoids both silent losses."""
    text = _guide_text()
    for term in ("larkdocio.model.nodes", "HeadingNode", "isinstance", ".level"):
        assert term in text, f"the guide never names {term!r}"
    # the answer must be in ONE place a reader lands on, not scattered.
    section = text.split("### The tree's own types", 1)
    assert len(section) == 2, "the guide has no node-model subsection"
    body = section[1].split("\n## ", 1)[0]
    for term in ("HeadingNode", "isinstance", "level", "larkdocio.model.nodes"):
        assert term in body, f"the node-model subsection never names {term!r}"


def test_ac6_the_node_model_example_RUNS_as_pasted_and_prints_the_heading_level():
    """AC6: the subsection's example is EXECUTED, in a builtins-only namespace, exactly as a
    consumer's file runs it — and its output is checked. The whole finding was a pasted helper
    that ran fine and returned the wrong thing, so "it compiles" is not the bar."""
    import builtins
    import io
    import re
    from contextlib import redirect_stdout

    body = _guide_text().split("### The tree's own types", 1)[1].split("\n## ", 1)[0]
    blocks = re.findall(r"```python\n(.*?)```", body, flags=re.DOTALL)
    assert len(blocks) == 1, f"the subsection must carry exactly one example; found {len(blocks)}"

    namespace = {"__builtins__": builtins, "__name__": "guide_node_model_example"}
    out = io.StringIO()
    with redirect_stdout(out):
        exec(compile(blocks[0], "<guide: the tree's own types>", "exec"), namespace)
    printed = out.getvalue()
    assert "heading 2 Business Case" in printed, printed
    assert "Revenue grew 12.4% in Q3." in printed, printed


def test_ac6_the_node_model_pointer_is_honest_the_types_it_names_exist():
    """AC6: every node class the new subsection names is a real exported model type — a
    pointer to a type that does not exist is worse than no pointer."""
    import re

    import larkdocio.model as model

    body = _guide_text().split("### The tree's own types", 1)[1].split("\n## ", 1)[0]
    named = sorted(set(re.findall(r"\b([A-Z][A-Za-z]*Node)\b", body)))
    assert named, "the subsection names no node type at all"
    for name in named:
        assert hasattr(model, name), f"the guide names {name}, which the model does not export"


# --------------------------------------------------------------------------- #
# AC7 — the truth rows: the helpers are in capabilities().                        #
# --------------------------------------------------------------------------- #

def test_ac7_capabilities_names_the_two_tree_helpers():
    """AC7: the discovery registry reports the helpers, so a consumer reading
    ``capabilities()`` rather than the guide still finds them."""
    from larkdocio import capabilities

    ops = {op["name"]: op for op in capabilities(full=True)["surfaces"]["docx-read"]["operations"]}
    for name in ("walk", "plain_text"):
        assert name in ops, f"capabilities() docx-read does not report {name!r}"
        assert ops[name]["projected_from"] == "larkdocio.model.tree"


def test_ac7_the_helpers_are_documented_where_a_consumer_lands():
    """AC7: ``help(larkdocio.model)`` names both, so the pair is discoverable without the
    guide at all."""
    import larkdocio.model as model

    assert "walk" in model.__all__ and "plain_text" in model.__all__
    assert "walk" in model.__doc__ and "plain_text" in model.__doc__


# --------------------------------------------------------------------------- #
# LD-567 — the primary reading recipe stops teaching the empty branch, its       #
# stand-in tree exercises the branch it shows, and the container rule is a      #
# runtime projection of plain_text's own docstring, adjacent to the example.    #
# --------------------------------------------------------------------------- #

def _tree_types_body():
    return _guide_text().split("### The tree's own types", 1)[1].split("\n## ", 1)[0]


def _tree_types_python_block():
    import re

    blocks = re.findall(r"```python\n(.*?)```", _tree_types_body(), flags=re.DOTALL)
    assert len(blocks) == 1, (
        f"the subsection must carry exactly one example; found {len(blocks)}"
    )
    return blocks[0]


def test_ld567_ac2_the_stand_in_tree_carries_a_table_and_a_cell():
    """AC2: the recipe's own stand-in tree gains a table (and a cell), so the printed snippet
    exercises the branch it shows rather than a tree that never reaches it."""
    source = _tree_types_python_block()
    assert "TableNode" in source, "the stand-in tree still has no table"
    assert "TableCellNode" in source, "the stand-in tree still has no cell"


def test_ld567_ac1_ac2_the_example_RUNS_and_demonstrates_the_rule_not_just_the_heading():
    """AC1 + AC2, proven by RUNNING the snippet exactly as pasted (the whole finding was a
    pasted example that ran fine and printed the wrong thing).

    The table and cell branches must NOT present an empty `plain_text()` result as if it were
    real content (AC1) — and the actual words inside the cell, reached by `walk` descending
    into it, must be printed by the very same loop (AC2), proving the composition rather than
    hiding it."""
    import builtins
    import io
    from contextlib import redirect_stdout

    source = _tree_types_python_block()
    namespace = {"__builtins__": builtins, "__name__": "guide_node_model_example"}
    out = io.StringIO()
    with redirect_stdout(out):
        exec(compile(source, "<guide: the tree's own types>", "exec"), namespace)
    printed = out.getvalue()

    assert "heading 2 Business Case" in printed, printed
    assert "Revenue grew 12.4% in Q3." in printed, printed
    # The container's OWN reduction is empty — and the snippet says so, rather than printing
    # a bare "" that looks like the table/cell's real content (AC1).
    for label in ("table", "cell"):
        line = next(ln for ln in printed.splitlines() if ln.startswith(label))
        assert line != f"{label} ", f"{label!r} branch prints a bare empty result: {line!r}"
        assert "empty" in line, f"{label!r} branch does not explain why it is empty: {line!r}"
    # The cell's own child (reached by walk descending into it, per AC2) carries the real
    # words — proving the correct composition, not merely a comment claiming one.
    assert "Q3 revenue: 12.4%" in printed, printed


def test_ld567_ac3_the_container_rule_is_a_projection_of_plain_texts_docstring():
    """AC3: the guide's container-rule wording is a runtime PROJECTION of
    ``larkdocio.model.plain_text.__doc__`` — never a sentence retyped a second (or third) time
    in this test file. Only short LOCATOR anchors are typed here, exactly the way
    ``guide_recipes.recipe_preamble`` locates a heading by a short slug rather than by copying
    the heading's prose."""
    from doc_prose import prose

    from larkdocio.model import plain_text

    doc = plain_text.__doc__
    start = doc.index("Never its child blocks")
    end_marker = '``""``'
    end = doc.index(end_marker, start) + len(end_marker)
    projected = prose(doc[start:end])

    body = _tree_types_body()
    assert projected in prose(body), (
        "the guide's container rule has drifted from plain_text's own docstring — it must be "
        "a projection, not a paraphrase"
    )


def test_ld567_ac3_the_rule_and_the_example_are_adjacent():
    """AC3: the rule sits WHERE the example is, not many lines above it — the projected quote
    (located by its own short anchor) must appear within a short distance, in characters, of
    the fenced code block it explains."""
    body = _tree_types_body()
    fence_end = body.index("```", body.index("```python") + 1) + len("```")
    rule_start = body.index("Never its child blocks")
    assert 0 <= rule_start - fence_end < 400, (
        f"the container rule sits {rule_start - fence_end} characters after the example — "
        f"AC3 requires it adjacent, not stated far above or below"
    )


