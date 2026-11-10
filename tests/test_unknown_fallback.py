"""Unknown-type fallback = warn + render children transparently (LD-045).

The read-completeness spec § F1b + Decision (e). Today the parser's unregistered-type branch warns
ONCE and drops the block AND its entire subtree (it never recurses into
children). The zoo proved the cost: an unregistered type-44 agenda dropped 8-9
descendant blocks — a populated title + real body text — behind a single warning
(the LD-040 file-in-view failure generalized to any unknown CONTAINER type).

The new contract (Decision e): an unregistered type still **warns once** (naming
the type + block_id, unchanged message shape) but now **recurses its children
transparently** — building child nodes at the block's own depth, emitted with no
markup of the unknown block's own (the view/grid own-depth-recurser precedent).
A leaf unknown (no children) still emits nothing.

Design ruling (AC2): this is the net for GENUINELY unknown types ONLY. Known
types keep their registered handlers, so the "Unknown block type N" warn stays a
meaningful signal — a known type must never silently ride the fallback.
"""
import logging

from harness import build_blocks, render


def _parser_with(blocks):
    from larkdocio.read.config import Config
    from larkdocio.read.parser import Parser

    parser = Parser(Config())
    parser.block_map = {b.block_id: b for b in blocks}
    return parser


# --- AC1: unknown CONTAINER surfaces its children transparently --------------

def test_unknown_container_renders_children_transparently(caplog):
    """An unregistered CONTAINER type surfaces its descendant text instead of
    dropping the whole subtree — with NO markup of its own (transparent)."""
    blocks = [
        {"block_id": "root", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "T"}}]},
         "children": ["unk"]},
        # 9997 is not a registered type; it wraps a real text child.
        {"block_id": "unk", "block_type": 9997, "parent_id": "root",
         "children": ["kid"]},
        {"block_id": "kid", "block_type": 2, "parent_id": "unk",
         "text": {"elements": [{"text_run": {"content": "surfaced body"}}]}},
    ]
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        out = render(blocks, doc_id="root")

    # The child's text is surfaced, not dropped.
    assert "surfaced body" in out, out
    # Transparent: no wrapper markup of the unknown block itself leaked in.
    assert "9997" not in out, out
    # It STILL warns once, naming the type + block_id (unchanged message shape).
    unknown = [r.getMessage() for r in caplog.records
               if r.levelno == logging.WARNING and "Unknown block type 9997" in r.getMessage()]
    assert len(unknown) == 1, unknown
    assert "block_id=unk" in unknown[0], unknown[0]


def test_leaf_unknown_emits_nothing_but_still_warns(caplog):
    """A leaf unknown (no children, e.g. `999 {}`) still emits nothing and warns."""
    blocks = [
        {"block_id": "root", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "T"}}]},
         "children": ["leaf"]},
        {"block_id": "leaf", "block_type": 999, "parent_id": "root",
         "undefined": {}},
    ]
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        out = render(blocks, doc_id="root")

    # Page title only; the leaf contributed nothing.
    assert out == "# T\n\n\n", repr(out)
    assert any("Unknown block type 999" in r.getMessage() for r in caplog.records)


def test_unknown_container_recurses_at_own_depth_via_child_nodes():
    """The fallback builds child NODES via the shared `_child_nodes` primitive at
    the block's OWN depth (the view/grid precedent) — proven by a nested unknown
    surfacing a deep text child."""
    blocks = [
        {"block_id": "root", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "T"}}]},
         "children": ["a"]},
        {"block_id": "a", "block_type": 9996, "parent_id": "root", "children": ["b"]},
        {"block_id": "b", "block_type": 9995, "parent_id": "a", "children": ["c"]},
        {"block_id": "c", "block_type": 2, "parent_id": "b",
         "text": {"elements": [{"text_run": {"content": "deep"}}]}},
    ]
    out = render(blocks, doc_id="root")
    assert "deep" in out, out


# --- AC2: design ruling — known types keep handlers; warn stays meaningful ----

def test_known_type_uses_its_handler_not_the_fallback(caplog):
    """A KNOWN type resolves to its registered handler's node and does NOT warn —
    so the `Unknown block type N` warn stays a meaningful signal for genuinely
    unknown types (a known type must never silently ride the fallback)."""
    from larkdocio.model import DividerNode, UnknownBlockNode

    blocks = build_blocks([{"block_id": "d", "block_type": 22, "divider": {}}])
    parser = _parser_with(blocks)
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        node = parser.parse_docx_node(blocks[0], 0)

    assert isinstance(node, DividerNode)
    assert not isinstance(node, UnknownBlockNode)
    assert not any("Unknown block type" in r.getMessage() for r in caplog.records)


def test_registering_a_handler_removes_a_type_from_the_fallback(caplog):
    """Verifiable design ruling (AC2): an unregistered type warns + rides the
    transparent fallback; registering a handler for that same type removes it
    from the fallback path (handler node, no warn)."""
    from larkdocio.model import DividerNode, UnknownBlockNode

    blocks = build_blocks([{"block_id": "x", "block_type": 9994, "children": []}])
    parser = _parser_with(blocks)

    # Unregistered -> warns + transparent fallback node.
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        node = parser.parse_docx_node(blocks[0], 0)
    assert isinstance(node, UnknownBlockNode)
    assert any("9994" in r.getMessage() for r in caplog.records)

    # Register a handler for 9994 on a COPY of this parser's registry (never
    # mutate the shared global) -> no fallback, no warn.
    caplog.clear()
    parser.registry = dict(parser.registry)
    parser.registry[9994] = lambda p, b, il: DividerNode()
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        node2 = parser.parse_docx_node(blocks[0], 0)
    assert isinstance(node2, DividerNode)
    assert not any("9994" in r.getMessage() for r in caplog.records)


# --- AC3: agenda has LEFT the fallback (S2/LD-046 registered its handlers) -----

def _load_agenda_fixture():
    import json

    from harness import FIXTURES_DIR

    return json.loads((FIXTURES_DIR / "agenda.input.json").read_text(encoding="utf-8"))


def test_agenda_no_longer_rides_the_fallback(caplog):
    """S2/LD-046 registered dedicated agenda handlers (44/45/47 transparent + a
    real 46 title handler), so the agenda family is a KNOWN type now: it must NOT
    warn and must NOT ride this transparent-fallback path anymore — the design
    ruling (AC2) that registering a handler removes a type from the fallback,
    proven end-to-end on the real S0 agenda fixture.

    At S1/LD-045 this same fixture surfaced only its body text (via the
    fallback's transparent CHILDREN recursion) while warning 7 times and leaving
    the type-46 titles (whose text lives in their own `elements`, not children)
    unsurfaced. Now the registered handlers surface BOTH the titles and the body,
    with zero `Unknown block type` warnings. The generalized "unknown container
    surfaces its subtree" guard lives in
    ``test_unknown_container_renders_children_transparently`` above (it uses a
    synthetic unknown type, not agenda).
    """
    blocks = _load_agenda_fixture()
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        out = render(blocks, doc_id="root")

    # Zero unknown-type warnings: agenda is registered, so it left the fallback.
    unknown = [r.getMessage() for r in caplog.records
               if r.levelno == logging.WARNING and "Unknown block type" in r.getMessage()]
    assert not unknown, unknown

    # Both the titles (via the 46 handler) and the body (via the transparent 47
    # wrapper) surface — no longer dropped or partially surfaced.
    assert "Agenda title 1" in out, out
    assert "Agenda topic 1 — self-referential sample" in out, out
    assert "Agenda body text - level 1" in out, out
