"""LD-098 — handler function-naming unification.

Pure rename: every block handler function converges on the ``handle_*``
convention (the majority form already used by headings.py, lists.py,
table.py, text.py, media.py, iframe.py, divider.py, container.py). Prior to
this issue, callout.py, file.py, quote.py, synced.py, diagram.py, and
embedded.py used the minority ``parse_docx_block_*`` convention.

Registration is by the ``@register_block(<int>)`` decorator, never by
function name, so the registry's int keys are NOT expected to change —
these tests assert the naming convention only; ``test_registry.py`` already
covers registry-key completeness/stability.
"""
import pathlib

import larkdocio.blocks as blocks_pkg

BLOCKS_DIR = pathlib.Path(blocks_pkg.__file__).parent


def test_all_registered_handlers_use_handle_prefix():
    """Every function registered via @register_block(...) is named handle_*.

    Before this rename, the handlers in callout.py, file.py, quote.py,
    synced.py, diagram.py, and embedded.py were named parse_docx_block_*,
    so this fails until the rename lands.
    """
    registry = blocks_pkg.get_registry()
    offenders = {
        block_type: handler.__name__
        for block_type, handler in registry.items()
        if not handler.__name__.startswith("handle_")
    }
    assert not offenders, (
        "Handler(s) not using the handle_* naming convention: "
        f"{offenders} — rename to handle_* (LD-098)."
    )


def test_no_parse_docx_block_references_remain_in_blocks_package():
    """No source file under larkdocio/blocks/ mentions the retired
    parse_docx_block_* name family — covers in-module call sites AND
    docstring cross-references (e.g. embedded.py's :func: refs into
    synced.py), not just the def lines themselves.
    """
    hits = []
    for py_file in sorted(BLOCKS_DIR.rglob("*.py")):  # LD-654: recursive population
        text = py_file.read_text(encoding="utf-8")
        if "parse_docx_block_" in text:
            for lineno, line in enumerate(text.splitlines(), start=1):
                if "parse_docx_block_" in line:
                    hits.append(f"{py_file.name}:{lineno}: {line.strip()}")
    assert not hits, "Dangling parse_docx_block_* reference(s):\n" + "\n".join(hits)
