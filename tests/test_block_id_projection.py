"""The opt-in block-identity projection (LD-230).

The projection is the reader's own Markdown plus one ``<!-- lark:block:<id> -->`` marker
per block-level node, rendered with literal text escaped so a document's own
marker-shaped prose cannot forge one, and returned together with the authoritative list
of identifiers it emitted.

The corpora here are built in this module on purpose. The prototype that measured marker
survival lives under ``dev/marker-preservation-probes/`` and is a BLUEPRINT, never an
import: nothing in ``src/`` or ``tests/`` depends on it.
"""
import difflib
import json
import re

import pytest

from harness import FIXTURES_DIR, build_blocks

from larkdocio.errors import LarkEscapeError
from larkdocio.model import (
    BlockIdProjection,
    MarkdownRenderer,
    Text,
    TextNode,
    block_id_marker,
    project_block_ids,
    strip_block_id_markers,
    unescape_literals,
    walk,
)
from larkdocio.model.renderer import _escape_literals
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser

# The test's OWN reader of the projected text. The library deliberately does not ship
# one: the emitted-identifier list is authoritative and a caller that re-derives it by
# pattern is exactly the failure mode the list exists to prevent. Here it is the
# independent second opinion the assertions compare against.
#
# LD-231 extended the shipped form with an OPTIONAL ``opaque=<kind>`` attribute for a
# block the projection conserves rather than invites an edit to (the conservation
# contract; see ``tests/test_opaque_marker_conservation.py``). The attribute is optional
# here for the same reason it is optional there: one grammar, so a reader of markers
# keeps working across both forms. Group 1 is still the identifier — every assertion
# below is unchanged.
_MARKER_LINE = re.compile(r"^[ \t>]*<!-- lark:block:(\S+)(?: opaque=\S+)? -->$")


def _marker_ids_in(text):
    return [
        m.group(1)
        for m in (_MARKER_LINE.match(line) for line in text.split("\n"))
        if m
    ]


# --------------------------------------------------------------------------- #
# Corpora.                                                                      #
# --------------------------------------------------------------------------- #

def _tree(block_dicts, doc_id=None):
    blocks = build_blocks(block_dicts)
    return Parser(Config()).parse_docx_tree(doc_id or block_dicts[0]["block_id"], blocks)


def _text(bid, parent, content, children=()):
    return {
        "block_id": bid, "parent_id": parent, "block_type": 2,
        "text": {"elements": [{"text_run": {"content": content}}]},
        "children": list(children),
    }


def _bullet(bid, parent, content, children=()):
    return {
        "block_id": bid, "parent_id": parent, "block_type": 12,
        "bullet": {"elements": [{"text_run": {"content": content}}]},
        "children": list(children),
    }


#: The deepest structure the reader emits, in one document: a heading with children, a
#: three-deep bullet list whose deepest item carries block-level breakout children (a
#: code fence and a quote), a quote container, a callout wrapping a list, a table, and an
#: image. Nesting was explicitly NOT probed before this issue, so the corpus is built to
#: be the hard case rather than a representative one.
NESTED_CORPUS = [
    {"block_id": "root", "parent_id": "", "block_type": 1,
     "page": {"elements": [{"text_run": {"content": "Deep Doc"}}]},
     "children": ["h1", "b0", "qc", "co", "tb", "im"]},
    {"block_id": "h1", "parent_id": "root", "block_type": 3,
     "heading1": {"elements": [{"text_run": {"content": "Findings"}}]},
     "children": ["hp"]},
    _text("hp", "h1", "Under the heading."),
    _bullet("b0", "root", "Top item", ["b1"]),
    _bullet("b1", "b0", "Nested item", ["b2"]),
    _bullet("b2", "b1", "Deepest item", ["cd", "qt", "b2p"]),
    {"block_id": "cd", "parent_id": "b2", "block_type": 14,
     "code": {"elements": [{"text_run": {"content": "deep_code()"}}], "style": {"language": 49}},
     "children": []},
    {"block_id": "qt", "parent_id": "b2", "block_type": 15,
     "quote": {"elements": [{"text_run": {"content": "deep quote"}}]},
     "children": []},
    _text("b2p", "b2", "A paragraph under the deepest item."),
    {"block_id": "qc", "parent_id": "root", "block_type": 34,
     "quote_container": {}, "children": ["qc1", "qc2"]},
    _text("qc1", "qc", "First quoted line."),
    _text("qc2", "qc", "Second quoted line."),
    {"block_id": "co", "parent_id": "root", "block_type": 19,
     "callout": {}, "children": ["cob"]},
    _bullet("cob", "co", "A bullet inside a callout"),
    {"block_id": "tb", "parent_id": "root", "block_type": 31,
     "table": {"property": {"row_size": 2, "column_size": 2}},
     "children": ["c00", "c01", "c10", "c11"]},
    {"block_id": "c00", "parent_id": "tb", "block_type": 32, "table_cell": {},
     "children": ["c00t"]},
    _text("c00t", "c00", "Head A"),
    {"block_id": "c01", "parent_id": "tb", "block_type": 32, "table_cell": {},
     "children": ["c01t"]},
    _text("c01t", "c01", "Head B"),
    {"block_id": "c10", "parent_id": "tb", "block_type": 32, "table_cell": {},
     "children": ["c10t"]},
    _text("c10t", "c10", "Cell A"),
    {"block_id": "c11", "parent_id": "tb", "block_type": 32, "table_cell": {},
     "children": ["c11t"]},
    _text("c11t", "c11", "Cell B"),
    {"block_id": "im", "parent_id": "root", "block_type": 27,
     "image": {"token": "img_tok_1"}, "children": []},
]

#: A document whose own prose is marker-shaped, plus the metacharacter cases the escape
#: policy exists for. The marker-shaped paragraph names an identifier this document does
#: NOT contain, which is the ordinary case: a consumer writing about markers.
ADVERSARIAL_CORPUS = [
    {"block_id": "root", "parent_id": "", "block_type": 1,
     "page": {"elements": [{"text_run": {"content": "Marker probe"}}]},
     "children": ["p1", "p2", "p3", "p4"]},
    _text("p1", "root", "The uptime was 99.9 percent."),
    _text("p2", "root", "# not a heading * not emphasis _not italic_ 2 < 3"),
    _text("p3", "root", "A consumer's own comment: <!-- reviewer: check this -->"),
    _text("p4", "root", "<!-- lark:block:doxcnNotInThisDoc -->"),
]

#: The worst case: prose spelling a REAL emitted identifier in the exact marker shape.
#: Under the projection's pinned escaping policy it cannot forge; with escaping OFF it
#: is byte-indistinguishable from the real marker, and that is precisely the hazard the
#: policy is pinned against.
FORGERY_CORPUS = [
    {"block_id": "root", "parent_id": "", "block_type": 1,
     "page": {"elements": [{"text_run": {"content": "Forgery probe"}}]},
     "children": ["p1", "p2"]},
    _text("p1", "root", "The uptime was 99.9 percent."),
    _text("p2", "root", "<!-- lark:block:p1 -->"),
]

#: Text the escape policy must round-trip exactly: literal backslashes, escaped
#: metacharacters, a line that is nothing but escapes, both line endings, and the
#: verbatim body of a code fence.
DECODE_CORPUS = [
    "",
    "plain text with no metacharacters",
    "The uptime was 99.9 percent.",
    "a literal backslash: \\",
    "a literal backslash before a dot: \\.",
    "two literal backslashes: \\\\",
    "\\*not emphasis\\*",
    "*_`#[]()!|><~+-.{}",
    "# not a heading * not emphasis _not italic_ 2 < 3",
    "<!-- lark:block:doxcnAbC123 -->",
    "line one\nline two",
    "line one\r\nline two",
    "trailing newline\n",
    "\r\n",
    "def f(x):\n    return x * 2  # doubles\n",
    "if a < b and c > d:\n\treturn [a, b](c)\n",
    "中文段落，含标点。",
]


def _fixture_trees():
    for path in sorted(FIXTURES_DIR.glob("*.input.json")):
        block_dicts = json.loads(path.read_text(encoding="utf-8"))
        yield path.name[: -len(".input.json")], _tree(block_dicts)


FIXTURE_TREES = list(_fixture_trees())
FIXTURE_IDS = [name for name, _ in FIXTURE_TREES]


def _projection_at(tree, escape_literals):
    """Project ``tree`` at an explicit escaping policy (the shipped one pins True)."""
    renderer = MarkdownRenderer(escape_literals=escape_literals, emit_block_ids=True)
    markdown = renderer.render(tree)
    return markdown, tuple(renderer.emitted_block_ids)


# --------------------------------------------------------------------------- #
# AC1 — one marker per block-level node, none for inline.                       #
# --------------------------------------------------------------------------- #

def test_ac1_every_content_bearing_block_node_carries_exactly_one_marker():
    tree = _tree(NESTED_CORPUS)
    projection = project_block_ids(tree)
    emitted = list(projection.block_ids)

    # No identifier twice, and every one of them belongs to a real block node.
    assert len(emitted) == len(set(emitted)), "an identifier was emitted more than once"
    tree_ids = {node.block_id for node in walk(tree) if node.block_id}
    assert set(emitted) <= tree_ids

    # Each is in the text exactly once, on its own line.
    assert _marker_ids_in(projection.markdown) == emitted

    # Every block-level node the reader renders content for is covered — the page root,
    # a heading, three list depths, a code fence, a quote, a quote container, a callout,
    # the table BLOCK and an image.
    for block_id in ("root", "h1", "hp", "b0", "b1", "b2", "cd", "qt", "b2p",
                     "qc", "qc1", "qc2", "co", "cob", "tb", "im"):
        assert block_id in emitted, f"no marker for block {block_id}"


def test_ac1_inline_nodes_have_no_identifier_to_project():
    # An identifier is a block-level fact; the inline classes do not carry the field at
    # all, so "no marker for an inline node" is structural rather than a filter.
    assert not hasattr(Text("x"), "block_id")


def test_ac1_a_table_cell_gets_no_marker_but_the_table_block_does():
    tree = _tree(NESTED_CORPUS)
    emitted = set(project_block_ids(tree).block_ids)
    assert "tb" in emitted
    for cell_id in ("c00", "c01", "c10", "c11", "c00t", "c01t", "c10t", "c11t"):
        assert cell_id not in emitted, (
            f"{cell_id} is inside a table cell, where a marker line cannot be expressed"
        )


# --------------------------------------------------------------------------- #
# AC2 — default output is byte-identical (the hard one).                        #
# --------------------------------------------------------------------------- #

def test_ac2_the_projection_is_off_by_default():
    assert MarkdownRenderer().emit_block_ids is False
    assert MarkdownRenderer().emitted_block_ids == []


@pytest.mark.parametrize("name,tree", FIXTURE_TREES, ids=FIXTURE_IDS)
def test_ac2_default_render_carries_no_marker_over_the_whole_corpus(name, tree):
    out = MarkdownRenderer().render(tree)
    assert "lark:block:" not in out
    assert MarkdownRenderer().emitted_block_ids == []


def test_ac2_the_default_read_path_is_untouched():
    blocks = build_blocks(NESTED_CORPUS)
    parser = Parser(Config())
    assert parser.renderer.emit_block_ids is False
    markdown = parser.parse_docx_content("root", blocks)
    assert "lark:block:" not in markdown
    assert markdown == MarkdownRenderer().render(_tree(NESTED_CORPUS))


# --------------------------------------------------------------------------- #
# AC3 — one documented byte form, and nothing else is one.                      #
# --------------------------------------------------------------------------- #

def test_ac3_the_marker_byte_form_is_pinned():
    assert block_id_marker("doxcnAbC123") == "<!-- lark:block:doxcnAbC123 -->"


def test_ac3_the_marker_sits_alone_on_the_line_before_its_block():
    tree = _tree(NESTED_CORPUS)
    lines = project_block_ids(tree).markdown.split("\n")
    index = lines.index("<!-- lark:block:h1 -->")
    assert lines[index + 1] == "# Findings"


def test_ac3_a_consumers_own_html_comment_is_not_a_marker():
    tree = _tree(ADVERSARIAL_CORPUS)
    projection = project_block_ids(tree)
    assert "reviewer" not in " ".join(projection.block_ids)
    for line in projection.markdown.split("\n"):
        if "reviewer" in line:
            assert not _MARKER_LINE.match(line)


# --------------------------------------------------------------------------- #
# AC4 — each marker parses as ONE opaque token, in document order.              #
# --------------------------------------------------------------------------- #

def _dialect_parser():
    """The reader's OWN dialect parser, built the way ``compose`` builds it."""
    from markdown_it import MarkdownIt

    from larkdocio.write.compose import (
        _DIALECT_EXTENSIONS, _DIALECT_PRESET, _MAX_NESTING,
    )

    md = MarkdownIt(_DIALECT_PRESET, {"maxNesting": _MAX_NESTING})
    for extension in _DIALECT_EXTENSIONS:
        md = md.enable(extension)
    return md


@pytest.mark.parametrize("corpus", [NESTED_CORPUS, ADVERSARIAL_CORPUS, FORGERY_CORPUS],
                         ids=["nested", "adversarial", "forgery"])
def test_ac4_each_marker_is_one_html_block_token_carrying_nothing_else(corpus):
    projection = project_block_ids(_tree(corpus))
    tokens = _dialect_parser().parse(projection.markdown)

    seen = []
    for token in tokens:
        lines = (token.content or "").split("\n")
        matches = [m for m in (_MARKER_LINE.match(ln) for ln in lines) if m]
        if not matches:
            continue
        assert token.type == "html_block", (
            f"a marker parsed as {token.type}, not one opaque html_block"
        )
        assert len(matches) == 1 and (token.content or "").rstrip("\n") == lines[0], (
            f"document text was swept into the marker token: {token.content!r}"
        )
        seen.extend(m.group(1) for m in matches)

    assert seen == list(projection.block_ids)


# --------------------------------------------------------------------------- #
# AC5 — additive only, asserted AT THE SAME escaping policy.                    #
# --------------------------------------------------------------------------- #

def _assert_additive(tree, escape_literals):
    markdown, ids = _projection_at(tree, escape_literals)
    plain = MarkdownRenderer(escape_literals=escape_literals).render(tree)
    assert strip_block_id_markers(markdown, ids) == plain

    opcodes = difflib.SequenceMatcher(
        None, plain.split("\n"), markdown.split("\n"), autojunk=False
    ).get_opcodes()
    kinds = {tag for tag, *_ in opcodes}
    assert kinds <= {"equal", "insert"}, f"the projection modified lines: {opcodes}"


@pytest.mark.parametrize("escape_literals", [True, False], ids=["escaped", "raw"])
@pytest.mark.parametrize("corpus", [NESTED_CORPUS, ADVERSARIAL_CORPUS],
                         ids=["nested", "adversarial"])
def test_ac5_strip_equals_render_at_the_same_policy(corpus, escape_literals):
    _assert_additive(_tree(corpus), escape_literals)


@pytest.mark.parametrize("name,tree", FIXTURE_TREES, ids=FIXTURE_IDS)
@pytest.mark.parametrize("escape_literals", [True, False], ids=["escaped", "raw"])
def test_ac5_additive_over_the_whole_shipped_corpus(name, tree, escape_literals):
    _assert_additive(tree, escape_literals)


# --------------------------------------------------------------------------- #
# AC6 — the escaping policy is pinned, and the hazard it removes is pinned too. #
# --------------------------------------------------------------------------- #

def test_ac6_the_projection_renders_with_literals_escaped():
    projection = project_block_ids(_tree(FORGERY_CORPUS))
    assert "The uptime was 99\\.9 percent\\." in projection.markdown
    assert "\\<\\!\\-\\- lark:block:p1 \\-\\-\\>" in projection.markdown
    # Escaped, the document's own marker-shaped prose is not a marker line: the real
    # marker for p1 is the only one.
    assert "p1" in projection.block_ids
    assert _marker_ids_in(projection.markdown).count("p1") == 1


def test_ac6_the_same_text_WOULD_forge_a_marker_with_escaping_off():
    tree = _tree(FORGERY_CORPUS)
    raw, ids = _projection_at(tree, escape_literals=False)
    # Two "markers" for p1 now: the real one, and the paragraph that merely says so.
    assert list(ids).count("p1") == 1
    assert _marker_ids_in(raw).count("p1") == 2, (
        "with escaping off a document's own prose is byte-indistinguishable from a "
        "marker — this is the hazard the pinned policy removes"
    )


def test_ac6_a_forged_marker_survives_the_round_trip_under_the_pinned_policy():
    # The same document that is unsafe with escaping off is safe with it on: escaped,
    # the prose is not a marker line, so the strip leaves it alone.
    tree = _tree(FORGERY_CORPUS)
    projection = project_block_ids(tree)
    restored = strip_block_id_markers(projection.markdown, projection.block_ids)
    assert restored == MarkdownRenderer(escape_literals=True).render(tree)


# --------------------------------------------------------------------------- #
# AC7 — the emitted identifier list is part of the result.                      #
# --------------------------------------------------------------------------- #

def test_ac7_the_result_carries_the_emitted_identifiers_in_document_order():
    projection = project_block_ids(_tree(NESTED_CORPUS))
    assert isinstance(projection, BlockIdProjection)
    assert isinstance(projection.block_ids, tuple)
    assert all(isinstance(bid, str) for bid in projection.block_ids)
    assert projection.block_ids[0] == "root", "the page root comes first"
    assert list(projection.block_ids) == _marker_ids_in(projection.markdown)


def test_ac7_the_result_is_json_serializable():
    projection = project_block_ids(_tree(NESTED_CORPUS))
    revived = json.loads(json.dumps(projection.to_dict()))
    assert revived["markdown"] == projection.markdown
    assert revived["block_ids"] == list(projection.block_ids)


def test_ac7_document_order_puts_a_parent_before_its_children():
    order = list(project_block_ids(_tree(NESTED_CORPUS)).block_ids)
    assert order.index("b0") < order.index("b1") < order.index("b2")
    assert order.index("h1") < order.index("hp")
    assert order.index("qc") < order.index("qc1") < order.index("qc2")


# --------------------------------------------------------------------------- #
# AC8 — the strip is marker-SET-aware, so adversarial content survives.         #
# --------------------------------------------------------------------------- #

def test_ac8_marker_shaped_content_survives_project_then_strip():
    tree = _tree(ADVERSARIAL_CORPUS)
    projection = project_block_ids(tree)
    restored = strip_block_id_markers(projection.markdown, projection.block_ids)
    assert restored == MarkdownRenderer(escape_literals=True).render(tree)
    assert "lark:block:doxcnNotInThisDoc" in restored, (
        "the document's own prose was deleted"
    )


def test_ac8_a_naive_line_strip_destroys_what_the_set_aware_strip_keeps():
    tree = _tree(ADVERSARIAL_CORPUS)
    raw, ids = _projection_at(tree, escape_literals=False)

    set_aware = strip_block_id_markers(raw, ids)
    assert set_aware == MarkdownRenderer(escape_literals=False).render(tree)

    naive = "".join(
        line for line in raw.splitlines(keepends=True)
        if not _MARKER_LINE.match(line.rstrip("\n"))
    )
    assert naive != set_aware, "the set-awareness has to make a difference to matter"
    assert "lark:block:doxcnNotInThisDoc" not in naive, (
        "a strip that removes anything marker-shaped deletes the document's own prose"
    )


def test_ac8_an_identifier_that_was_never_emitted_is_left_alone():
    text = "<!-- lark:block:REAL -->\nkept\n<!-- lark:block:FORGED -->\nalso kept\n"
    assert strip_block_id_markers(text, ["REAL"]) == (
        "kept\n<!-- lark:block:FORGED -->\nalso kept\n"
    )


# --------------------------------------------------------------------------- #
# AC9 — the decode is the exact inverse, and refuses when ambiguous.            #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("original", DECODE_CORPUS)
def test_ac9_decode_inverts_the_escaper_exactly(original):
    assert unescape_literals(_escape_literals(original)) == original


@pytest.mark.parametrize("original", DECODE_CORPUS)
def test_ac9_decode_inverts_a_projected_paragraph_end_to_end(original):
    if not original.strip():
        pytest.skip("an empty paragraph renders no content to decode")
    node = TextNode(content=[Text(original)], block_id="p")
    rendered = MarkdownRenderer(escape_literals=True).render(node)
    assert unescape_literals(rendered) == original + "\n"


@pytest.mark.parametrize("undecodable", ["a\\", "\\", "a\\x", "\\ ", "\\\n", "x\\\\\\y"])
def test_ac9_an_ambiguous_sequence_refuses_rather_than_guessing(undecodable):
    with pytest.raises(LarkEscapeError) as excinfo:
        unescape_literals(undecodable)
    assert excinfo.value.detail
    assert "backslash" in excinfo.value.detail


def test_ac9_the_refusal_detail_names_the_position():
    with pytest.raises(LarkEscapeError) as excinfo:
        unescape_literals("abc\\x")
    assert "position 3" in excinfo.value.detail


def test_ac9_the_decode_lives_next_to_the_escaper_it_inverts():
    # One module, so the codec cannot drift apart half at a time.
    assert unescape_literals.__module__ == _escape_literals.__module__
    assert unescape_literals.__module__ == "larkdocio.model.renderer"


# --------------------------------------------------------------------------- #
# AC10 — nesting and the indentation contract.                                  #
# --------------------------------------------------------------------------- #

def test_ac10_a_nested_marker_sits_at_the_indentation_of_the_block_it_introduces():
    lines = project_block_ids(_tree(NESTED_CORPUS)).markdown.split("\n")
    for block_id, indent in (("b0", ""), ("b1", "\t"), ("b2", "\t\t")):
        marker = f"{indent}<!-- lark:block:{block_id} -->"
        assert marker in lines, f"no marker at the right indent for {block_id}"
        assert lines[lines.index(marker) + 1].startswith(f"{indent}- ")


def test_ac10_a_marker_inside_a_quote_or_callout_takes_that_prefix():
    markdown = project_block_ids(_tree(NESTED_CORPUS)).markdown
    assert "> <!-- lark:block:qc1 -->" in markdown
    assert "> <!-- lark:block:cob -->" in markdown


def test_ac10_the_deep_list_still_parses_as_a_list():
    projection = project_block_ids(_tree(NESTED_CORPUS))
    types = [t.type for t in _dialect_parser().parse(projection.markdown)]
    assert types.count("bullet_list_open") >= 3, (
        "a marker broke the list out of its own nesting"
    )
    assert "code_block" not in types, (
        "an indented line was swallowed as an indented code block"
    )


# --------------------------------------------------------------------------- #
# AC11 — determinism.                                                           #
# --------------------------------------------------------------------------- #

def test_ac11_two_projections_of_the_same_document_are_byte_identical():
    first = project_block_ids(_tree(NESTED_CORPUS))
    second = project_block_ids(_tree(NESTED_CORPUS))
    assert first.markdown == second.markdown
    assert first.block_ids == second.block_ids


def test_ac11_a_second_render_on_a_fresh_renderer_repeats_the_identifier_list():
    tree = _tree(NESTED_CORPUS)
    assert _projection_at(tree, True) == _projection_at(tree, True)


# --------------------------------------------------------------------------- #
# AC12 — the capability is reported, and no permission moved.                   #
# --------------------------------------------------------------------------- #

def test_ac12_the_projection_is_reported_as_a_reader_operation():
    from larkdocio import capabilities

    ops = capabilities(full=True)["surfaces"]["docx-read"]["operations"]
    row = next((op for op in ops if op["name"] == "project_block_ids"), None)
    assert row is not None, "the projection is not discoverable from capabilities()"
    assert row["projected_from"] == "larkdocio.model.projection"


def test_ac12_the_projection_needs_no_permission():
    from larkdocio import capabilities

    ops = capabilities(full=True)["surfaces"]["docx-read"]["operations"]
    row = next(op for op in ops if op["name"] == "project_block_ids")
    assert row["permissions"]["endpoints"] == []
    assert row["permissions"]["scopes"] == []
