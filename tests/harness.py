"""Shared test helpers: build real SDK Block objects from JSON and render.

Kept in a plain module (not conftest) so test files can ``from harness import
...`` reliably. ``conftest.py`` puts ``src/`` and this ``tests/`` directory on
``sys.path`` before this loads.
"""
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def build_blocks(block_dicts):
    """Turn a list of block dicts (parse_docx_content's input shape) into real
    SDK Block objects via the SDK's own ``init(...)`` deserializer."""
    from lark_oapi.api.docx.v1.model.block import Block

    return [Block(d) for d in block_dicts]


def render(block_dicts, doc_id=None):
    """Build SDK blocks from dicts and run the parser, returning markdown.

    If ``doc_id`` is omitted, the first block's id is used (conventionally the
    page/root block)."""
    from larkdocio.read.parser import Parser
    from larkdocio.read.config import Config

    blocks = build_blocks(block_dicts)
    if doc_id is None:
        doc_id = block_dicts[0]["block_id"]
    return Parser(Config()).parse_docx_content(doc_id, blocks)
