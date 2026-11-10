"""Embedded-data placeholder family (LD-048).

The embedded-data family — bitable (18), sheet (30), and reference_base (53) —
were previously **dropped** (18/30 intentionally-skipped → warn+drop; 53
unregistered → warn+drop). Per the read-completeness spec § Decision (a) (no silent drops), each now
CONSTRUCTs a typed model node whose renderer emits a **traceable marker** naming
the block + its id(s) — the ``reference_synced`` / file-attachment precedent.
**Deep read of the Base/Sheet contents is explicitly OUT of scope** (spec § Non-
Goals strategic descope) — these are placeholder markers only, zero API calls.

These tests:

* assert the handler return TYPES (proving the family is registered + migrated);
* pin the node payload shapes (token-bearing; 53 also carries ``view_id``);
* pin the renderer's byte-exact marker text — including the **18-vs-53
  distinction** the markers must document (embedding a base = 18; switching it to
  a named view = 53), and the **token-only** shape of the 30 marker (dims arrive
  null, so there is nothing else to mark);
* pin the Optional[str] sentinel (``token is None`` models an absent payload →
  emit nothing), and the present-but-None edge (defaults to ``'unknown'``, like
  :class:`ReferenceSyncedNode`).

Whole-document byte-identical output is additionally locked by the three
DELIBERATELY-updated goldens (test_golden.py: ``bitable`` / ``sheet`` /
``reference_base``) which flow these nodes through the parser + renderer — that
golden diff IS the S4 spec-change record (consented output ADDITION).
"""
from harness import build_blocks, render

from larkdocio.model import (
    BitableNode,
    MarkdownRenderer,
    ReferenceBaseNode,
    SheetNode,
)
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser


def _p():
    return Parser(Config())


def _r():
    return MarkdownRenderer()


# --- exact marker text (the traceable-marker contract) ---------------------

BITABLE_MARKER = (
    "> 📊 **Embedded Base** (bitable) — not fetched. token: `TOK18`. "
    "Contents (records, views, formulas) live in a separate Base document; "
    "deep read is out of scope. (Switching an embedded base to a named view "
    "makes it a reference_base — type 53 — instead.)\n"
)
SHEET_MARKER = (
    "> 📊 **Embedded Sheet** — not fetched. token: `TOK30`. "
    "The spreadsheet's cells live in a separate Sheet document; deep read is "
    "out of scope.\n"
)
REFERENCE_BASE_MARKER = (
    "> 📊 **Embedded Base — named view** (reference_base) — not fetched. "
    "token: `TOK53`, view: `VIEW53`. A base switched to a named view (distinct "
    "from an embedded Base — type 18; consumers hit both interchangeably).\n"
)


# --- bitable (18): handler builds a BitableNode ----------------------------

def test_bitable_handler_returns_node_with_token():
    from larkdocio.blocks.embedded import handle_bitable

    b = build_blocks(
        [{"block_id": "bt", "block_type": 18,
          "bitable": {"token": "TOK18", "view_type": None}}]
    )[0]
    node = handle_bitable(_p(), b, 0)
    assert isinstance(node, BitableNode)
    assert node.token == "TOK18"


def test_bitable_handler_missing_attr_returns_empty_node():
    from larkdocio.blocks.embedded import handle_bitable

    class _Bare:
        pass

    node = handle_bitable(_p(), _Bare(), 0)
    assert isinstance(node, BitableNode)
    assert node.token is None
    assert _r().render(node) == ""


def test_bitable_handler_none_payload_defaults_to_unknown():
    # A real SDK Block whose `bitable` is present-but-None (mis-routed type-2):
    # the `not hasattr` guard does NOT fire (SDK Blocks always carry the attr),
    # so token defaults to 'unknown' and the marker is still emitted.
    from larkdocio.blocks.embedded import handle_bitable

    b = build_blocks([{"block_id": "x", "block_type": 2}])[0]
    node = handle_bitable(_p(), b, 0)
    assert node.token == "unknown"


def test_bitable_renderer_exact_marker():
    assert _r().render(BitableNode(token="TOK18")) == BITABLE_MARKER


def test_bitable_renderer_none_token_is_empty():
    assert _r().render(BitableNode(token=None)) == ""


# --- sheet (30): handler builds a SheetNode (token only, dims null) ---------

def test_sheet_handler_returns_node_with_token():
    from larkdocio.blocks.embedded import handle_sheet

    b = build_blocks(
        [{"block_id": "sh", "block_type": 30,
          "sheet": {"token": "TOK30", "row_size": None, "column_size": None}}]
    )[0]
    node = handle_sheet(_p(), b, 0)
    assert isinstance(node, SheetNode)
    assert node.token == "TOK30"


def test_sheet_handler_missing_attr_returns_empty_node():
    from larkdocio.blocks.embedded import handle_sheet

    class _Bare:
        pass

    node = handle_sheet(_p(), _Bare(), 0)
    assert isinstance(node, SheetNode)
    assert node.token is None
    assert _r().render(node) == ""


def test_sheet_handler_none_payload_defaults_to_unknown():
    from larkdocio.blocks.embedded import handle_sheet

    b = build_blocks([{"block_id": "x", "block_type": 2}])[0]
    node = handle_sheet(_p(), b, 0)
    assert node.token == "unknown"


def test_sheet_renderer_exact_marker_token_only():
    # Dims arrive null → the marker carries ONLY the token, nothing else.
    assert _r().render(SheetNode(token="TOK30")) == SHEET_MARKER


def test_sheet_renderer_none_token_is_empty():
    assert _r().render(SheetNode(token=None)) == ""


# --- reference_base (53): handler builds a ReferenceBaseNode ----------------

def test_reference_base_handler_returns_node_with_token_and_view():
    from larkdocio.blocks.embedded import handle_reference_base

    b = build_blocks(
        [{"block_id": "rb", "block_type": 53,
          "reference_base": {"token": "TOK53", "view_id": "VIEW53",
                             "layout_mode": "Normal"}}]
    )[0]
    node = handle_reference_base(_p(), b, 0)
    assert isinstance(node, ReferenceBaseNode)
    assert node.token == "TOK53"
    assert node.view_id == "VIEW53"


def test_reference_base_handler_missing_attr_returns_empty_node():
    from larkdocio.blocks.embedded import handle_reference_base

    class _Bare:
        pass

    node = handle_reference_base(_p(), _Bare(), 0)
    assert isinstance(node, ReferenceBaseNode)
    assert node.token is None and node.view_id is None
    assert _r().render(node) == ""


def test_reference_base_handler_none_payload_defaults_to_unknown():
    from larkdocio.blocks.embedded import handle_reference_base

    b = build_blocks([{"block_id": "x", "block_type": 2}])[0]
    node = handle_reference_base(_p(), b, 0)
    assert node.token == "unknown" and node.view_id == "unknown"


def test_reference_base_renderer_exact_marker():
    node = ReferenceBaseNode(token="TOK53", view_id="VIEW53")
    assert _r().render(node) == REFERENCE_BASE_MARKER


def test_reference_base_renderer_none_token_is_empty():
    assert _r().render(ReferenceBaseNode(token=None, view_id=None)) == ""


# --- the 18-vs-53 distinction is documented in the markers (AC2) -----------

def test_markers_document_the_18_vs_53_distinction():
    bt = _r().render(BitableNode(token="TOK18"))
    rb = _r().render(ReferenceBaseNode(token="TOK53", view_id="VIEW53"))
    # 18 names 53 as the named-view form; 53 names 18 as the plain-embed form.
    assert "type 53" in bt and "named view" in bt
    assert "type 18" in rb and "named view" in rb


# --- end-to-end whole-document renders (golden-shape) ----------------------

def test_bitable_end_to_end_emits_marker():
    blocks = [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc Title"}}]},
         "children": ["bt"]},
        {"block_id": "bt", "parent_id": "root", "block_type": 18,
         "bitable": {"token": "TOK18", "view_type": None}},
    ]
    out = render(blocks, doc_id="root")
    assert BITABLE_MARKER.rstrip("\n") in out


def test_sheet_end_to_end_emits_marker():
    blocks = [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc Title"}}]},
         "children": ["sh"]},
        {"block_id": "sh", "parent_id": "root", "block_type": 30,
         "sheet": {"token": "TOK30", "row_size": None, "column_size": None}},
    ]
    out = render(blocks, doc_id="root")
    assert SHEET_MARKER.rstrip("\n") in out


def test_reference_base_end_to_end_emits_marker():
    blocks = [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc Title"}}]},
         "children": ["rb"]},
        {"block_id": "rb", "parent_id": "root", "block_type": 53,
         "reference_base": {"token": "TOK53", "view_id": "VIEW53",
                            "layout_mode": "Normal"}},
    ]
    out = render(blocks, doc_id="root")
    assert REFERENCE_BASE_MARKER.rstrip("\n") in out


# --- registry: the family is registered (18/30/53) -------------------------

def test_embedded_family_registered():
    from larkdocio.blocks import get_registry

    registry = get_registry()
    assert 18 in registry and 30 in registry and 53 in registry
