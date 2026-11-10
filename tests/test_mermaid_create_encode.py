"""THE CREATABLE add_ons-40 MERMAID BLOCK — the payload, byte-exact against the gate's
own captures (LD-192 / AC2 + AC6).

**What authorizes this file.** ``dev/mermaid-gate-probe-2026-07-29.md`` § 1 returned
**CREATE: GO** — a *specimen-shaped* ``add_ons`` (docx block type 40) create is accepted
``code 0`` on both create endpoints and at both positions, and the created block is
byte-shape-identical to a Mermaid block the maintainer typed by hand. § 10 lists exactly what the
payload must carry, and § 8 records the **record-normalization law** the server stores by.

Every assertion below is measured against the spike's **committed captures**
(``tests/captures/mermaid-gate-captures/``) rather than against a hand-written expectation, so the
encoder is pinned to a body the API really accepted — the same discipline as every other
fixture in this suite (PROJECT.md § Quality bar: pin real payload shapes).

In this tree the specimen's Mermaid *source* inside those captures is a flowchart this project
wrote, swapped in for the hand-typed one in every encoding at once, with the same structure and
the same 1,646-byte record (``tests/captures/README.md``). What the tests pin — the block shape,
the record's keys and the normalization law — does not depend on the diagram's words.

The three refusal codes the matrix separated are pinned too (§ 4): they are what makes
``1770001`` a *malformed-body* answer rather than a prohibition, which is the finding this
whole issue rests on. If Lark ever closes the type-40 create route, these rows are the
re-test that detects it.
"""
import json
from pathlib import Path

import pytest

from larkdocio.blocks.diagram import MERMAID_COMPONENT_TYPE_ID
from larkdocio.mermaid.ruleset import THEMES
from larkdocio.write import NewBlock, NewParagraph
from larkdocio.write.encode import (
    CREATABLE_BLOCK_TYPES,
    MERMAID_BLOCK_TYPE,
    MERMAID_RECORD_VIEW,
    block_type_for,
    encode_block,
    encode_content,
    go_json_escape,
    mermaid_record,
    table_cell_texts,
)
from larkdocio.write.model import NewBlockKind

CAPTURES = Path(__file__).resolve().parents[1] / "tests" / "captures" / "mermaid-gate-captures"


def _capture(name):
    return json.loads((CAPTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def specimen():
    """The maintainer specimen block as the spike read it — the shape this encoder must emit.

    READ-ONLY, and read from a **committed capture**: nothing here touches the specimen
    document itself (the issue forbids it outright), so this test needs no credentials and
    no network.
    """
    capture = _capture("20-specimen.json")
    (only,) = capture["specimens"].values()
    return only


@pytest.fixture(scope="module")
def matrix():
    """``{label: attempt}`` for every row of the spike's create matrix."""
    return {a["label"]: a for a in _capture("21-create-matrix.json")["attempts"]}


# =========================================================================== #
# AC2 — the record: the Go-canonical normalization law, proven on the specimen  #
# =========================================================================== #

def test_the_record_law_reproduces_the_specimens_own_record_BYTE_for_BYTE(specimen):
    """§ 8's law, as the sharpest possible assertion: fed the specimen's own Mermaid source,
    the encoder emits the **exact 1646 bytes** Lark stored for a block the maintainer typed by hand.

    This is what "specimen-shaped" means operationally. The specimen's record is already in
    Go's default form (it came from Lark), so byte-equality here proves the encoder emits
    that form — sorted keys, compact separators, ``<``/``>``/``&`` escaped — rather than
    merely something semantically equal.
    """
    ours = mermaid_record(specimen["record_decoded"]["data"])
    assert ours == specimen["record_raw"]
    assert len(ours) == specimen["record_len"] == 1646


def test_the_record_is_a_json_STRING_carrying_exactly_data_theme_view(specimen):
    """Row (g) of the matrix refused ``9499`` for a record sent as an *object*. The record is
    a JSON string, and its three keys are the specimen's three keys."""
    record = mermaid_record("graph TD\n  A --> B")
    assert isinstance(record, str)
    assert sorted(json.loads(record)) == ["data", "theme", "view"] == sorted(
        specimen["record_keys"])


def test_the_record_is_sorted_and_compact_like_go_encoding_json():
    record = mermaid_record("graph TD\n  A --> B")
    assert record.startswith('{"data":')
    assert '", "' not in record and '": ' not in record, f"not compact: {record}"
    assert list(json.loads(record)) == sorted(json.loads(record))


@pytest.mark.parametrize("char", ["<", ">", "&"])
def test_the_record_escapes_the_three_characters_go_escapes(char):
    """The one place a hand-rolled ``json.dumps`` would drift from the server's form. A
    ``<br/>`` in a node label is ordinary Mermaid, so this is the common case, not an edge.

    The expected escape is **derived from the code point** here exactly as the encoder derives
    it, and the pairing is then cross-checked against the specimen's own bytes by
    ``test_the_record_law_reproduces_the_specimens_own_record_BYTE_for_BYTE`` — so this test
    cannot pass by agreeing with a typo in the encoder.
    """
    escape = "\\u%04x" % ord(char)
    record = mermaid_record(f'graph TD\n  A["x{char}y"] --> B')
    assert escape in record, record
    assert char not in record, record
    assert go_json_escape(char) == escape


def test_the_record_round_trips_the_source_verbatim_through_the_escaping():
    """Escaping is a *transport* form, never a content change: the decoded source is what
    was authored, byte for byte."""
    source = 'flowchart TD\n    A["a<br/>b & c"] --> B["x > y"]\n'
    assert json.loads(mermaid_record(source))["data"] == source


def test_the_record_carries_the_default_theme_and_the_specimens_view(specimen):
    record = json.loads(mermaid_record("graph TD\n  A --> B"))
    assert record["theme"] == specimen["record_decoded"]["theme"] == "default"
    assert record["view"] == specimen["record_decoded"]["view"] == MERMAID_RECORD_VIEW


@pytest.mark.parametrize("theme", THEMES)
def test_every_whitelisted_theme_reaches_the_record(theme):
    assert json.loads(mermaid_record("graph TD\n  A --> B", theme=theme))["theme"] == theme


# =========================================================================== #
# AC2 — the create payload, byte-exact against the ACCEPTED capture rows        #
# =========================================================================== #

def test_the_encoded_payload_is_byte_identical_to_the_ACCEPTED_capture_row(specimen, matrix):
    """The headline AC2 assertion. Row (a) — the full specimen replay — was accepted
    ``code 0`` at ``children``/append, at ``children``/``index=1`` **and** at
    ``descendant``/append. Our encoder's child payload must be that body, byte for byte.
    """
    row_a = matrix["row-a-children-append"]
    assert row_a["code"] == 0 and row_a["http_status"] == 200
    (accepted_child,) = row_a["request_body"]["children"]

    ours = encode_block(NewBlock.mermaid(specimen["record_decoded"]["data"]))

    assert ours == accepted_child
    # Byte-exact, not merely dict-equal: same keys in the same order, same serialization.
    assert json.dumps(ours) == json.dumps(accepted_child)


def _accepted_block(attempt):
    """The type-40 block payload out of an accepted attempt, whichever endpoint it used.

    ``create_children`` sends ``{"children": [block, ...]}``; the ``descendant`` endpoint sends
    ``{"children_id": ["tmp0"], "descendants": [{**block, "block_id": "tmp0"}]}`` — the same
    block payload plus a caller-minted temp id used only to wire the subtree. The temp id is
    the **envelope**, not the content, so it is dropped here: what is being compared across the
    three rows is the block itself.
    """
    body = attempt["request_body"]
    if "children" in body:
        (child,) = body["children"]
        return child
    (descendant,) = body["descendants"]
    assert descendant["block_id"] in body["children_id"], body
    return {k: v for k, v in descendant.items() if k != "block_id"}


@pytest.mark.parametrize("label", [
    "row-a-children-append",      # append at the end
    "row-a-children-index1",      # index-positioned BETWEEN two blocks
    "row-a-descendant-append",    # the other create endpoint
])
def test_the_same_payload_was_accepted_at_BOTH_positions_and_BOTH_endpoints(
        label, specimen, matrix):
    """The amplifier's "both positions" clause. One payload, three accepted call shapes —
    so the encoder needs no positional variant, and the engine's existing
    ``create_children`` + ``index`` plumbing is enough.
    """
    attempt = matrix[label]
    assert attempt["code"] == 0, attempt
    accepted_child = _accepted_block(attempt)
    assert encode_block(NewBlock.mermaid(specimen["record_decoded"]["data"])) == accepted_child


def test_the_index_positioned_row_really_placed_the_block_BETWEEN_two_blocks(matrix):
    """The amplifier asked for the index case specifically, so the capture is checked for it
    rather than trusted: row (a) at ``index=1`` is an insertion *between* existing blocks, and
    that is the position the engine uses for a ``BEFORE``/``AFTER`` anchor."""
    body = matrix["row-a-children-index1"]["request_body"]
    assert body["index"] == 1
    assert matrix["row-a-children-index1"]["code"] == 0


def test_the_payload_carries_the_field_the_server_calls_REQUIRED(matrix):
    """Row (e) refused ``99992402`` with the server's own named field violation:
    ``children[*].add_ons.component_type_id is required``. We emit it."""
    violation, = matrix["row-e-children-append"]["response"]["error"]["field_violations"]
    assert violation["field"] == "children[*].add_ons.component_type_id"
    payload = encode_block(NewBlock.mermaid("graph TD\n  A --> B"))
    assert payload["add_ons"]["component_type_id"] == MERMAID_COMPONENT_TYPE_ID


def test_the_component_type_id_is_the_READERS_own_constant_not_a_second_copy():
    """One definition of the component id, shared by the reader that parses type 40 and the
    encoder that creates one — so the two halves cannot drift into disagreeing about which
    add-on a Mermaid block is. (§ 3 re-confirmed the shipped constant against the specimen.)
    """
    payload = encode_block(NewBlock.mermaid("graph TD\n  A --> B"))
    assert payload["add_ons"]["component_type_id"] is MERMAID_COMPONENT_TYPE_ID


def test_component_id_is_emitted_EMPTY_exactly_as_a_hand_typed_block_carries_it(specimen):
    """§ 3's decisive finding: the one id-looking field is ``""`` on a real block — there is
    nothing server-minted to synthesize. Emitting it (rather than omitting it, which rows
    b/c/h prove also works) is what makes the body the **specimen** shape."""
    assert specimen["component_id"] == ""
    assert encode_block(NewBlock.mermaid("x")) ["add_ons"]["component_id"] == ""


def test_the_block_type_is_40(specimen):
    assert MERMAID_BLOCK_TYPE == specimen["block_type"] == 40
    block = NewBlock.mermaid("graph TD\n  A --> B")
    assert block_type_for(block) == 40
    assert encode_block(block)["block_type"] == 40


def test_the_payload_has_no_key_beyond_block_type_and_add_ons():
    payload = encode_block(NewBlock.mermaid("graph TD\n  A --> B"))
    assert sorted(payload) == ["add_ons", "block_type"]
    assert sorted(payload["add_ons"]) == ["component_id", "component_type_id", "record"]


# =========================================================================== #
# AC2 — the three REFUSAL codes stay pinned (so 1770001 can never be re-read    #
# as a prohibition, and a drift in the shapes we do NOT send is still visible)  #
# =========================================================================== #

@pytest.mark.parametrize("label, code, why", [
    ("row-e-children-append", 99992402,
     "add_ons present but missing component_type_id"),
    ("row-f-children-append", 1770001,
     "block_type 40 with NO add_ons key at all — the shape that produced the prior"),
    ("row-g-children-append", 9499,
     "record sent as a JSON object rather than a JSON string"),
])
def test_the_malformed_shapes_the_encoder_never_emits_are_pinned(label, code, why, matrix):
    """The prior this issue overturns, kept honest. ``1770001`` came from **row f** — a
    type-40 create carrying no ``add_ons`` object — not from a specimen-shaped one. Pinning
    all three codes is what makes "the code is about the payload, not the type" a measured
    claim rather than a remembered one.
    """
    attempt = matrix[label]
    assert attempt["code"] == code, why
    assert attempt["http_status"] == 400


def test_the_encoder_emits_none_of_those_three_malformations(matrix):
    payload = encode_block(NewBlock.mermaid("graph TD\n  A --> B"))
    refused_bodies = [
        matrix[label]["request_body"]["children"][0]
        for label in ("row-e-children-append", "row-f-children-append",
                      "row-g-children-append")
    ]
    for refused in refused_bodies:
        assert payload != refused
    assert payload["add_ons"]                                   # not row e's bare {}
    assert "add_ons" in payload                                  # not row f's missing key
    assert isinstance(payload["add_ons"]["record"], str)         # not row g's object


# =========================================================================== #
# AC6 — THE ENCODER AND THE MATRIX MOVE TOGETHER                                #
# =========================================================================== #

def test_type_40_is_in_the_encoders_creatable_set():
    """AC6's documented call, in code: mermaid **becomes authorable**, so 40 joins
    ``CREATABLE_BLOCK_TYPES`` — and ``tests/test_blocks_md_matrix.py`` (which pins BLOCKS.md
    row 40's Write column against this very set) forces the row to move in the same commit.
    That coupling is the point: the word never flips alone.
    """
    assert MERMAID_BLOCK_TYPE in CREATABLE_BLOCK_TYPES


def test_the_closed_enum_gained_exactly_one_kind_and_it_is_mermaid():
    """The enum stays **closed** — this adds one kind, deliberately, on the spike's evidence;
    it does not open the door to the types the spike never probed."""
    assert NewBlockKind.MERMAID.value == "mermaid"
    assert {k.value for k in NewBlockKind} == {
        "paragraph", "heading", "bullet", "ordered", "todo", "code", "quote", "table",
        "mermaid",
    }


def test_a_mermaid_block_is_a_LEAF_and_carries_no_cell_texts():
    """It is not a table and not a list: no children, no cell fills, one create call."""
    block = NewBlock.mermaid("graph TD\n  A --> B")
    assert block.children == ()
    assert block.depth == 1
    assert table_cell_texts(block) == ()
    (encoded,) = encode_content((block,))
    assert encoded.parent is None and encoded.depth == 1 and encoded.cell_texts == ()


def test_a_mermaid_block_encodes_the_same_inside_a_mixed_content_tuple():
    """The kind composes with the shipped ones — an insert may carry prose *and* a diagram."""
    content = (NewParagraph("intro"), NewBlock.mermaid("graph TD\n  A --> B"),
               NewBlock.heading(2, "after"))
    encoded = encode_content(content)
    assert [e.payload["block_type"] for e in encoded] == [2, 40, 4]
    assert encoded[1].payload == encode_block(content[1])


# =========================================================================== #
# The model's own construction refusals (the LD-134 discipline, applied here)   #
# =========================================================================== #

def test_the_source_is_carried_and_round_trips_through_the_wire_form():
    block = NewBlock.mermaid("graph TD\n  A --> B", theme="dark")
    d = block.to_dict()
    assert d == {"kind": "mermaid", "text": "graph TD\n  A --> B", "theme": "dark"}
    assert NewBlock.from_dict(d) == block
    assert encode_block(NewBlock.from_dict(d)) == encode_block(block)


def test_the_default_theme_is_omitted_from_the_wire_form_but_present_in_the_record():
    block = NewBlock.mermaid("graph TD\n  A --> B")
    assert "theme" not in block.to_dict()
    assert json.loads(encode_block(block)["add_ons"]["record"])["theme"] == "default"


def test_an_EMPTY_source_is_refused_because_it_would_author_an_INVISIBLE_block():
    """§ 8's observation, turned into a refusal. Lark accepts an empty ``data`` ``code 0``
    and the reader then emits **nothing at all** — no fence, no marker — so an empty source
    authors a block that is invisible in Markdown. That is a silent content drop, which the
    authoring doctrine forbids; it is refused with the reason named.
    """
    for empty in ("", "   ", "\n\n"):
        with pytest.raises(ValueError) as exc:
            NewBlock.mermaid(empty)
        assert "mermaid" in str(exc.value)


@pytest.mark.parametrize("theme", ["wobbly", "Default", "solarized", ""])
def test_an_off_whitelist_theme_is_REFUSED_because_the_server_validates_NOTHING(theme):
    """§ 8 measured it: ``theme: "wobbly"`` is accepted ``code 0`` and **kept**. The server
    validates nothing inside the record, so the whitelist is the only guard there is — which
    is exactly the argument for refusing rather than warning (§ 11 Q3).
    """
    with pytest.raises(ValueError) as exc:
        NewBlock.mermaid("graph TD\n  A --> B", theme=theme)
    assert "theme" in str(exc.value)
    for sanctioned in THEMES:
        assert sanctioned in str(exc.value)


@pytest.mark.parametrize("kind, kwargs", [
    (NewBlockKind.PARAGRAPH, {"text": "x"}),
    (NewBlockKind.CODE, {"text": "x"}),
    (NewBlockKind.QUOTE, {"text": "x"}),
])
def test_theme_is_meaningful_only_for_a_mermaid_block(kind, kwargs):
    with pytest.raises(ValueError) as exc:
        NewBlock(kind=kind, theme="dark", **kwargs)
    assert "theme" in str(exc.value)


def test_a_mermaid_block_cannot_carry_children_a_level_a_language_or_a_grid():
    source = "graph TD\n  A --> B"
    for field, value in (("level", 2), ("language", "python"), ("done", True),
                         ("rows", (("a",),))):
        with pytest.raises(ValueError):
            NewBlock(kind=NewBlockKind.MERMAID, text=source, **{field: value})
    with pytest.raises(ValueError):
        NewBlock(kind=NewBlockKind.MERMAID, text=source,
                 children=(NewBlock.paragraph("x"),))


def test_the_compiler_and_the_create_path_meet_at_a_string(specimen):
    """The integration seam, asserted rather than described: ``larkdocio.mermaid`` compiles a
    structured spec to Mermaid **text**, and ``NewBlock.mermaid`` takes text. Nothing else
    couples the two, which is why LD-191 needed no API and this issue needs no compiler.
    """
    from larkdocio.mermaid import flowchart

    source = flowchart({
        "direction": "TD",
        "nodes": [{"id": "A", "label": "Start"}, {"id": "B", "label": "Done"}],
        "edges": [{"from": "A", "to": "B"}],
    })
    payload = encode_block(NewBlock.mermaid(source))
    assert payload["block_type"] == 40
    assert json.loads(payload["add_ons"]["record"])["data"] == source
    assert payload["add_ons"]["component_type_id"] == specimen["component_type_id"]
