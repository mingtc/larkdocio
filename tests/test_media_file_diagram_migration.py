"""Media / file / diagram-family migration tests (LD-029).

The asset-emitting family — image (27), file (23), add_ons/Mermaid (40),
board (43), grid_column (25) — now CONSTRUCTs typed model nodes instead of
concatenating Markdown strings. These handlers **emit** tokens/placeholders; the
actual download + token->local-link substitution lives in the T1 pipeline
(``read/download.py``) and is out of scope here — the family owns only what it
emits.

These tests:

* assert the handler return TYPES (proving the migration happened);
* pin the node payload shape (the emitted token/caption/name/source);
* pin the renderer's byte-exact serialization of each case;
* **pin the SIDE EFFECT** — the image/board handlers append their token to
  ``parser.img_tokens`` / ``parser.board_tokens`` **at handler (construction)
  time**, NOT at render time. This is load-bearing: the download pipeline reads
  those lists after ``parse_docx_content`` returns to substitute local links, so
  the append must happen when the handler runs (LD-031/032 may separate node
  construction from rendering; the append must not migrate into the renderer).

Byte-identical whole-document *output* is additionally locked by the unchanged
T1 goldens (test_golden.py: image / image_no_token / board / mermaid /
file_attachment / grid_columns) which flow these nodes through the strangler
shim + renderer, and by the unchanged T1 download-pipeline tests
(test_download_pipeline.py) which exercise the duplicate-/failed-token
substitution against ``parser.img_tokens`` / ``parser.board_tokens``.

Mutation note (AC2): ``dev/mutation-baseline-2026-07-24.md`` § per-module lists
NO survivors for ``media.py`` / ``file.py`` / ``diagram.py`` (none appear in the
per-module table — the family had no triaged net-gap; the only survivor-heavy
neighbour, ``download.py`` at 177, is the asset-download pipeline that is
explicitly out of scope for this block-model story). There is therefore no
family-specific survivor to kill test-first; the pins below strengthen the net
anyway against the mutations the rewrite is most exposed to (the emitted token
strings, the missing-token/absent branches, the Mermaid-vs-unsupported
discriminant, the ``or 'unknown'`` fallback, and the construction-time append).

KEEP (LD-096, mindfulness not immunity): unique coverage the goldens cannot hold —
the load-bearing SIDE-EFFECT pins (``parser.img_tokens`` / ``parser.board_tokens``
appended at HANDLER-construction time, read later by the download pipeline; not
doc output), plus handler return-TYPE / carried-data, the Mermaid-vs-unsupported
and valid-JSON-non-dict discriminants, the ``or 'unknown'`` (never ``"None"``)
fallback, and the unreachable defensive guards (``FileNode()`` empty render;
``GridColumnNode`` standalone out-of-context). A future audit may revisit.
"""
from harness import build_blocks, render

from larkdocio.model import (
    AddOnsNode,
    BoardNode,
    FileNode,
    GridColumnNode,
    ImageNode,
    MarkdownRenderer,
)
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser


def _p():
    return Parser(Config())


def _r():
    return MarkdownRenderer()


# --- image (27): handler builds an ImageNode + appends the token -----------

def test_image_handler_returns_image_node_with_token_and_caption():
    from larkdocio.blocks.media import handle_image

    b = build_blocks([{
        "block_id": "img", "block_type": 27,
        "image": {"token": "boxcnTOK", "caption": {"content": "a cap"}},
    }])[0]
    parser = _p()
    node = handle_image(parser, b, 0)
    assert isinstance(node, ImageNode)
    assert node.token == "boxcnTOK"
    assert node.caption == "a cap"


def test_image_handler_appends_token_at_construction_time():
    # SIDE EFFECT PIN: the token is queued on parser.img_tokens by the HANDLER,
    # BEFORE anything is rendered. The download pipeline reads img_tokens after
    # parse_docx_content returns; if the append moved into the renderer this
    # assertion (which never renders) would fail.
    from larkdocio.blocks.media import handle_image

    b = build_blocks([{
        "block_id": "img", "block_type": 27,
        "image": {"token": "boxcnTOK", "caption": {"content": "cap"}},
    }])[0]
    parser = _p()
    assert parser.img_tokens == []
    handle_image(parser, b, 0)  # no render performed
    assert parser.img_tokens == ["boxcnTOK"]


def test_image_handler_missing_token_does_not_queue():
    from larkdocio.blocks.media import handle_image

    b = build_blocks([{
        "block_id": "img", "block_type": 27,
        "image": {"caption": {"content": "orphan"}},
    }])[0]
    parser = _p()
    node = handle_image(parser, b, 0)
    assert isinstance(node, ImageNode)
    assert node.token is None
    assert node.caption == "orphan"
    assert parser.img_tokens == []  # nothing to download


def test_image_handler_absent_image_returns_empty_node():
    from larkdocio.blocks.media import handle_image

    # A type-27 block whose ``image`` payload is entirely absent -> a node that
    # renders "" (caption sentinel None distinguishes "no image" from
    # "image present but no token").
    b = build_blocks([{"block_id": "img", "block_type": 2}])[0]  # no .image
    node = handle_image(_p(), b, 0)
    assert isinstance(node, ImageNode)
    assert node.caption is None


def test_image_renderer_with_token():
    assert _r().render(ImageNode(token="TOK", caption="cap")) == "![cap](TOK)\n"


def test_image_renderer_empty_caption_still_emits_empty_alt():
    assert _r().render(ImageNode(token="TOK", caption="")) == "![](TOK)\n"


def test_image_renderer_missing_token_marker_with_caption():
    assert _r().render(ImageNode(token=None, caption="orphan")) == (
        "[Image: missing token] orphan\n"
    )


def test_image_renderer_missing_token_marker_without_caption():
    assert _r().render(ImageNode(token=None, caption="")) == "[Image: missing token]\n"


def test_image_renderer_absent_image_is_empty_string():
    assert _r().render(ImageNode()) == ""


# --- board (43): handler builds a BoardNode + appends the token ------------

def test_board_handler_returns_board_node_and_queues_token():
    from larkdocio.blocks.diagram import handle_board

    b = build_blocks([{
        "block_id": "bd", "block_type": 43, "board": {"token": "BRDTOK"},
    }])[0]
    parser = _p()
    node = handle_board(parser, b, 0)
    assert isinstance(node, BoardNode)
    assert node.token == "BRDTOK"
    assert parser.board_tokens == ["BRDTOK"]  # queued at construction time


def test_board_handler_no_token_returns_empty_node_and_queues_nothing():
    from larkdocio.blocks.diagram import handle_board

    b = build_blocks([{"block_id": "bd", "block_type": 43, "board": {}}])[0]
    parser = _p()
    node = handle_board(parser, b, 0)
    assert isinstance(node, BoardNode)
    assert node.token is None
    assert parser.board_tokens == []


def test_board_renderer_with_token():
    assert _r().render(BoardNode(token="BRDTOK")) == "![Whiteboard](BRDTOK)\n"


def test_board_renderer_no_token_is_empty_string():
    assert _r().render(BoardNode()) == ""


# --- add_ons / Mermaid (40): handler builds an AddOnsNode ------------------

MERMAID_ID = "blk_640017963d808005a21a6445"


def _add_ons_block(record, component_type_id=MERMAID_ID):
    return build_blocks([{
        "block_id": "m", "block_type": 40,
        "add_ons": {
            "component_id": "c1",
            "component_type_id": component_type_id,
            "record": record,
        },
    }])[0]


def test_add_ons_handler_mermaid_extracts_source():
    from larkdocio.blocks.diagram import handle_mermaid

    node = handle_mermaid(_p(), _add_ons_block('{"data": "graph TD"}'), 0)
    assert isinstance(node, AddOnsNode)
    assert node.mermaid_source == "graph TD"
    assert node.unsupported_component_id is None


def test_add_ons_handler_valid_json_string_yields_empty_source():
    # record JSON that decodes to a bare *string* (valid JSON, non-dict) is
    # coerced to {} then .get('data', '') -> "" (no crash), exactly like the
    # legacy handler. (The raw-record fallback fires ONLY on a JSONDecodeError.)
    from larkdocio.blocks.diagram import handle_mermaid

    node = handle_mermaid(_p(), _add_ons_block('"just a string"'), 0)
    assert node.mermaid_source == ""


def test_add_ons_handler_list_record_yields_empty_source():
    from larkdocio.blocks.diagram import handle_mermaid

    node = handle_mermaid(_p(), _add_ons_block('[1, 2, 3]'), 0)
    # A JSON list is coerced to {} then .get('data', '') -> "" (no crash).
    assert node.mermaid_source == ""


def test_add_ons_handler_invalid_json_falls_back_to_raw_record():
    # A record that is NOT valid JSON raises JSONDecodeError; the legacy handler
    # then keeps the RAW record string as the mermaid source. Pin that branch.
    from larkdocio.blocks.diagram import handle_mermaid

    node = handle_mermaid(_p(), _add_ons_block('graph TD; A-->B'), 0)
    assert node.mermaid_source == 'graph TD; A-->B'


def test_add_ons_handler_unsupported_component_sets_marker_id():
    from larkdocio.blocks.diagram import handle_mermaid

    node = handle_mermaid(_p(), _add_ons_block("{}", component_type_id="blk_OTHER"), 0)
    assert node.unsupported_component_id == "blk_OTHER"
    assert node.mermaid_source is None


def test_add_ons_handler_unsupported_none_component_uses_unknown():
    # AC2 pin: a None/empty component id must resolve to the literal "unknown"
    # (never the string "None") in the node the handler builds.
    from larkdocio.blocks.diagram import handle_mermaid

    node = handle_mermaid(_p(), _add_ons_block("{}", component_type_id=None), 0)
    assert node.unsupported_component_id == "unknown"


def test_add_ons_renderer_mermaid_fenced_and_stripped():
    node = AddOnsNode(mermaid_source="  graph TD\n  A --> B  ")
    assert _r().render(node) == "```mermaid\ngraph TD\n  A --> B\n```\n"


def test_add_ons_renderer_empty_source_is_empty_string():
    assert _r().render(AddOnsNode(mermaid_source="")) == ""
    assert _r().render(AddOnsNode()) == ""


def test_add_ons_renderer_unsupported_marker():
    node = AddOnsNode(unsupported_component_id="blk_OTHER")
    assert _r().render(node) == "[Unsupported Add-On block: blk_OTHER]\n"


def test_add_ons_renderer_unsupported_marker_never_prints_none():
    node = AddOnsNode(unsupported_component_id="unknown")
    out = _r().render(node)
    assert out == "[Unsupported Add-On block: unknown]\n"
    assert "None" not in out


# --- file (23): handler builds a FileNode ----------------------------------

def test_file_handler_returns_file_node_with_name_and_token():
    from larkdocio.blocks.file import handle_file

    b = build_blocks([{
        "block_id": "f", "block_type": 23,
        "file": {"token": "FTOK", "name": "report.pdf"},
    }])[0]
    node = handle_file(_p(), b, 0)
    assert isinstance(node, FileNode)
    assert node.name == "report.pdf"
    assert node.token == "FTOK"


def test_file_handler_name_none_falls_back():
    from larkdocio.blocks.file import handle_file

    b = build_blocks([{
        "block_id": "f", "block_type": 23, "file": {"token": "FTOK", "name": None},
    }])[0]
    node = handle_file(_p(), b, 0)
    assert node.name == "Unknown File Attachment"


def test_file_handler_none_file_uses_fallback_name():
    # The SDK Block always *has* a ``file`` attribute (set to None), so the
    # ``not hasattr(b, 'file')`` guard never fires for a real block; a None file
    # falls through to the falsy-aware fallback -> a node carrying the
    # 'Unknown File Attachment' name (byte-identical to the legacy handler, which
    # emitted the attachment line, NOT "").
    from larkdocio.blocks.file import handle_file

    b = build_blocks([{"block_id": "f", "block_type": 23}])[0]  # file attr = None
    node = handle_file(_p(), b, 0)
    assert isinstance(node, FileNode)
    assert node.name == "Unknown File Attachment"
    assert node.token is None


def test_file_node_empty_guard_renders_nothing():
    # The defensive ``not b`` guard's FileNode() (name sentinel None) renders "".
    # Reachable only via a falsy block; pinned here at the node/renderer level.
    assert _r().render(FileNode()) == ""


def test_file_renderer_with_token():
    node = FileNode(name="report.pdf", token="FTOK")
    assert _r().render(node) == "📎 **File Attachment:** report.pdf (token: `FTOK`)\n"


def test_file_renderer_without_token():
    node = FileNode(name="report.pdf", token=None)
    assert _r().render(node) == "📎 **File Attachment:** report.pdf\n"


def test_file_renderer_absent_is_empty_string():
    assert _r().render(FileNode()) == ""


# --- grid_column (25): transparent safety-net node -------------------------

def test_grid_column_handler_returns_grid_column_node():
    from larkdocio.blocks.diagram import handle_grid_column

    b = build_blocks([{"block_id": "gc", "block_type": 25, "grid_column": {}}])[0]
    node = handle_grid_column(_p(), b, 0)
    assert isinstance(node, GridColumnNode)


def test_grid_column_renderer_is_empty_string():
    assert _r().render(GridColumnNode()) == ""


# --- integration: whole-document output byte-identical ---------------------

def test_image_end_to_end_queues_token_and_emits_link():
    blocks = [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "T"}}]}, "children": ["i"]},
        {"block_id": "i", "parent_id": "root", "block_type": 27,
         "image": {"token": "boxbTOK"}},
    ]
    out = render(blocks, doc_id="root")
    assert "![](boxbTOK)" in out


def test_board_and_mermaid_end_to_end():
    blocks = [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "T"}}]}, "children": ["b", "m"]},
        {"block_id": "b", "parent_id": "root", "block_type": 43,
         "board": {"token": "BRDTOK"}},
        {"block_id": "m", "parent_id": "root", "block_type": 40,
         "add_ons": {"component_type_id": MERMAID_ID,
                     "record": '{"data": "graph TD\\n  A --> B"}'}},
    ]
    out = render(blocks, doc_id="root")
    assert "![Whiteboard](BRDTOK)" in out
    assert "```mermaid" in out and "graph TD" in out


# --- registry division unchanged (Decision Log #2) -------------------------

def test_registry_division_unchanged():
    from larkdocio.blocks import get_registry

    registry = get_registry()
    for t in (27, 23, 25, 40, 43):
        assert t in registry
