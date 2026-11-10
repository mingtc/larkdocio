"""Iframe (type 26) URL-as-link handler — S3 / LD-047 (the read-completeness spec § F1 row 26, Decision c).

An embedded iframe (type 26) carries a real URL in ``iframe.component.url``, but
that URL is **percent-encoded** (``https%3A%2F%2F…``). This story registers a
dedicated handler that emits the URL as a Markdown link, **decoding it first**
via the existing ``utils.url.unescape_url`` precedent — so the link is the real
``https://…`` target, not a broken percent-encoded string.

- AC1 — ``@register_block(26)`` builds an ``IframeNode`` carrying the DECODED url;
  the renderer emits ``[url](url)``. The percent-decode is mandatory.
- AC2 — a missing/empty ``component``/``url`` emits a **visible marker**
  (``[Iframe: missing url]``) — never a silent drop (the image ``[Image: missing
  token]`` precedent). ``iframe_type`` (15 known-provider vs 99 generic) is
  captured into the node but dropped at render (no portable Markdown form —
  consumed-into-model / dropped-at-render, like text colors LD-042).
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


def _load_iframe_fixture():
    return json.loads((FIXTURES_DIR / "iframe.input.json").read_text(encoding="utf-8"))


# --- AC1: registered handler builds a decoded-URL node -----------------------

def test_iframe_26_registered():
    """Type 26 has a registered handler — so it no longer rides the unknown-type
    fallback (a leaf unknown that silently emitted nothing)."""
    from larkdocio.blocks import get_registry

    assert 26 in get_registry(), "block type 26 (iframe) has no registered handler"


def test_iframe_handler_builds_decoded_url_node():
    """The handler builds an IframeNode carrying the percent-DECODED url and the
    captured iframe_type."""
    from larkdocio.model import IframeNode

    blocks = build_blocks([
        {"block_id": "if", "block_type": 26,
         "iframe": {"component": {"iframe_type": 15,
                                  "url": "https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DdQw4w9WgXcQ"}}},
    ])
    node = _parser_with(blocks).parse_docx_node(blocks[0], 0)
    assert isinstance(node, IframeNode)
    assert node.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert node.iframe_type == 15


def test_iframe_renders_decoded_markdown_link():
    """The renderer emits ``[url](url)`` with the DECODED url — never the
    percent-encoded raw string."""
    blocks = [
        {"block_id": "if", "block_type": 26,
         "iframe": {"component": {"iframe_type": 15,
                                  "url": "https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DdQw4w9WgXcQ"}}},
    ]
    out = render(blocks, doc_id="if")
    decoded = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert out == f"[{decoded}]({decoded})\n", repr(out)
    # The percent-encoding must be gone.
    assert "%3A" not in out and "%2F" not in out, out


def test_iframe_type_99_generic_also_decodes():
    """The generic (iframe_type 99) web-preview shape decodes exactly the same —
    both zoo iframe shapes are covered."""
    blocks = [
        {"block_id": "if", "block_type": 26,
         "iframe": {"component": {"iframe_type": 99,
                                  "url": "https%3A%2F%2Fwww.github.com%2F"}}},
    ]
    out = render(blocks, doc_id="if")
    assert out == "[https://www.github.com/](https://www.github.com/)\n", repr(out)


# --- AC2: robustness — missing/empty url emits a visible marker --------------

def test_iframe_missing_url_emits_marker():
    """An empty ``url`` emits a visible marker (never a silent drop / broken empty
    link) — the image ``[Image: missing token]`` precedent."""
    blocks = [
        {"block_id": "if", "block_type": 26,
         "iframe": {"component": {"iframe_type": 99, "url": ""}}},
    ]
    out = render(blocks, doc_id="if")
    assert out == "[Iframe: missing url]\n", repr(out)


def test_iframe_missing_component_emits_marker():
    """An absent ``component`` still emits the visible marker — never a silent
    drop."""
    blocks = [
        {"block_id": "if", "block_type": 26, "iframe": {}},
    ]
    out = render(blocks, doc_id="if")
    assert out == "[Iframe: missing url]\n", repr(out)


def test_iframe_absent_payload_emits_marker():
    """A type-26 block with no ``iframe`` payload at all still surfaces the marker
    rather than vanishing."""
    blocks = [
        {"block_id": "if", "block_type": 26},
    ]
    out = render(blocks, doc_id="if")
    assert out == "[Iframe: missing url]\n", repr(out)


def test_iframe_registered_emits_no_unknown_warn(caplog):
    """Being registered, type 26 emits NO ``Unknown block type`` warning."""
    blocks = [
        {"block_id": "root", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "T"}}]},
         "children": ["if"]},
        {"block_id": "if", "parent_id": "root", "block_type": 26,
         "iframe": {"component": {"iframe_type": 15,
                                  "url": "https%3A%2F%2Fexample.com%2F"}}},
    ]
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        render(blocks, doc_id="root")
    unknown = [r.getMessage() for r in caplog.records
               if r.levelno == logging.WARNING and "Unknown block type" in r.getMessage()]
    assert not unknown, unknown


# --- AC3: the S0 iframe fixture drives both shapes ---------------------------

def test_iframe_fixture_renders_both_decoded_links():
    """The S0 iframe fixture (iframe_type 15 YouTube + 99 GitHub, both percent-
    encoded urls) surfaces both as decoded Markdown links."""
    out = render(_load_iframe_fixture(), doc_id="root")
    assert "[https://www.youtube.com/watch?v=dQw4w9WgXcQ]" in out, out
    assert "[https://www.github.com/]" in out, out
    assert "%3A" not in out and "%2F" not in out, out
