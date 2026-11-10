"""Shared block-fixture builders for the parser tests.

Type-N block dicts (``parse_docx_content``'s input shape) that had been
re-authored byte-identically across several family test files (the maintainer's
multi-agent-drift concern; LD-039 consolidation). Kept in a plain importable
module beside ``harness.py`` — ``conftest.py`` puts this ``tests/`` directory on
``sys.path`` — so a change to a payload shape (API-drift is an expected hazard,
PROJECT.md § "API-drift is expected") is edited in exactly one place instead of
five.

Scope: only the *byte-identical builder functions* live here. Each test keeps
its own inline block-dict literals wherever those literals are the readable
per-test spec (test-quality § 3C) — they are not hidden behind a builder.
"""


def text_block(bid, parent, content):
    """A type-2 text block carrying a single ``text_run`` of ``content``."""
    return {
        "block_id": bid,
        "parent_id": parent,
        "block_type": 2,
        "text": {"elements": [{"text_run": {"content": content}}]},
        "children": [],
    }


def heading1(bid, parent, content, child_ids):
    """A type-3 heading1 block with ``child_ids``."""
    return {
        "block_id": bid,
        "parent_id": parent,
        "block_type": 3,
        "heading1": {"elements": [{"text_run": {"content": content}}]},
        "children": list(child_ids),
    }


def page(*child_ids):
    """A type-1 page root (id ``root``, title ``T``) carrying ``child_ids``."""
    return {
        "block_id": "root",
        "parent_id": "doc",
        "block_type": 1,
        "page": {"elements": [{"text_run": {"content": "T"}}]},
        "children": list(child_ids),
    }


def table(bid, parent, col_size, child_ids, extra=None):
    """A type-31 table block; ``extra`` merges into the table property dict."""
    prop = {"column_size": col_size}
    if extra:
        prop.update(extra)
    return {
        "block_id": bid,
        "parent_id": parent,
        "block_type": 31,
        "table": {"property": prop},
        "children": list(child_ids),
    }


def cell(bid, parent, child_ids):
    """A type-32 table_cell block carrying ``child_ids``."""
    return {
        "block_id": bid,
        "parent_id": parent,
        "block_type": 32,
        "table_cell": {},
        "children": list(child_ids),
    }
