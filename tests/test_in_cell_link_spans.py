"""LD-619 — a link-carrying text run inside a docx TABLE CELL.

*"``| EX-01 | Example Item | [Example Item - Details](https://…) |``"* — the shape one
consumer filed, and the shape the measurement below was taken on, whose link column was a
wall of 60-character URLs. **The row's words, its header and its link label are placeholders
in this tree**: the consumer's own were replaced by generic ones, identically in what was sent
and in what Lark stored (``tests/captures/README.md``), so the capture still pairs the request with Lark's
own read-back and the round trip below is still proved against Lark's bytes (D-06). This
library refused it; **Lark does not**, and that is a measurement rather than an inference:
``dev/ld517-in-cell-link/findings.md``, ruled into a build by ``requirements/DECISIONS.md``
**D-110**.

**THE FIXTURE IS THE REAL CAPTURE, AND THIS MODULE LOADS IT FROM DISK.** Every payload
shape asserted here is read out of
``tests/captures/ld517-in-cell-link/captures/001-in-cell-link-readback.json`` — the probe's own
committed capture, ``sent`` for what went to Lark and ``read_back`` for what Lark stored —
so the round trip is proved against **Lark's bytes**, never against a fixture invented to
match this encoder (D-06). If the encoder drifts from the capture, these tests redden.

Conformance-tier: the accepted payload shape and the reader's projection of it are
**measured external truth / product contract**, not this module's internal choices
(``process/doctrine/conformance-tier.md`` § A.4).
"""
import dataclasses
import json
import pathlib

import pytest

from compose_roundtrip import reader_markdown
from harness import render

from larkdocio.write import compose
from larkdocio.write.apply import build_whole_paragraph_update, build_span_elements_update
from larkdocio.write.encode import encode_content, table_cell_spans, table_cell_texts
from larkdocio.write.model import NewBlock, NewBlockKind, TextSpan

pytestmark = pytest.mark.conformance

#: The probe's committed capture — the ONE source of every shape asserted below.
CAPTURE = json.loads(
    (pathlib.Path(__file__).resolve().parents[1]
     / "tests" / "captures" / "ld517-in-cell-link" / "captures"
     / "001-in-cell-link-readback.json").read_text(encoding="utf-8")
)

LABEL = "Example Item - Details"
URL = "https://example.com/items/example-item"

#: The exact run Lark **stored** inside the cell, on both write routes, quoted from the
#: capture's fresh read-back. Six style keys, five of them false — Lark does not model a
#: cell's inner text block as a lesser thing.
STORED_RUN = CAPTURE["read_back"]["route_A_cell_inner_block"]["runs"][0]


def _sent_cell_element():
    """The element the probe SENT in the route-A descendant body, from the capture."""
    for descendant in CAPTURE["sent"]["route_A_descendant_body"]["descendants"]:
        text = descendant.get("text")
        if text and text["elements"][0]["text_run"].get("text_element_style"):
            return text["elements"][0]
    raise AssertionError("the capture no longer carries a styled cell element")


def _sent_fill_element():
    """The element the probe SENT on the route-B batch_update body, from the capture."""
    return CAPTURE["sent"]["route_B_batch_update_body"][0]["update_text_elements"][
        "elements"][0]


def metrics() -> NewBlock:
    """The consumer's own row, as the typed shape authors it."""
    return NewBlock.table(
        [["Code", "Name", "Link"],
         ["EX-01", "Example Item", (TextSpan(LABEL, link_url=URL),)]],
        header_row=True,
    )


# --------------------------------------------------------------------------- #
# The capture is what it claims to be — checked before anything is asserted    #
# against it, so a capture that changed cannot silently weaken every arm.      #
# --------------------------------------------------------------------------- #

def test_the_capture_says_lark_accepted_and_stored_the_run_on_BOTH_routes():
    assert CAPTURE["issue"] == "LD-517"
    assert CAPTURE["verdicts"] == {
        "control_paragraph": "ACCEPTED_AND_STORED_VERBATIM",
        "route_A_create_time_descendant": "ACCEPTED_AND_STORED_VERBATIM",
        "route_B_fill_time_update_text_elements": "ACCEPTED_AND_STORED_VERBATIM",
    }
    assert STORED_RUN["text_element_style"]["link"] == {"url": URL}
    assert STORED_RUN["content"] == LABEL


# --------------------------------------------------------------------------- #
# AC1 — the observable: a link survives a round trip through a table cell.      #
# --------------------------------------------------------------------------- #

def test_ac1_the_run_LARK_STORED_renders_back_as_the_labelled_link():
    """The read half, against the stored bytes rather than against our own encoder.

    The cell payload here is the capture's ``read_back`` run, pasted into the grid shape
    the capture's own ``block_id_relations`` describe (a type-32 cell wrapping one type-2
    text block).
    """
    blocks = [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": []}, "children": ["t"]},
        {"block_id": "t", "parent_id": "root", "block_type": 31,
         "table": {"property": {"row_size": 1, "column_size": 2, "header_row": True}},
         "children": ["c0", "c1"]},
        {"block_id": "c0", "parent_id": "t", "block_type": 32, "table_cell": {},
         "children": ["x0"]},
        {"block_id": "x0", "parent_id": "c0", "block_type": 2, "children": [],
         "text": {"elements": [{"text_run": {"content": "EX-01"}}]}},
        {"block_id": "c1", "parent_id": "t", "block_type": 32, "table_cell": {},
         "children": ["x1"]},
        {"block_id": "x1", "parent_id": "c1", "block_type": 2, "children": [],
         "text": {"elements": [{"text_run": STORED_RUN}]}},
    ]
    assert f"| EX-01 | [{LABEL}]({URL}) |" in render(blocks, doc_id="root")


def test_ac1_a_markdown_table_whose_cell_holds_a_labelled_link_ROUND_TRIPS():
    """Markdown in, the same Markdown out — through ``compose()`` and the real reader."""
    source = (
        "| Code | Name | Link |\n"
        "|---|---|---|\n"
        f"| EX-01 | Example Item | [{LABEL}]({URL}) |\n"
    )
    assert reader_markdown(compose(source)) == source


def test_ac1_the_composed_cell_is_a_SPAN_carrying_the_url_verbatim():
    source = f"| A |\n|---|\n| [{LABEL}]({URL}) |\n"
    table = compose(source)[0]
    assert table.kind is NewBlockKind.TABLE
    assert table.rows[1][0] == (TextSpan(LABEL, link_url=URL),)


def test_ac1_the_plain_text_projection_of_a_rich_cell_is_its_anchor_text():
    """``table_cell_texts`` stays the plain-text projection every existing reader of a
    NewBlock uses (the preview, the refusal messages, the reconciler) — a rich cell adds a
    layer rather than replacing the field, exactly as ``spans`` does on a paragraph."""
    assert table_cell_texts(metrics()) == (
        "Code", "Name", "Link", "EX-01", "Example Item", LABEL,
    )


# --------------------------------------------------------------------------- #
# AC2 — BOTH write routes carry it, because Lark accepts both.                 #
# --------------------------------------------------------------------------- #

def test_ac2_route_A_the_atomic_descendant_create_sends_the_captured_element():
    """The one-call ``descendant`` subtree — the element is the capture's own ``sent``."""
    from larkdocio.write.encode import table_subtree

    encoded = encode_content((metrics(),))[0]
    _table_id, descendants = table_subtree(encoded)
    linked = [d for d in descendants
              if d.get("text", {}).get("elements", [{}])[0].get(
                  "text_run", {}).get("text_element_style")]
    assert len(linked) == 1
    assert linked[0]["text"]["elements"] == [_sent_cell_element()]


def test_ac2_route_B_the_create_grow_fill_batch_update_sends_the_captured_element():
    """The ``update_text_elements`` body the fill patches into a Lark-provisioned cell."""
    body = build_span_elements_update((TextSpan(LABEL, link_url=URL),))
    assert body == {"update_text_elements": {"elements": [_sent_fill_element()]}}


def test_ac2_a_plain_cell_is_BYTE_IDENTICAL_on_both_routes_to_what_it_always_was():
    """The plain path does not move: an unlinked cell keeps the exact bytes it had."""
    from larkdocio.write.encode import table_subtree

    encoded = encode_content((NewBlock.table([["a", "b"]], header_row=False),))[0]
    _table_id, descendants = table_subtree(encoded)
    inner = [d for d in descendants if d["block_type"] == 2]
    assert [d["text"]["elements"] for d in inner] == [
        [{"text_run": {"content": "a"}}], [{"text_run": {"content": "b"}}],
    ]
    assert build_whole_paragraph_update([], "a") == {
        "update_text_elements": {"elements": [{"text_run": {"content": "a"}}]}}


# --------------------------------------------------------------------------- #
# AC3 — the new boundary. A LINK, and nothing else, is what was measured.      #
# --------------------------------------------------------------------------- #

def test_ac3_a_table_BLOCK_still_refuses_spans_and_now_names_the_cell_route():
    """TRANSFORMED, never deleted (D-110). The original reason survives verbatim — a
    table's content lives in rows — and only the conclusion moved: the anchor is authored
    in the ROW, so the block-level carrier is still the wrong place for it."""
    with pytest.raises(ValueError) as exc:
        NewBlock(kind=NewBlockKind.TABLE, rows=(("a",),),
                 spans=(TextSpan("x", link_url=URL),))
    message = str(exc.value)
    assert "content lives in rows" in message
    assert "rows=" in message and "TextSpan" in message


def test_ac3_no_style_key_other_than_link_can_reach_a_cell():
    """The fence is STRUCTURAL, not a runtime check: a ``TextSpan`` has exactly two
    fields, so bold / italic / strikethrough / inline code / underline in a cell are
    **inexpressible by construction** — there is nothing to refuse and nothing that could
    be widened by accident. LD-517 measured a **link**; this is what keeps the build inside
    the measurement (D-106's evidence-borrowing fence, D-59)."""
    assert [f.name for f in dataclasses.fields(TextSpan)] == ["text", "link_url"]

    from larkdocio.write.encode import table_subtree
    encoded = encode_content((metrics(),))[0]
    _table_id, descendants = table_subtree(encoded)
    for descendant in descendants:
        for element in descendant.get("text", {}).get("elements", ()):
            style = element["text_run"].get("text_element_style", {})
            assert set(style) <= {"link"}, style


@pytest.mark.parametrize("construct,cell", [
    ("bold", "**bold**"),
    ("italic", "*italic*"),
    ("strikethrough", "~~struck~~"),
    ("inline-code", "`code`"),
    ("image", "![alt](x.png)"),
])
def test_ac3_every_OTHER_inline_construct_in_a_cell_is_still_refused(construct, cell):
    """Unmeasured, not refuted — and therefore not shipped."""
    from larkdocio.write.model import RefusedError

    with pytest.raises(RefusedError) as exc:
        compose(f"| A |\n|---|\n| {cell} |\n")
    assert exc.value.refusal.detail.startswith(f"{construct} at line 3")


def test_ac3_a_labelled_link_OUTSIDE_a_cell_is_still_refused_by_the_dialect():
    """The dialect opened in the CELL only. In a paragraph the shipped route is still the
    typed one (``NewBlock.rich_paragraph``) — D-110 ruled the cell, and widening the
    dialect elsewhere is a separate decision nobody has taken."""
    from larkdocio.write.model import RefusedError

    with pytest.raises(RefusedError) as exc:
        compose(f"see [{LABEL}]({URL})\n")
    assert exc.value.refusal.detail.startswith("link at line 1")
    # the typed paragraph route is still what the refusal names
    assert "rich_paragraph" in exc.value.refusal.detail


def test_ac3_a_bare_url_cell_still_composes_as_PLAIN_TEXT_not_as_a_span():
    """The reader's own autolink shape is unchanged: ``[url](url)`` in a cell is the one
    link whose anchor IS its href, and it stays a plain run (LD-054)."""
    table = compose(f"| A |\n|---|\n| [{URL}]({URL}) |\n")[0]
    assert table.rows[1][0] == URL
    assert table_cell_spans(table) == (None, None)


def test_ac3_a_percent_encoded_url_is_refused_in_a_cell_too():
    with pytest.raises(ValueError, match="PERCENT-ENCODED"):
        NewBlock.table([["a"], [(TextSpan("x", link_url="https%3A%2F%2Fexample.com"),)]])


def test_ac3_an_empty_span_sequence_in_a_cell_is_refused_rather_than_authored_blank():
    with pytest.raises(ValueError, match="at least one span"):
        NewBlock.table([["a"], [()]])


def test_ac3_a_cell_holding_something_that_is_neither_text_nor_spans_is_refused():
    with pytest.raises(ValueError, match="row 1 / column 0"):
        NewBlock.table([["a"], [42]])
    with pytest.raises(ValueError, match="row 1 / column 0"):
        NewBlock.table([["a"], [("not a span",)]])


# --------------------------------------------------------------------------- #
# The typed record survives JSON — a plan is serialized and approved out of     #
# process, so a rich cell that could not round-trip through the record would    #
# be a cell that vanishes between the preview and the apply.                    #
# --------------------------------------------------------------------------- #

def test_a_rich_cell_survives_the_to_dict_from_dict_round_trip():
    block = metrics()
    wire = block.to_dict()
    assert wire["rows"][1][2] == [{"text": LABEL, "link_url": URL}]
    assert json.loads(json.dumps(wire)) == wire
    assert NewBlock.from_dict(wire) == block


# --------------------------------------------------------------------------- #
# AC2, end to end: the whole gated chain against the offline Lark doubles —     #
# compose → dry_run → apply → READ IT BACK with the shipped parser. Both        #
# routes, chosen the way the engine chooses them (one table alone takes the      #
# atomic descendant call; a table beside another block takes create-grow-fill). #
# --------------------------------------------------------------------------- #

_ROSTER_MD = (
    "| Code | Name | Link |\n"
    "|---|---|---|\n"
    f"| EX-01 | Example Item | [{LABEL}]({URL}) |\n"
)


def _apply_and_read_back(content, monkeypatch):
    """Author ``content`` into an empty offline document and read the Markdown back.

    The doubles' shared document store is installed through ``monkeypatch`` rather than by
    hand: it is a **class** attribute other modules also patch, and a hand-rolled
    ``del`` in a ``finally`` would remove a store this test never installed.
    """
    import guide_recipes as gr

    from larkdocio.read.config import new_config
    from larkdocio.read.parser import Parser
    from larkdocio.write import apply, dry_run
    from larkdocio.write.client import text_block
    from larkdocio.write.model import Anchor, InsertPosition, InsertRequest

    doc = "doccnExample00002"
    store = gr.OfflineDocuments(empty=True)
    monkeypatch.setattr(gr.OfflineWriteClient, "documents", store, raising=False)
    monkeypatch.setattr(gr.OfflineDocxReadClient, "documents", store, raising=False)

    client = gr.OfflineWriteClient("write-app", "write-secret")
    client.create_children(doc, doc, [text_block("anchor line")], index=0)

    read_client = gr.OfflineDocxReadClient("read-app", "read-secret", "larksuite.com")
    docx, blocks = read_client.get_docx_content(doc)
    root = Parser(new_config()).parse_docx_tree(docx.document_id, blocks)

    plan = dry_run([InsertRequest(
        reference=Anchor(quote="anchor line"),
        position=InsertPosition.AFTER,
        content=tuple(content),
    )], root)
    log = apply(plan, client, doc)
    assert [e.outcome for e in log.entries] == ["inserted"], log.entries

    docx, blocks = read_client.get_docx_content(doc)
    return Parser(new_config()).parse_docx_content(docx.document_id, blocks), log


def test_ac2_route_A_end_to_end_the_link_is_READ_BACK_out_of_the_cell(monkeypatch):
    """One table alone — the atomic ``descendant`` route."""
    markdown, _log = _apply_and_read_back(compose(_ROSTER_MD), monkeypatch)
    assert f"| EX-01 | Example Item | [{LABEL}]({URL}) |" in markdown


def test_ac2_route_B_end_to_end_the_link_is_READ_BACK_out_of_the_cell(monkeypatch):
    """A paragraph BESIDE the table — two encoded blocks, so the engine takes the
    create-then-grow-then-fill route and the cell is one Lark provisioned itself."""
    content = compose("before the table\n\n" + _ROSTER_MD)
    assert len(content) == 2, content
    markdown, _log = _apply_and_read_back(content, monkeypatch)
    assert f"| EX-01 | Example Item | [{LABEL}]({URL}) |" in markdown


# --------------------------------------------------------------------------- #
# The file-first projection's identity guard reaches a rich cell too.           #
# --------------------------------------------------------------------------- #

def test_a_marker_riding_a_rich_cell_s_ANCHOR_TEXT_is_refused_not_written_back():
    """The compiled-projection guard is span-aware: an identity marker in a cell's anchor
    text is refused exactly as one in plain cell text is. A marker in the URL is impossible
    by construction — a projected marker carries spaces and a ``TextSpan`` refuses a URL
    with whitespace in it."""
    from larkdocio.write.compiler import _marker_guarded_content
    from larkdocio.write.model import RefusedError

    clean = NewBlock.table([["a"], [(TextSpan("plain label", link_url=URL),)]])
    assert _marker_guarded_content(clean, ["doxabc"], "where") == clean

    marked = NewBlock.table(
        [["a"], [(TextSpan("<!-- lark:block:doxabc -->", link_url=URL),)]])
    with pytest.raises(RefusedError, match="identity marker"):
        _marker_guarded_content(marked, ["doxabc"], "where")


def test_a_rich_cell_survives_the_whole_REQUEST_record_too():
    """The record a caller approves out of process is an ``InsertRequest``, not a bare block —
    so the cell has to survive that serialization as well, or a link would vanish between the
    preview somebody signed off and the apply."""
    from larkdocio.write.model import Anchor, InsertPosition, InsertRequest

    request = InsertRequest(reference=Anchor(quote="q"),
                            position=InsertPosition.AFTER, content=(metrics(),))
    wire = request.to_dict()
    assert wire["content"][0]["rows"][1][2] == [{"text": LABEL, "link_url": URL}]
    assert InsertRequest.from_dict(json.loads(json.dumps(wire))) == request

