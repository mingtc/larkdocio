"""Indent-guard regression (fix indent-guard-1B).

A block-level child (table/code/divider) nested under a LIST ITEM must NOT be
prepended with a hard tab. The old behavior prepended ``'\\t' * indent_level``
for EVERY block, which turned a nested table's ``|...|`` lines into an indented
code block (4-space / tab indent => CommonMark code block), corrupting it.

The fix: only list-type blocks (bullet 12 / ordered 13 / todo 17) get the tab
indent; all other block types prepend no tab. This keeps nested-list rendering
intact (asserted in test_lists.py) while letting nested block-level children
render at column 0.

The reference-parser assertion uses ``markdown_it`` as a TEST-ONLY parser to
confirm the nested table is not mangled into a code block. It is an optional
test dependency (declared in the ``dev`` extra); when it is absent that one
assertion is skipped, but the parser-independent invariant below always runs.
"""
import json

import pytest

from harness import FIXTURES_DIR, render


def _render_fixture(name):
    block_dicts = json.loads(
        (FIXTURES_DIR / f"{name}.input.json").read_text(encoding="utf-8")
    )
    return render(block_dicts)


def test_nested_table_row_has_no_leading_indent():
    """Parser-independent invariant: the nested table's pipe rows carry no
    leading tab/space indent (which would corrupt them into a code block), and
    the bullet text + all cells survive. Always runs (no optional deps)."""
    out = _render_fixture("bullet_nested_table")

    pipe_lines = [ln for ln in out.splitlines() if ln.lstrip().startswith("|")]
    assert pipe_lines, f"no table rows found in output:\n{out}"
    for ln in pipe_lines:
        assert not ln.startswith("\t"), f"table row is tab-indented (corrupts to code block): {ln!r}"
        assert not ln.startswith("    "), f"table row is space-indented: {ln!r}"

    assert "Item with a table" in out
    for cell in ("H1", "H2", "a", "b"):
        assert cell in out


def test_nested_table_parses_as_real_table_element():
    """Reference-parser assertion (test-only ``markdown_it``): the rendered
    nested table must parse into a real ``<table>`` element — not a code block,
    and not folded into the list item's paragraph as literal ``|`` pipes.

    A blank line must separate the list-item line from the breakout table so
    CommonMark terminates the list paragraph (LD-051). Merely "not a code block"
    (the prior, weaker assertion) passed even when the table was folded into the
    list paragraph as literal pipes; asserting a ``<table>`` element exists is
    the real contract. Skipped if the optional ``markdown-it-py`` dev dependency
    is not installed."""
    MarkdownIt = pytest.importorskip("markdown_it").MarkdownIt

    out = _render_fixture("bullet_nested_table")

    md = MarkdownIt("commonmark").enable("table")
    html = md.render(out)
    assert "<pre>" not in html and "<code>" not in html, (
        "nested table was mangled into an indented code block — the indent "
        f"guard did not take effect. HTML:\n{html}"
    )
    assert "<table>" in html, (
        "nested table did not parse as a real <table> — with no blank line "
        "separating the list line from the table, CommonMark lazy-continuation "
        f"folds the pipe rows into the list paragraph as literal text. HTML:\n{html}"
    )


# --- LD-033 R-S0: the tab-on-block-child invariant, pinned DEEP --------------
#
# The load-bearing indent invariant is parser-independent, so a bad golden
# regeneration during the flip (R-S1..R-S5) that `--update-golden` would
# otherwise BLESS is still caught here. A block-level (non-list) child of a list
# item — a code fence, a table pipe row — must carry NO leading tab/space,
# regardless of how deep its list ancestors are indented. The deep gauntlet
# fixtures put such children under 2- and 3-level list nesting.


@pytest.mark.parametrize(
    "fixture",
    ["block_child_under_deep_list", "deep_gauntlet"],
)
def test_block_child_under_deep_list_is_not_indented(fixture):
    """A code fence or table pipe row nested under a (possibly deep) list item
    renders at column 0 — no leading tab or 4-space indent that would corrupt it
    into a CommonMark indented-code block. Parser-independent (always runs)."""
    out = _render_fixture(fixture)
    lines = out.splitlines()

    fence_lines = [ln for ln in lines if ln.lstrip().startswith("```")]
    assert fence_lines, f"no code fence found in {fixture}:\n{out}"
    pipe_lines = [ln for ln in lines if ln.lstrip().startswith("|")]

    for ln in fence_lines + pipe_lines:
        assert not ln.startswith("\t"), (
            f"[{fixture}] block-level child is tab-indented "
            f"(corrupts to a code block): {ln!r}"
        )
        assert not ln.startswith("    "), (
            f"[{fixture}] block-level child is space-indented: {ln!r}"
        )


def test_deep_list_markers_deepen_by_one_tab_per_level():
    """The three list levels in deep_list_nesting carry 0, 1, 2 leading tabs —
    pinning the depth-threading the flip must preserve exactly."""
    out = _render_fixture("deep_list_nesting")
    assert "\n- Level 1\n" in out
    assert "\n\t- Level 2\n" in out
    assert "\n\t\t- Level 3\n" in out
