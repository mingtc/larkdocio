"""LD-033 (R-S0 net, AC2) — kill the 4 GENUINE renderer survivors, test-first.

The extended-scope mutation re-baseline (dev/mutation-baseline-2026-07-24-extended.md)
put model/renderer.py at 96.0% — 19 survivors, of which ~15 are provably
equivalent (do not chase). The 4 GENUINE gaps are all in the markdown-table path
+ the quote-container rstrip, unexercised by any prior test. These pins each go
RED under the named mutant and GREEN on develop (hand-applied mutant → RED →
revert → GREEN, recorded in the LD-033 issue Activity). They target the renderer
directly via the model/unit path — the handler already applies `or 1` to
col_size, so renderer.py:338 is only reachable by constructing the node.

KEEP (LD-096, mindfulness not immunity): the mutation-kill holder for the 4
genuine renderer survivors — markdown-cell newline -> ``<br>`` join, ragged-final-
row padding (``rows[-1]``), falsy ``col_size`` -> 1, and ``_quote_container``
``rstrip("\\n")`` (newlines-only, spaces/tabs preserved). Each is reachable only
by constructing the node directly; not held by any doc golden. A future audit
may revisit.
"""
from larkdocio.model import MarkdownRenderer, QuoteContainerNode, RawBlock, TableNode


def _render(node):
    return MarkdownRenderer().render(node)


def test_markdown_cell_newlines_join_with_br():
    """A multiline markdown-table cell joins its newlines with ``<br>`` so the
    lines stack in a GitHub-style renderer while the pipe-row stays one physical
    line (LD-041 consented output change; was a space-collapse before). Kills the
    `raw.replace("\\n", "<br>")` survivor: only the HTML/merge path elsewhere had a
    multiline cell before this."""
    node = TableNode(cells=["line1\nline2", "H2", "a", "b"],
                     col_size=2, header_row=True, merges=[])
    out = _render(node)
    assert "line1<br>line2" in out
    assert "line1 line2" not in out, "cell newline was not joined with <br>"
    assert "line1\nline2" not in out, "literal newline leaked into the pipe row"


def test_ragged_final_row_padded_in_three_row_table():
    """renderer.py:353-354 — the RAGGED FINAL row of a >=3-row table is padded to
    col_size (`rows[-1].extend(...)`). Kills the `rows[-1]` -> `rows[+1]` survivor:
    with >=3 rows, `rows[+1]` is the SECOND row (index 1), so the mutant pads the
    wrong (already-full) middle row and leaves the true final row short."""
    # col_size 2, 5 cells -> rows [A,B] [C,D] [E]; the final [E] is ragged.
    node = TableNode(cells=["A", "B", "C", "D", "E"],
                     col_size=2, header_row=True, merges=[])
    out = _render(node)
    # Correct: the FINAL row is padded to 2 columns.
    assert "| E |  |" in out, "ragged final row was not padded to col_size"
    # Correct: the middle row stays exactly 2 columns (the mutant over-pads it).
    assert "| C | D |\n" in out
    assert "| C | D |  |" not in out, "the wrong (middle) row was padded"


def test_falsy_col_size_defaults_to_one():
    """renderer.py:338 — a falsy `col_size` defaults to 1 (`node.col_size or 1`),
    so each cell folds onto its own row. Kills the `or 1` -> `or 2` survivor.
    Only reachable by constructing the node: the table handler already applies
    `or 1` before the node is built."""
    node = TableNode(cells=["A", "B"], col_size=0, header_row=True, merges=[])
    out = _render(node)
    # col_size 1 -> A is its own (header) row, B its own data row.
    assert "| A |\n" in out
    assert "| B |\n" in out
    # The `or 2` mutant would fold both onto one row.
    assert "| A | B |" not in out, "falsy col_size did not default to 1"


def test_quote_container_child_trailing_spaces_preserved():
    """renderer.py:468 — `_quote_container` rstrips only trailing NEWLINES
    (`rstrip("\\n")`), so a child line ending in trailing spaces/tabs keeps them.
    Kills the `rstrip("\\n")` -> `rstrip(None)` survivor, which would strip all
    trailing whitespace (spaces + tabs), not just newlines."""
    node = QuoteContainerNode(children=[RawBlock("keep spaces   \n")])
    out = _render(node)
    assert "> keep spaces   \n" in out, (
        "trailing spaces were stripped — rstrip must target only newlines"
    )

    # And a trailing tab is likewise preserved (rstrip(None) would eat it too).
    node_tab = QuoteContainerNode(children=[RawBlock("keep tab\t\n")])
    out_tab = _render(node_tab)
    assert "> keep tab\t\n" in out_tab
