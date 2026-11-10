"""Agenda family handlers — S2 / LD-046 (the read-completeness spec § F1 rows 44/45/46/47, Decision d).

The agenda meeting-block family is a container tree: 44 (agenda) / 45 (agenda_item)
/ 47 (agenda_item_content) are empty structural wrappers holding children, and 46
(agenda_item_title) carries the title inline run in its OWN ``elements`` (NOT in
children). This story registers **dedicated** handlers so agenda renders as a
proper structured tree — it no longer rides the S1 unknown-type fallback (that
would leave an ``Unknown block type`` warn for a type we actually support).

- 44 / 45 / 47 → registered **transparent** handlers (the view/grid own-depth
  recurser precedent): each carries its child NODES and the renderer emits them
  with no markup of the wrapper's own; NO ``Unknown block type`` warn.
- 46 → a real handler that renders the title text from ``elements`` via
  ``build_inline`` (the text/heading inline path); a populated title emits its
  text, an empty ``elements`` emits nothing (no dangling marker); ``align`` is
  dropped (visual, no MD form).
"""
import json
import logging

from harness import FIXTURES_DIR, build_blocks, render


def _parser_with(blocks):
    from larkdocio.read.config import Config
    from larkdocio.read.parser import Parser

    parser = Parser(Config())
    parser.block_map = {b.block_id: b for b in blocks}
    return parser


def _load_agenda_fixture():
    return json.loads((FIXTURES_DIR / "agenda.input.json").read_text(encoding="utf-8"))


# --- AC1: registered transparent handlers for 44 / 45 / 47 -------------------

def test_agenda_44_45_47_registered():
    """The three structural wrappers each have a registered handler — so they no
    longer ride the unknown-type fallback."""
    from larkdocio.blocks import get_registry

    registry = get_registry()
    for t in (44, 45, 47):
        assert t in registry, f"block type {t} has no registered handler"


def test_agenda_transparent_handlers_build_transparent_nodes():
    """44 / 45 / 47 build a node carrying their child NODES (via ``_child_nodes``
    at their own depth), the view/grid transparent precedent."""
    from larkdocio.model import (
        AgendaItemContentNode,
        AgendaItemNode,
        AgendaNode,
    )

    blocks = build_blocks([
        {"block_id": "ag", "block_type": 44, "agenda": {}, "children": ["ai"]},
        {"block_id": "ai", "parent_id": "ag", "block_type": 45,
         "agenda_item": {}, "children": ["ac"]},
        {"block_id": "ac", "parent_id": "ai", "block_type": 47,
         "agenda_item_content": {}, "children": ["b"]},
        {"block_id": "b", "parent_id": "ac", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "body"}}]}},
    ])
    parser = _parser_with(blocks)

    ag = parser.parse_docx_node(blocks[0], 0)
    assert isinstance(ag, AgendaNode)
    assert isinstance(ag.children[0], AgendaItemNode)
    assert isinstance(ag.children[0].children[0], AgendaItemContentNode)


def test_agenda_wrappers_emit_no_own_markup_and_no_warn(caplog):
    """A transparent 44/45/47 subtree surfaces its descendant body text with NO
    markup of the wrappers themselves, and — being registered — emits NO
    ``Unknown block type`` warning for 44/45/47."""
    blocks = [
        {"block_id": "root", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "T"}}]},
         "children": ["ag"]},
        {"block_id": "ag", "parent_id": "root", "block_type": 44,
         "agenda": {}, "children": ["ai"]},
        {"block_id": "ai", "parent_id": "ag", "block_type": 45,
         "agenda_item": {}, "children": ["ac"]},
        {"block_id": "ac", "parent_id": "ai", "block_type": 47,
         "agenda_item_content": {}, "children": ["b"]},
        {"block_id": "b", "parent_id": "ac", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "surfaced body"}}]}},
    ]
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        out = render(blocks, doc_id="root")

    assert "surfaced body" in out, out
    # Transparent: no wrapper type numbers leak into the output.
    for t in ("44", "45", "47"):
        assert t not in out, out
    # Registered → no unknown-type warning for the agenda structural wrappers.
    unknown = [r.getMessage() for r in caplog.records
               if r.levelno == logging.WARNING and "Unknown block type" in r.getMessage()]
    assert not unknown, unknown


# --- AC2: real handler for 46 agenda_item_title ------------------------------

def test_agenda_title_46_registered_and_builds_title_node():
    """46 has a dedicated handler that builds an AgendaItemTitleNode carrying the
    title's inline sequence from ``elements``."""
    from larkdocio.blocks import get_registry
    from larkdocio.model import AgendaItemTitleNode, Text

    assert 46 in get_registry()

    blocks = build_blocks([
        {"block_id": "t", "block_type": 46,
         "agenda_item_title": {"elements": [{"text_run": {"content": "Topic"}}],
                               "align": 1}},
    ])
    node = _parser_with(blocks).parse_docx_node(blocks[0], 0)
    assert isinstance(node, AgendaItemTitleNode)
    assert node.content == [Text("Topic")]


def test_agenda_title_populated_emits_text():
    """A populated 46 title renders its text on its own line."""
    blocks = [
        {"block_id": "t", "block_type": 46,
         "agenda_item_title": {"elements": [{"text_run": {"content": "Topic A"}}],
                               "align": 1}},
    ]
    out = render(blocks, doc_id="t")
    assert out == "Topic A\n", repr(out)


def test_agenda_title_empty_elements_emits_nothing():
    """An empty ``elements`` (or absent title) emits nothing — no dangling marker
    / no stray blank line."""
    # Empty elements list.
    blocks = [{"block_id": "t", "block_type": 46, "agenda_item_title": {"elements": []}}]
    assert render(blocks, doc_id="t") == "", repr(render(blocks, doc_id="t"))

    # A single empty text_run (renders to "") — still nothing.
    blocks2 = [{"block_id": "t", "block_type": 46,
                "agenda_item_title": {"elements": [{"text_run": {"content": ""}}]}}]
    assert render(blocks2, doc_id="t") == "", repr(render(blocks2, doc_id="t"))


def test_agenda_title_styled_run_renders():
    """The 46 title routes through the standard inline path, so a styled run
    renders exactly like a heading line would."""
    blocks = [
        {"block_id": "t", "block_type": 46,
         "agenda_item_title": {"elements": [
             {"text_run": {"content": "Bold topic",
                           "text_element_style": {"bold": True}}}]}},
    ]
    assert render(blocks, doc_id="t") == "**Bold topic**\n", repr(render(blocks, doc_id="t"))


# --- AC3: the S0 agenda fixture renders the full structured subtree ----------

def test_agenda_fixture_renders_titles_and_body():
    """The S0 agenda fixture drives the family: both titles surface (via the 46
    handler) and the body text surfaces (via the transparent 47 wrapper); empty
    body paragraphs / titles emit nothing beyond their blank line."""
    out = render(_load_agenda_fixture(), doc_id="root")

    assert "Agenda topic 1 — self-referential sample" in out, out
    assert "Agenda title 1" in out, out
    assert "Agenda body text - level 1" in out, out


def test_agenda_fixture_no_unknown_warn(caplog):
    """The agenda fixture no longer rides the unknown-type fallback: registering
    44/45/46/47 means ZERO ``Unknown block type`` warnings for the subtree."""
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        render(_load_agenda_fixture(), doc_id="root")

    unknown = [r.getMessage() for r in caplog.records
               if r.levelno == logging.WARNING and "Unknown block type" in r.getMessage()]
    assert not unknown, unknown
