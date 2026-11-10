"""LD-454 — ONE escaping policy, applied by BOTH directions of the reconcile round trip.

The projection escapes literal text (``--`` → ``\\-\\-``) so a document's own
marker-shaped prose cannot forge an identity marker. Every escape it writes has to be
undone again on the way back, or a line the caller never touched is written to Lark in its
**escaped** form as authored intent — silent corruption of untouched content, reached
through the guide's own copy-this recipe.

**Where the asymmetry was.** The dialect's own parser undoes the escaping for free
everywhere it processes backslash escapes — a paragraph, a list item, a quote, a heading, a
table cell. It does **not** in a **verbatim** context: inside a fenced code block a
backslash is a backslash, to markdown-it and to CommonMark itself. So the compiler took the
segment's raw Markdown, composed it, and shipped a code block's escaped body to Lark
verbatim, while the plan's own comparison had been made in the decoded domain all along.

The property pinned here is the one the round trip actually promises: **project → edit ONE
line → reconcile → compile, and every line the caller did not touch is byte-identical to
the block's original text.** Table-driven over the measured shape (a fenced code block
containing ``--``) and over every literal class the projection escapes, and across the
block kinds and the request families the reconciler emits.
"""
import pytest

from harness import build_blocks

from larkdocio.model import project_block_ids
from larkdocio.model.renderer import _ESCAPABLE, _escape_literals
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write.compiler import VERBATIM_KINDS, compile_reconciliation
from larkdocio.write.model import EditRequest, InsertRequest
from larkdocio.write.preview import dry_run
from larkdocio.write.reconcile import reconcile

REVISION = 7


# --------------------------------------------------------------------------- #
# Fixtures — a REAL tree, projected by the shipped projection.                 #
#                                                                              #
# The escaping under test has to be the reader's own, not a plausible-looking   #
# spelling of it: a hand-written "\\-\\-" would prove the test agrees with      #
# itself. So every case here starts from block payloads and goes through        #
# ``project_block_ids``.                                                        #
# --------------------------------------------------------------------------- #

def _code(bid, parent, content, lang=49):
    return {"block_id": bid, "parent_id": parent, "block_type": 14,
            "code": {"elements": [{"text_run": {"content": content}}],
                     "style": {"language": lang}},
            "children": []}


def _text(bid, parent, content, block_type=2, key="text"):
    return {"block_id": bid, "parent_id": parent, "block_type": block_type,
            key: {"elements": [{"text_run": {"content": content}}]},
            "children": []}


def _document(*body_blocks):
    """A page with ``body_blocks`` under it, parsed into the reader's own node tree."""
    ids = [b["block_id"] for b in body_blocks]
    blocks = [{"block_id": "root", "parent_id": "", "block_type": 1,
               "page": {"elements": [{"text_run": {"content": "Runbook"}}]},
               "children": ids}] + list(body_blocks)
    return Parser(Config()).parse_docx_tree("root", build_blocks(blocks))


def _round_trip(tree, old, new):
    """``(projection, plan, requests)`` for an edit that replaces ``old`` with ``new``.

    The edit is made on the projection's own text the way the copy-this recipe instructs —
    a caller rewriting one line of what they were handed.
    """
    projection = project_block_ids(tree)
    assert old in projection.markdown, (old, projection.markdown)
    plan = reconcile(projection, projection.markdown.replace(old, new))
    assert plan.ok, [r.detail for r in plan.refusals]
    return projection, plan, compile_reconciliation(plan, projection)


def _projected_body(*body_blocks):
    """What the PROJECTION reads for ``body_blocks``, markers stripped.

    The domain the copy-this recipe hands an editor: structure raw, literal text escaped.
    Produced by the shipped projection rather than by escaping a hand-written fragment
    whole — blanket-escaping markup destroys the structure and would test a paragraph.
    """
    from larkdocio.model import strip_block_id_markers

    projection = project_block_ids(_document(*body_blocks))
    markdown = strip_block_id_markers(projection.markdown, projection.block_ids)
    return markdown.split("# Runbook", 1)[1].strip("\n")


def _replacement(requests):
    edits = [r for r in requests if isinstance(r, EditRequest)]
    assert len(edits) == 1, requests
    return edits[0].replacement


# --------------------------------------------------------------------------- #
# AC1 — one policy, stated once; the two decode call sites are ONE function.   #
# --------------------------------------------------------------------------- #

def test_ac1_the_two_decode_import_sites_are_the_same_function():
    """``model.projection`` and ``model.renderer`` both export ``unescape_literals`` —
    and the question this bug forces is whether that is two inverses or one. It is one:
    the projection **re-exports** the renderer's, which is where the escaper lives. A
    second, independently-written inverse is exactly what would let the two halves of the
    codec drift, so this is pinned by identity rather than by behaviour."""
    import importlib

    renderer_module = importlib.import_module("larkdocio.model.renderer")
    one = renderer_module.unescape_literals
    for name in ("larkdocio.model.projection",
                 "larkdocio.write.reconcile",
                 "larkdocio.write.compiler"):
        assert importlib.import_module(name).unescape_literals is one, name


def test_ac1_the_verbatim_kinds_are_named_once_and_are_the_dialects_own():
    """The policy's one moving part: which composed kinds the dialect will NOT decode for
    us. It is the fenced code block, and the set is named rather than open-coded at each
    call site."""
    from larkdocio.write.model import NewBlockKind

    assert VERBATIM_KINDS == frozenset({NewBlockKind.CODE})


# --------------------------------------------------------------------------- #
# AC2 — the round-trip identity property, table-driven.                        #
# --------------------------------------------------------------------------- #

#: The measured shape from the field report (dogfood round 4, run D2-opus-high) plus one
#: line per literal class the projection escapes — a class that stops decoding is a class
#: that starts corrupting runbooks.
LITERAL_LINES = [
    pytest.param("deploy rollback --service $SERVICE", id="the-measured-shape"),
] + [
    pytest.param(f"literal {ch} here", id=f"escapable-{ord(ch):02x}")
    for ch in _ESCAPABLE
]


@pytest.mark.parametrize("untouched", LITERAL_LINES)
def test_ac2_an_untouched_code_line_is_byte_identical_after_the_round_trip(untouched):
    original = f"{untouched}\necho done"
    tree = _document(_code("cd", "root", original))
    _p, _plan, requests = _round_trip(tree, "echo done", "echo finished")

    assert _replacement(requests) == f"{untouched}\necho finished", (
        "the line the caller never touched came back changed — the projection's escaping "
        "reached the document as authored intent")


@pytest.mark.parametrize("untouched", LITERAL_LINES)
def test_ac2_the_projection_really_escaped_the_line_it_round_tripped(untouched):
    """The control the property needs: a case whose projection carried no escape at all
    would pass the test above while proving nothing."""
    escaped = _escape_literals(untouched)
    if escaped == untouched:
        pytest.skip(f"{untouched!r} carries nothing the policy escapes")
    tree = _document(_code("cd", "root", f"{untouched}\necho done"))
    assert escaped in project_block_ids(tree).markdown


BLOCK_KINDS = [
    pytest.param(_code("b", "root", "deploy rollback --service $SERVICE\necho done"),
                 "echo done", "echo finished",
                 "deploy rollback --service $SERVICE\necho finished", id="fenced-code"),
    pytest.param(_text("b", "root", "run -- the tool -- twice"),
                 "twice", "thrice", "run -- the tool -- thrice", id="paragraph"),
    pytest.param(_text("b", "root", "run -- the tool", block_type=12, key="bullet"),
                 "tool", "binary", "run -- the binary", id="list-item"),
    pytest.param(_text("b", "root", "quoted -- text", block_type=15, key="quote"),
                 "text", "prose", "quoted -- prose", id="quote"),
    pytest.param(_text("b", "root", "Heading -- one", block_type=3, key="heading1"),
                 "one", "two", "Heading -- two", id="heading"),
]


@pytest.mark.parametrize("block, old, new, expected", BLOCK_KINDS)
def test_ac2_every_block_kind_round_trips_its_untouched_literals(block, old, new, expected):
    _p, _plan, requests = _round_trip(_document(block), old, new)
    assert _replacement(requests) == expected


def _inserted(added):
    """The content an editor ADDED to the projection, compiled — the insert family.

    ``added`` is written in the projection's own domain (structure raw, literals escaped),
    which is what an editor copying a block within the document it was handed produces.
    """
    projection = project_block_ids(_document(_text("p", "root", "Intro.")))
    plan = reconcile(projection, projection.markdown + "\n" + added + "\n")
    assert plan.ok, [r.detail for r in plan.refusals]
    requests = compile_reconciliation(plan, projection)
    inserts = [r for r in requests if isinstance(r, InsertRequest)]
    assert len(inserts) == 1, requests
    return inserts[0].content


def test_ac2_a_table_cells_literals_survive_the_insert_path():
    """A table's cells are the compiler's other text-carrying field. They reach it through
    the INSERT family, which is the second request family the policy has to hold in."""
    table = [
        {"block_id": "tb", "parent_id": "root", "block_type": 31,
         "table": {"property": {"row_size": 2, "column_size": 2}},
         "children": ["c00", "c01", "c10", "c11"]},
        {"block_id": "c00", "parent_id": "tb", "block_type": 32, "table_cell": {},
         "children": ["t00"]},
        _text("t00", "c00", "a -- one"),
        {"block_id": "c01", "parent_id": "tb", "block_type": 32, "table_cell": {},
         "children": ["t01"]},
        _text("t01", "c01", "b -- two"),
        {"block_id": "c10", "parent_id": "tb", "block_type": 32, "table_cell": {},
         "children": ["t10"]},
        _text("t10", "c10", "c -- three"),
        {"block_id": "c11", "parent_id": "tb", "block_type": 32, "table_cell": {},
         "children": ["t11"]},
        _text("t11", "c11", "d"),
    ]
    content = _inserted(_projected_body(*table))
    assert content[0].rows == (("a -- one", "b -- two"), ("c -- three", "d"))


def test_ac2_an_inserted_code_block_carries_no_escape_into_the_document():
    """The insert family, on the shape that corrupts: a code block added in the
    projection's own domain — which is the domain the copy-this recipe hands the editor."""
    body = _projected_body(_code("cd", "root", "curl -X POST --fail example.com"))
    assert "\\-\\-fail" in body, body
    content = _inserted(body)
    assert content[0].text == "curl -X POST --fail example.com"


def test_ac2_nested_list_items_keep_the_literals_the_parser_already_decoded():
    """The pass walks the composed tree, so the other thing it must not do is decode
    twice: a nested list item's text was decoded by the parser as it read it, and running
    the inverse over it again would eat a backslash the editor meant."""
    body = "- step " + _escape_literals("-- one") + "\n    - step " + _escape_literals("-- two")
    content = _inserted(body)
    assert content[0].text == "step -- one"
    assert [c.text for c in content[0].children] == ["step -- two"]


def test_ac2_the_policy_reaches_a_verbatim_body_nested_under_another_block():
    """The pass is written over the composed TREE rather than over its top level. The
    authoring dialect refuses a fence inside a list item today (``compose`` says so in its
    own words), so this is asserted against the seam directly — the day a kind grows
    verbatim children, the policy already reaches them."""
    from larkdocio.write.compiler import _decoded_verbatim
    from larkdocio.write.model import NewBlock, NewBlockKind

    child = NewBlock(kind=NewBlockKind.CODE, text="make \\-\\- build", language="bash")
    parent = NewBlock(kind=NewBlockKind.BULLET, text="step one", children=(child,))
    decoded = _decoded_verbatim((parent,), "test")
    assert decoded[0].children[0].text == "make -- build"
    assert decoded[0].text == "step one"


# --------------------------------------------------------------------------- #
# AC3 — the plan preview renders both sides under ONE policy.                  #
# --------------------------------------------------------------------------- #

def test_ac3_the_preview_shows_the_untouched_line_unchanged_on_both_sides():
    """``before`` is the block's current text and ``after`` is what will land. Under one
    policy the untouched line is the SAME bytes on both sides, so the diff a caller reads
    is the diff they asked for."""
    original = "deploy rollback --service $SERVICE\necho done"
    tree = _document(_code("cd", "root", original))
    _p, _plan, requests = _round_trip(tree, "echo done", "echo finished")
    plan = dry_run(requests, tree, document_revision_id=REVISION)
    assert not plan.refusals, [r.to_dict() for r in plan.refusals]
    entry = plan.entries[0]
    assert entry.before == original
    assert entry.after == "deploy rollback --service $SERVICE\necho finished"
    assert entry.before.splitlines()[0] == entry.after.splitlines()[0]


def test_ac3_the_preview_does_not_decode_one_side_so_the_pre_fix_body_is_visible():
    """The masking control, written as the defect behaved: hand the preview the escaped
    replacement the compiler USED to emit and the two sides differ **visibly** — the
    backslashes are on screen, on a line the caller never edited. The preview renders both
    sides raw; it has no decode of its own to hide behind, and this pins that it never
    grows one."""
    original = "deploy rollback --service $SERVICE\necho done"
    tree = _document(_code("cd", "root", original))
    corrupting = "deploy rollback \\-\\-service $SERVICE\necho finished"
    from larkdocio.write.model import AnchorById

    plan = dry_run(
        [EditRequest(anchor=AnchorById(block_id="cd"), replacement=corrupting)],
        tree, document_revision_id=REVISION,
    )
    assert not plan.refusals, [r.to_dict() for r in plan.refusals]
    entry = plan.entries[0]
    assert entry.after == corrupting, "the preview must show exactly what will land"
    assert entry.before.splitlines()[0] != entry.after.splitlines()[0], (
        "a corrupting replacement must READ as a change to the untouched line")
