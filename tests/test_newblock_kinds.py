"""Offline unit tests for the typed ``NewBlock`` kinds + their Lark encoders
(LD-134).

Before this story ``NewParagraph(text: str)`` was the **entire** creatable surface — the
dogfood session's **F2** blocker ("the docx write engine cannot create headings at any
level"), which made headings, lists and todos inexpressible and halted three of the maintainer's
four asks. S1 lifts the floor to the **Markdown-expressible non-table set**: a typed
:class:`~larkdocio.write.model.NewBlock` family (the additive ``kind`` ``NewParagraph``'s
own docstring anticipated) covering

* **heading(level)** — Lark heading1..heading9 (block types 3–11),
* **paragraph** — the back-compatible ``NewParagraph`` equivalent (type 2),
* **bullet / ordered / todo list items, with nesting** (types 12 / 13 / 17),
* **code(language)** (type 14) and **quote** (type 15),

each with an **encoder** to the real ``create_children`` child payload. The payload oracle
is the **reader's own parse shapes**: every encoded payload is deserialized by the SDK's own
``Block(...)`` and rendered by the reader's registered handler, so *what the reader parses,
the encoder emits* is asserted rather than asserted-about (AC2/AC3).

Everything stays inside the existing gate: ``NewBlock`` is dumb frozen typed data, the
encoder never touches a client, and the only way content reaches Lark is
``dry_run`` → :class:`~larkdocio.write.preview.Plan` → ``apply`` (AC4). All offline (a fake
clock + a stub opener, no network); the live create-per-kind is QA's ``live_write`` gate.
"""
import ast
import dataclasses
import json
import sys
from pathlib import Path

import pytest

from harness import render

from larkdocio.blocks.text import DOCX_CODE_LANG_TO_MD
from larkdocio.langs import MD_LANG_TO_DOCX_CODE
from larkdocio.write.apply import apply
from larkdocio.write.client import text_block
from larkdocio.write.encode import (
    CREATABLE_BLOCK_TYPES,
    block_type_for,
    create_batches,
    encode_block,
    encode_content,
)
from larkdocio.write.model import (
    MAX_CHILDREN_PER_CALL,
    MAX_NEST_DEPTH,
    Anchor,
    InsertPosition,
    InsertRequest,
    NewBlock,
    NewBlockKind,
    NewParagraph,
)
from larkdocio.write.preview import PlanEntry, dry_run

from write_harness import (
    StubOpener,
    _block_payload,
    _by_method,
    _client,
    _page,
    _para,
    _parent_payload,
    _run,
)


# --------------------------------------------------------------------------- #
# helpers                                                                       #
# --------------------------------------------------------------------------- #

def _insert_blocks(quote, position, blocks, *, breadcrumb=()):
    """An :class:`InsertRequest` carrying typed ``NewBlock`` content."""
    return InsertRequest(
        reference=Anchor(quote=quote, breadcrumb=breadcrumb),
        position=position,
        content=tuple(blocks),
    )


def _create_ok(created_ids):
    """A ``create_children`` response: ``data.children`` carries the new block id(s)."""
    return {"code": 0, "data": {
        "children": [{"block_id": bid} for bid in created_ids],
        "document_revision_id": 200,
    }}


def _read_back(encoded):
    """Render an ENCODED flat sequence through the READER — the payload oracle.

    Rebuilds the block tree the encoder described (parent pointers → ``children``
    lists), deserializes each child payload with the SDK's own ``Block(...)`` (via
    ``harness.build_blocks``) and renders it with the reader's registered handlers. So
    the assertion is "the reader parses what the encoder emitted", not "the dict looks
    right".
    """
    ids = [f"nb{i}" for i in range(len(encoded))]
    kids = {i: [] for i in range(len(encoded))}
    roots = []
    for i, ec in enumerate(encoded):
        if ec.parent is None:
            roots.append(ids[i])
        else:
            kids[ec.parent].append(ids[i])
    blocks = [{
        "block_id": "root", "parent_id": "doc", "block_type": 1,
        "page": {"elements": []}, "children": roots,
    }]
    for i, ec in enumerate(encoded):
        parent_id = "root" if ec.parent is None else ids[ec.parent]
        blocks.append({
            "block_id": ids[i], "parent_id": parent_id,
            "children": list(kids[i]), **ec.payload,
        })
    return render(blocks, doc_id="root")


def _read_one(item):
    """Render a SINGLE ``NewBlock`` (or ``NewParagraph``) through the reader."""
    return _read_back(encode_content((item,)))


# =========================================================================== #
# AC1 — the typed NewBlock family: frozen, JSON-round-tripping, back-compatible #
# =========================================================================== #

def test_ac1_the_kind_enum_is_exactly_the_md_expressible_set():
    """The closed kind vocabulary — heading / paragraph / bullet / ordered / todo /
    code / quote, plus the ``table`` LD-135 added (S2) and the ``mermaid`` diagram LD-192
    added on live evidence. It is a **closed enum**, which is what keeps the types this
    library does not author (image / board / embed / bitable / sheet) structurally
    inexpressible: there is no kind for them and no token/url field to smuggle one.

    **``mermaid`` is here because the API proved it creatable, and that is the rule the enum
    follows**: a kind is admitted on evidence, not on convenience. It was previously listed
    among the "write-hostile" types on the strength of one *naive* create that refused
    ``1770001``; a specimen-shaped create is accepted ``code 0``, so the claim was false and
    the kind belongs. Nothing follows for **bitable (18)** or **sheet (30)** — that probe
    covered mermaid only, and they remain inexpressible.

    (S1's own kinds are pinned individually below; this set is the vocabulary boundary.)"""
    assert {k.value for k in NewBlockKind} == {
        "paragraph", "heading", "bullet", "ordered", "todo", "code", "quote", "table",
        "mermaid",
    }


def test_ac1_newblock_is_frozen():
    nb = NewBlock.paragraph("hello")
    with pytest.raises(dataclasses.FrozenInstanceError):
        nb.text = "mutated"


@pytest.mark.parametrize("item", [
    NewBlock.paragraph("plain"),
    NewBlock.paragraph(""),
    NewBlock.heading(1, "H1"),
    NewBlock.heading(9, "H9"),
    NewBlock.bullet("b"),
    NewBlock.ordered("o"),
    NewBlock.todo("t", done=False),
    NewBlock.todo("t", done=True),
    NewBlock.code("print(1)", language="python"),
    NewBlock.code(""),
    NewBlock.quote("q"),
    NewBlock.bullet("L1", children=(NewBlock.bullet("L2", children=(NewBlock.bullet("L3"),)),)),
])
def test_ac1_every_kind_json_round_trips(item):
    """Frozen + JSON-round-trippable: ``from_dict(json(to_dict()))`` reproduces the
    value, nesting included."""
    assert NewBlock.from_dict(json.loads(json.dumps(item.to_dict()))) == item


def test_ac1_newparagraph_remains_valid_and_equivalent_to_kind_paragraph():
    """Back-compat: ``NewParagraph`` is still accepted as insert content and encodes
    **byte-identically** to ``kind=paragraph`` — the same Lark payload, so an existing
    consumer's writes are unchanged."""
    assert encode_block(NewParagraph("same text")) == encode_block(
        NewBlock.paragraph("same text"))
    assert encode_block(NewParagraph("same text")) == text_block("same text")


def test_ac1_newparagraph_serialization_stays_tagless_and_byte_unchanged():
    """A ``NewParagraph`` still serializes as the bare ``{"text": ...}`` it always did
    (no ``kind`` tag), so W3-era plan JSON reads back byte-compatible — the tagless
    ``EditRequest`` precedent."""
    assert NewParagraph("x").to_dict() == {"text": "x"}


def test_ac1_a_newblock_serializes_with_a_kind_discriminator():
    """A ``NewBlock`` tags itself, so one content dispatcher tells the two apart."""
    assert NewBlock.paragraph("x").to_dict()["kind"] == "paragraph"
    assert NewBlock.heading(2, "x").to_dict() == {"kind": "heading", "text": "x", "level": 2}


def test_ac1_mixed_newparagraph_and_newblock_content_is_accepted():
    """One insert may carry both shapes — the widening is additive, not a migration."""
    req = _insert_blocks("q", InsertPosition.AFTER, [
        NewParagraph("old shape"), NewBlock.heading(1, "new shape")])
    assert len(req.content) == 2


# -- the typed structural refusals (never a crash, never a silent coercion) --- #

@pytest.mark.parametrize("level", [0, -1, 10, 99])
def test_ac1_heading_level_outside_lark_1_9_is_a_typed_refusal(level):
    """Lark ships heading1..heading9 (block types 3–11) and nothing else, so a level
    outside 1–9 has no block type — refused at construction with the range named."""
    with pytest.raises(ValueError, match="1..9"):
        NewBlock.heading(level, "x")


def test_ac1_a_level_on_a_non_heading_kind_is_a_typed_refusal():
    with pytest.raises(ValueError, match="level"):
        NewBlock(kind=NewBlockKind.BULLET, text="x", level=2)


def test_ac1_a_heading_without_a_level_is_a_typed_refusal():
    with pytest.raises(ValueError, match="level"):
        NewBlock(kind=NewBlockKind.HEADING, text="x")


def test_ac1_a_language_on_a_non_code_kind_is_a_typed_refusal():
    with pytest.raises(ValueError, match="language"):
        NewBlock(kind=NewBlockKind.QUOTE, text="x", language="python")


def test_ac1_done_on_a_non_todo_kind_is_a_typed_refusal():
    with pytest.raises(ValueError, match="done"):
        NewBlock(kind=NewBlockKind.BULLET, text="x", done=True)


@pytest.mark.parametrize("kind", [
    NewBlockKind.PARAGRAPH, NewBlockKind.HEADING, NewBlockKind.CODE, NewBlockKind.QUOTE,
])
def test_ac1_children_on_a_non_list_kind_is_a_typed_refusal(kind):
    """Nesting is a **list** structure in this rung (bullet / ordered / todo). A
    paragraph / heading / code / quote carrying children is refused rather than
    silently flattened."""
    extra = {"level": 1} if kind is NewBlockKind.HEADING else {}
    with pytest.raises(ValueError, match="children"):
        NewBlock(kind=kind, text="x", children=(NewBlock.bullet("c"),), **extra)


@pytest.mark.parametrize("factory", [
    lambda: NewBlock.heading(1, ""),
    lambda: NewBlock.bullet(""),
    lambda: NewBlock.ordered("   "),
    lambda: NewBlock.todo(""),
    lambda: NewBlock.quote(""),
])
def test_ac1_a_marker_kind_with_no_text_is_a_typed_refusal(factory):
    """A heading / list item / quote is a **marker plus content**: with no content the
    reader would emit a bare marker that carries nothing, so it is refused rather than
    authored. (A paragraph and a code block are content-only and may be empty — the
    next test.)"""
    with pytest.raises(ValueError, match="text"):
        factory()


def test_ac1_an_empty_paragraph_and_an_empty_code_block_are_allowed():
    """An empty paragraph is a legitimate blank line and an empty fence is a legitimate
    empty code block — neither is a marker with nothing behind it."""
    assert NewBlock.paragraph("").text == ""
    assert NewBlock.code("").text == ""


def test_ac1_an_unknown_kind_string_is_a_typed_refusal():
    with pytest.raises(ValueError):
        NewBlock.from_dict({"kind": "callout", "text": "x"})


def test_ac1_an_unknown_code_language_is_a_typed_refusal_naming_the_token():
    """A language Lark has no enum for is refused at construction — never silently
    downgraded to plain text (which would lose the consumer's intent invisibly)."""
    with pytest.raises(ValueError, match="nosuchlang"):
        NewBlock.code("x", language="nosuchlang")


def test_ac1_no_language_means_plain_text():
    assert NewBlock.code("x").language is None
    assert encode_block(NewBlock.code("x"))["code"]["style"]["language"] == 1


# =========================================================================== #
# AC2 — encoders produce the documented Lark create_children payloads           #
#        (asserted against the READER's own parse shapes)                       #
# =========================================================================== #

def test_ac2_creatable_block_types_are_the_documented_set():
    """The block types the creatable floor can bring into existence: text 2, heading1..9
    3–11, bullet 12, ordered 13, code 14, quote 15, todo 17 — plus the table family 31/32
    that LD-135 (S2) added, and the **add_ons diagram 40** that LD-192 added. Together,
    BLOCKS.md's ``creatable`` rows (the matrix guard pins that correspondence both ways)."""
    assert CREATABLE_BLOCK_TYPES == frozenset(
        {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 31, 32, 40})


@pytest.mark.parametrize("level,block_type", [(l, l + 2) for l in range(1, 10)])
def test_ac2_heading_encodes_to_its_lark_block_type_and_keyed_container(level, block_type):
    """heading{L} → block type ``L + 2`` (heading1 = 3 … heading9 = 11) with the
    content under the ``heading{L}`` key the reader reads it from."""
    payload = encode_block(NewBlock.heading(level, f"H{level}"))
    assert payload == {
        "block_type": block_type,
        f"heading{level}": {"elements": [{"text_run": {"content": f"H{level}"}}]},
    }
    assert block_type_for(NewBlock.heading(level, "x")) == block_type


@pytest.mark.parametrize("level", list(range(1, 10)))
def test_ac2_heading_round_trips_through_the_readers_own_handler(level):
    """The reader emits ``#``×level for the encoded heading, **capped at ``######``** for
    H7–H9 (LD-145 — seven ``#`` is not a heading in CommonMark; the authored level still
    reaches Lark intact, and the reader's tree still reports it). The write side is
    unchanged: ``NewBlock.heading(9, …)`` still creates a heading9."""
    out = _read_one(NewBlock.heading(level, "Section"))
    assert f"{'#' * min(level, 6)} Section" in out, out
    assert "#######" not in out, out


def test_ac2_paragraph_encodes_to_the_type_2_text_block():
    payload = encode_block(NewBlock.paragraph("body text"))
    assert payload == {
        "block_type": 2,
        "text": {"elements": [{"text_run": {"content": "body text"}}]},
    }
    assert "body text" in _read_one(NewBlock.paragraph("body text"))


def test_ac2_bullet_encodes_to_type_12_and_reads_back_as_a_bullet():
    assert encode_block(NewBlock.bullet("item")) == {
        "block_type": 12,
        "bullet": {"elements": [{"text_run": {"content": "item"}}]},
    }
    assert "- item" in _read_one(NewBlock.bullet("item"))


def test_ac2_ordered_encodes_to_type_13_and_reads_back_numbered():
    assert encode_block(NewBlock.ordered("first")) == {
        "block_type": 13,
        "ordered": {"elements": [{"text_run": {"content": "first"}}]},
    }
    assert "1. first" in _read_one(NewBlock.ordered("first"))


@pytest.mark.parametrize("done,marker", [(False, "- [ ] "), (True, "- [x] ")])
def test_ac2_todo_encodes_its_done_state_and_reads_back_in_both_states(done, marker):
    """The done state lives in ``todo.style.done`` — exactly where the reader reads it
    (``b.todo.style.done``). Both states asserted (the amplifier)."""
    payload = encode_block(NewBlock.todo("task", done=done))
    assert payload == {
        "block_type": 17,
        "todo": {
            "elements": [{"text_run": {"content": "task"}}],
            "style": {"done": done},
        },
    }
    assert f"{marker}task" in _read_one(NewBlock.todo("task", done=done))


def test_ac2_code_encodes_the_language_enum_and_reads_back_fenced():
    payload = encode_block(NewBlock.code("print(1)", language="python"))
    assert payload == {
        "block_type": 14,
        "code": {
            "elements": [{"text_run": {"content": "print(1)"}}],
            "style": {"language": 49},
        },
    }
    assert "```python\nprint(1)\n```" in _read_one(
        NewBlock.code("print(1)", language="python"))


def test_ac2_a_code_block_with_no_language_reads_back_as_a_bare_fence():
    out = _read_one(NewBlock.code("nolang"))
    assert "```\nnolang\n```" in out, out


def test_ac2_quote_encodes_to_type_15_and_reads_back_prefixed():
    assert encode_block(NewBlock.quote("said")) == {
        "block_type": 15,
        "quote": {"elements": [{"text_run": {"content": "said"}}]},
    }
    assert "> said" in _read_one(NewBlock.quote("said"))


def test_ac2_the_md_language_map_is_the_readers_own_map_reversed():
    """The encoder's MD-token → Lark-enum map is **derived from** the reader's
    ``DOCX_CODE_LANG_TO_MD``, so the two can never disagree about a language (and every
    token a reader can emit is a token the encoder accepts)."""
    expected = {md: docx for docx, md in DOCX_CODE_LANG_TO_MD.items() if md}
    assert MD_LANG_TO_DOCX_CODE == expected
    # the reverse direction is unambiguous — no two Lark enums share an MD token
    tokens = [md for md in DOCX_CODE_LANG_TO_MD.values() if md]
    assert len(tokens) == len(set(tokens))


# -- the amplifier: unicode, MD metacharacters, a fence inside a fence --------- #

@pytest.mark.parametrize("kind_factory", [
    lambda t: NewBlock.paragraph(t),
    lambda t: NewBlock.heading(3, t),
    lambda t: NewBlock.bullet(t),
    lambda t: NewBlock.ordered(t),
    lambda t: NewBlock.todo(t),
    lambda t: NewBlock.quote(t),
    lambda t: NewBlock.code(t),
])
def test_ac2_unicode_content_survives_the_encoder_verbatim(kind_factory):
    """CJK + emoji + combining marks land byte-verbatim in the payload (no escaping,
    no normalization, no encoding games)."""
    text = "示例 ✅ café — naïve 🚀"
    payload = encode_block(kind_factory(text))
    container = next(v for k, v in payload.items() if k != "block_type")
    assert container["elements"][0]["text_run"]["content"] == text


@pytest.mark.parametrize("literal", ["- not a list", "# not a heading", "**not bold**", "> not a quote"])
def test_ac2_authored_md_metacharacters_land_literal_in_the_payload(literal):
    """The LD-130 escaping interplay: escaping is a **reader** concern (it protects
    plain text from parsing as structure). The **encoder** must ship the authored text
    verbatim — a consumer that authors the literal text ``- not a list`` inside a bullet
    gets that text, not a nested list and not a backslash."""
    payload = encode_block(NewBlock.bullet(literal))
    assert payload["bullet"]["elements"][0]["text_run"]["content"] == literal
    assert "\\" not in payload["bullet"]["elements"][0]["text_run"]["content"]


def test_ac2_authored_md_metacharacters_are_escaped_by_the_reader_not_the_encoder():
    """Round-trip proof of the same interplay: the authored literal reaches Lark
    unescaped, and the READER escapes it on the way back out so it can never
    masquerade as structure."""
    out = _read_one(NewBlock.bullet("- not a list"))
    assert "- \\- not a list" in out, out


def test_ac2_a_code_block_may_contain_a_fence():
    """A fence inside a code block's content is content, not structure — the encoder
    ships it verbatim (the reader's fencing is the reader's problem)."""
    body = "```\nnested fence\n```"
    payload = encode_block(NewBlock.code(body, language="markdown"))
    assert payload["code"]["elements"][0]["text_run"]["content"] == body


# =========================================================================== #
# AC3 — nesting: parent/child relationships, one create_children call per parent #
# =========================================================================== #

def test_ac3_flat_content_encodes_as_one_root_batch():
    """The back-compat shape: flat content is a single batch at the insertion point —
    exactly the one ``create_children`` call the W3 engine always made."""
    encoded = encode_content((NewParagraph("a"), NewBlock.heading(1, "b")))
    assert [e.parent for e in encoded] == [None, None]
    assert [e.depth for e in encoded] == [1, 1]
    assert create_batches(encoded) == ((None, (0, 1)),)


def test_ac3_three_level_nesting_encodes_the_parent_child_relationships():
    """A 3-level bullet tree encodes **pre-order** with each child pointing at its
    parent's position, and one batch per parent (the API creates one level per
    ``create_children`` call)."""
    tree = NewBlock.bullet("L1", children=(
        NewBlock.bullet("L2", children=(NewBlock.bullet("L3"),)),
    ))
    encoded = encode_content((tree,))

    assert [e.payload["block_type"] for e in encoded] == [12, 12, 12]
    assert [e.parent for e in encoded] == [None, 0, 1]
    assert [e.depth for e in encoded] == [1, 2, 3]
    assert create_batches(encoded) == ((None, (0,)), (0, (1,)), (1, (2,)))


def test_ac3_nesting_round_trips_structurally_through_the_reader():
    """The structural round-trip (AC3): the encoded tree, read back by the reader's own
    list handlers, is a 3-level nested list (the renderer's tab indents)."""
    tree = NewBlock.bullet("L1", children=(
        NewBlock.bullet("L2", children=(NewBlock.bullet("L3"),)),
    ))
    out = _read_back(encode_content((tree,)))
    assert "- L1" in out, out
    assert "\t- L2" in out, out
    assert "\t\t- L3" in out, out


def test_ac3_mixed_list_kinds_may_nest_within_each_other():
    """A bullet may parent an ordered item may parent a todo — the three list kinds
    nest freely (each is a Lark list block that can hold children)."""
    tree = NewBlock.bullet("b", children=(
        NewBlock.ordered("o", children=(NewBlock.todo("t", done=True),)),
    ))
    encoded = encode_content((tree,))
    assert [e.payload["block_type"] for e in encoded] == [12, 13, 17]
    out = _read_back(encoded)
    assert "- b" in out and "\t1. o" in out and "\t\t- [x] t" in out, out


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_ac3_nesting_at_depth_1_2_3_is_accepted(depth):
    item = NewBlock.bullet(f"d{depth}")
    for level in range(depth - 1, 0, -1):
        item = NewBlock.bullet(f"d{level}", children=(item,))
    encoded = encode_content((item,))
    assert max(e.depth for e in encoded) == depth


def test_ac3_nesting_deeper_than_the_documented_cap_is_a_typed_refusal():
    """Past the documented cap the tree is refused **with the cap named** — never
    silently flattened (the spec's parked nesting question, answered: cap + refuse).

    The refusal fires at **construction**, the earliest possible point: the block that
    would exceed the cap cannot exist, so an over-deep tree can never reach a plan, an
    encoder, or a write."""
    item = NewBlock.bullet("deepest")
    for _ in range(MAX_NEST_DEPTH - 1):      # exactly at the cap so far
        item = NewBlock.bullet("wrap", children=(item,))
    with pytest.raises(ValueError, match=str(MAX_NEST_DEPTH)) as exc:
        NewBlock.bullet("one too deep", children=(item,))
    assert "flatten" in str(exc.value), "the refusal must promise no silent flattening"


def test_ac3_a_tree_at_exactly_the_cap_is_accepted():
    item = NewBlock.bullet("deepest")
    for _ in range(MAX_NEST_DEPTH - 1):
        item = NewBlock.bullet("wrap", children=(item,))
    assert max(e.depth for e in encode_content((item,))) == MAX_NEST_DEPTH


def test_ac3_more_siblings_than_create_children_accepts_is_a_typed_refusal():
    """``create_children`` creates **1–50** blocks per call, so a sibling group past 50
    cannot be created in one level — a typed refusal naming the limit, not an opaque
    ``1770001`` from Lark halfway through a batch."""
    with pytest.raises(ValueError, match=str(MAX_CHILDREN_PER_CALL)):
        NewBlock.bullet("parent", children=tuple(
            NewBlock.bullet(f"c{i}") for i in range(MAX_CHILDREN_PER_CALL + 1)))
    with pytest.raises(ValueError, match=str(MAX_CHILDREN_PER_CALL)):
        InsertRequest(
            reference=Anchor(quote="q"),
            position=InsertPosition.AFTER,
            content=tuple(NewParagraph(f"p{i}") for i in range(MAX_CHILDREN_PER_CALL + 1)),
        )


# -- apply: one create_children per parent, real ids threaded down ------------- #

def test_ac3_apply_creates_a_nested_tree_one_call_per_parent_threading_real_ids():
    """The apply path (injected transport): batch 1 lands at the plan's insertion point;
    each deeper batch is created **under the real block id Lark returned** for its
    parent — so the nesting the consumer authored is the nesting that exists."""
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", InsertPosition.AFTER, [
        NewBlock.bullet("L1", children=(
            NewBlock.bullet("L2", children=(NewBlock.bullet("L3"),)),
        )),
    ])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),         # its LIVE parent → the index (LD-453)
        _create_ok(["realL1"]),
        _create_ok(["realL2"]),
        _create_ok(["realL3"]),
    ])
    log = apply(plan, _client(opener), "doc123")

    posts = _by_method(opener, "POST")
    assert len(posts) == 3
    assert "/blocks/root/children" in posts[0]["url"]
    assert posts[0]["body"]["index"] == 1
    assert posts[0]["body"]["children"] == [
        {"block_type": 12, "bullet": {"elements": [{"text_run": {"content": "L1"}}]}}]
    assert "/blocks/realL1/children" in posts[1]["url"]
    assert posts[1]["body"]["index"] == -1          # appended as the parent's last child
    assert "/blocks/realL2/children" in posts[2]["url"]
    assert log.entries[0].outcome == "inserted"
    assert log.entries[0].created_block_ids == ("realL1", "realL2", "realL3")


def test_ac3_a_flat_insert_still_issues_exactly_one_create_children_call():
    """Back-compat, proved at the transport: flat ``NewParagraph`` content produces the
    SAME single call with the SAME body the W3 engine produced."""
    tree = _page(_para("p1", "first line"))
    plan = dry_run([_insert_blocks("first line", InsertPosition.AFTER, [
        NewParagraph("a brand new paragraph")])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("first line")], parent_id="root"),
        _parent_payload("root", ["p1"]),         # its LIVE parent → the index (LD-453)
        _create_ok(["newX"]),
    ])
    apply(plan, _client(opener), "doc123")

    posts = _by_method(opener, "POST")
    assert len(posts) == 1
    assert posts[0]["body"] == {
        "index": 1,
        "children": [{
            "block_type": 2,
            "text": {"elements": [{"text_run": {"content": "a brand new paragraph"}}]},
        }],
    }


def test_ac3_apply_creates_a_heading_through_the_gate():
    """F2, closed: a heading now reaches Lark through the plan-gated path."""
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", InsertPosition.AFTER, [
        NewBlock.heading(2, "Findings")])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),         # its LIVE parent → the index (LD-453)
        _create_ok(["newH"]),
    ])
    log = apply(plan, _client(opener), "doc123")

    post = _by_method(opener, "POST")[0]
    assert post["body"]["children"] == [
        {"block_type": 4, "heading2": {"elements": [{"text_run": {"content": "Findings"}}]}}]
    assert log.entries[0].created_block_ids == ("newH",)


# =========================================================================== #
# AC4 — gated + findings-agnostic; the AST guard extends to the new types        #
# =========================================================================== #

_MODEL_DIR = Path(__file__).resolve().parents[1] / "src" / "larkdocio" / "write" / "model"
_ENCODE_PY = Path(__file__).resolve().parents[1] / "src" / "larkdocio" / "write" / "encode.py"
_LANGS_PY = Path(__file__).resolve().parents[1] / "src" / "larkdocio" / "langs.py"


def _code_identifiers(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
    return names


@pytest.mark.parametrize("path", [_ENCODE_PY, _LANGS_PY])
def test_ac4_the_new_modules_reference_no_findings_vocabulary(path):
    """AC4 (D6): the findings-agnostic AST guard **extends to the new modules** — the
    encoder and the language table learn nothing about a consumer's findings schema."""
    idents = {n.lower() for n in _code_identifiers(ast.parse(path.read_text(encoding="utf-8")))}
    for word in ("finding", "layer", "severity", "accepted", "rejected"):
        offenders = {n for n in idents if word in n}
        assert not offenders, f"findings-schema vocabulary in {path.name}: {offenders}"


def test_ac4_the_new_model_symbols_are_covered_by_the_findings_guard():
    """The guard must actually SEE the new content types — a guard that scans a file the
    new symbols do not live in is theatre."""
    idents = set()
    for p in sorted(_MODEL_DIR.rglob("*.py")):  # LD-654: population must be recursive
        idents |= _code_identifiers(ast.parse(p.read_text(encoding="utf-8")))
    for name in ("NewBlock", "NewBlockKind"):
        assert name in idents, f"the findings guard does not cover {name}"


@pytest.mark.parametrize("path", [_ENCODE_PY, _LANGS_PY])
def test_ac4_the_new_modules_import_only_stdlib_and_larkdocio(path):
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
    allowed = set(sys.stdlib_module_names) | {"larkdocio"}
    assert roots <= allowed, f"{path.name}: non-stdlib imports {roots - allowed}"


def test_ac4_the_encoder_never_writes_and_needs_no_client():
    """The encoder is pure: no credential, no transport, no client, no socket — so there
    is no ungated authoring path through it. Asserted over CODE identifiers (the
    docstring may freely *name* the endpoint whose payload shape it documents)."""
    idents = _code_identifiers(ast.parse(_ENCODE_PY.read_text(encoding="utf-8")))
    for forbidden in (
        "WriteClient", "urlopen", "urlretrieve", "create_children", "_patch_block",
        "batch_delete", "_write", "apply", "token_fetcher",
    ):
        assert forbidden not in idents, (
            f"the encoder must not reach a transport or a write path: {forbidden}")


def test_ac4_the_encoder_needs_no_client_at_runtime():
    """Called with nothing but typed data, the encoder produces payloads — proving a
    consumer can build (and inspect) authored content with no credentials configured."""
    payloads = [e.payload for e in encode_content((
        NewBlock.heading(1, "H"),
        NewBlock.bullet("b", children=(NewBlock.todo("t"),)),
        NewBlock.code("x", language="rust"),
    ))]
    assert [p["block_type"] for p in payloads] == [3, 12, 17, 14]


def test_ac4_authored_content_reaches_lark_only_through_a_dry_run_plan():
    """The gate is unchanged and non-forgeable: ``apply`` accepts **only** a ``Plan``,
    and a ``Plan`` exists only as ``dry_run``'s output. A hand-built batch of NewBlock
    content cannot be applied."""
    with pytest.raises(TypeError):
        apply([PlanEntry.insert_resolved(
            reference=Anchor(quote="q"),
            content=(NewBlock.heading(1, "forged"),),
            position="after",
            block_id="b1",
            insertion_point=None,
        )], _client(StubOpener([])), "doc123")


def test_ac4_a_dry_run_of_newblock_content_issues_no_write():
    """A dry-run of authored content is still zero writes."""
    tree = _page(_para("p1", "anchor line"))
    opener = StubOpener([])
    dry_run([_insert_blocks("anchor line", InsertPosition.AFTER, [
        NewBlock.heading(1, "H"), NewBlock.bullet("b")])], tree)
    assert opener.requests == []


def test_ac4_the_plan_entry_round_trips_newblock_content_through_json():
    """The plan wire format carries the new kinds: one content dispatcher deserializes
    ``NewBlock`` (tagged) and ``NewParagraph`` (tagless) — so a consumer's approval UX
    can serialize a plan and read it back without losing the authored structure."""
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", InsertPosition.AFTER, [
        NewBlock.heading(3, "Section"),
        NewBlock.todo("do it", done=True),
        NewParagraph("legacy shape"),
    ])], tree)
    entry = plan.entries[0]
    back = PlanEntry.from_dict(json.loads(json.dumps(entry.to_dict())))
    assert back.content == entry.content
    assert back.content == (
        NewBlock.heading(3, "Section"),
        NewBlock.todo("do it", done=True),
        NewParagraph("legacy shape"),
    )


def test_ac4_the_dry_run_preview_shows_every_authored_kind():
    """The mandatory dry-run previews WHAT would be created for every kind — an approval
    UX can show the authored structure before a single write."""
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line", InsertPosition.AFTER, [
        NewBlock.heading(1, "H"), NewBlock.bullet("b"), NewBlock.code("c", language="go"),
    ])], tree)
    shown = plan.to_dict()["entries"][0]["content"]
    assert [c["kind"] for c in shown] == ["heading", "bullet", "code"]


# =========================================================================== #
# AC5 — truth rows: the capabilities() floor lists the new kinds                #
# =========================================================================== #

def test_ac5_the_capabilities_floor_lists_the_new_creatable_type():
    """AC5: the projected creatable-content floor names ``NewBlock`` alongside
    ``NewParagraph`` — projected from ``InsertRequest.content``, so it cannot claim a
    richer floor than the model accepts."""
    from larkdocio import capabilities

    cc = capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]
    assert cc["creatable"] == ["NewBlock", "NewParagraph"], cc
    assert "kind" in cc["creatable_content_fields"]


def test_ac5_the_capabilities_floor_no_longer_claims_headings_are_not_creatable():
    """The floor must stop lying the other way: headings / list items / todos / code /
    quotes moved OUT of ``not_creatable``."""
    from larkdocio import capabilities

    cc = capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]
    joined = " ".join(cc["not_creatable"]).lower()
    for gone in ("heading", "list item", "code block", "quote"):
        assert gone not in joined, f"{gone!r} is creatable now: {cc['not_creatable']}"
    # …and since LD-135 (S2) a plain table is creatable too — only a MERGED cell is not.
    assert "merged" in joined, f"the merged-cell exclusion must be named: {cc['not_creatable']}"


def test_ac5_the_floor_prose_names_the_new_creatable_set():
    from larkdocio import capabilities

    floor = capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]["floor"].lower()
    for word in ("heading", "bullet", "ordered", "todo", "code", "quote", "nest"):
        assert word in floor, f"the floor prose must name {word!r}"
