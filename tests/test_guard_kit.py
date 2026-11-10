"""Direct unit tests for :mod:`guard_kit` — the shared matrix-guard seam (LD-242).

``guard_kit`` is the module the doc-reading guards share instead of each re-deriving the
repo root and re-rolling a Markdown-table row splitter. It is a *seam*, so it is tested
**directly** here rather than only through its users: a guard that silently starts parsing
more (or fewer) rows is exactly the failure this module could introduce everywhere at once.

The four cases AC1 names are the four that have actually bitten a hand-rolled splitter in
this repo: a table inside a fenced code block, the ``|---|---|`` separator row, a ragged
row, and an escaped pipe.
"""

import pathlib
import re

import pytest

import guard_kit
from guard_kit import (REPO_ROOT, md_ragged_rows, md_table_cells, md_table_rows,
                       md_tables, section)

# --------------------------------------------------------------------------- #
# REPO_ROOT                                                                    #
# --------------------------------------------------------------------------- #


def test_repo_root_is_the_repo_root_not_the_tests_dir():
    assert isinstance(REPO_ROOT, pathlib.Path)
    assert REPO_ROOT.is_dir()
    assert (REPO_ROOT / "pyproject.toml").is_file(), REPO_ROOT
    assert (REPO_ROOT / "tests" / "guard_kit.py").is_file(), REPO_ROOT
    assert REPO_ROOT.name != "tests"


def test_repo_root_is_the_same_path_every_guard_used_to_re_derive():
    """The two idioms the migrated files used, byte-for-byte."""
    here = pathlib.Path(guard_kit.__file__).resolve()
    assert REPO_ROOT == here.parent.parent
    assert REPO_ROOT == here.parents[1]


# --------------------------------------------------------------------------- #
# md_table_cells — the one-row primitive                                       #
# --------------------------------------------------------------------------- #


def test_cells_splits_a_row_into_trimmed_cells():
    assert md_table_cells("| a | b | c |") == ["a", "b", "c"]


def test_cells_tolerates_leading_and_trailing_whitespace_on_the_line():
    assert md_table_cells("   | a | b |   ") == ["a", "b"]


def test_cells_of_a_ragged_row_are_just_its_own_cells():
    """AC1 — a ragged row (fewer cells than the header) is not padded, not dropped, not an
    error: the caller decides what a short row means."""
    assert md_table_cells("| a | b |") == ["a", "b"]
    assert md_table_cells("| a |") == ["a"]
    assert md_table_cells("| a | b | c | d | e |") == ["a", "b", "c", "d", "e"]


def test_cells_keeps_an_escaped_pipe_inside_one_cell():
    """AC1 — ``\\|`` is a literal pipe in Markdown, not a cell boundary."""
    assert md_table_cells(r"| a \| b | c |") == [r"a \| b", "c"]
    assert md_table_cells(r"| `x \| y` |") == [r"`x \| y`"]


def test_cells_does_not_unescape_the_escape():
    """The escape is *honoured*, not *removed* — the cell text is what the document says,
    so a guard comparing against the document keeps comparing against the document."""
    assert md_table_cells(r"| a \| b |")[0] == "a \\| b"


def test_cells_of_a_separator_row_are_its_dashes():
    assert md_table_cells("|---|:--|--:|") == ["---", ":--", "--:"]


def test_cells_of_an_empty_cell_is_the_empty_string():
    assert md_table_cells("| a |  | c |") == ["a", "", "c"]


def test_cells_survives_a_row_with_no_outer_pipes():
    assert md_table_cells("a | b") == ["a", "b"]


# --------------------------------------------------------------------------- #
# is_separator_row                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("line", ["|---|---|", "| --- | --- |", "|:---|---:|", "|-|-|"])
def test_separator_rows_are_recognised(line):
    assert guard_kit.is_separator_row(line)


@pytest.mark.parametrize("line", ["| a | b |", "| 1 | - |", "| -a- | b |"])
def test_content_rows_are_not_separator_rows(line):
    assert not guard_kit.is_separator_row(line)


# --------------------------------------------------------------------------- #
# md_table_rows — the document walk                                            #
# --------------------------------------------------------------------------- #

_DOC = """\
# A document

| name | status |
|------|--------|
| one  | active |
| two  | parked |

Prose in between.

```markdown
| fake | row |
|------|-----|
| not  | real |
```

| ragged |
| a | b \\| c |
"""


def test_rows_yields_every_content_row_in_order():
    assert md_table_rows(_DOC)[:3] == [
        ["name", "status"],
        ["one", "active"],
        ["two", "parked"],
    ]


def test_rows_drops_the_separator_row():
    """AC1 — ``|---|---|`` is table *syntax*, never a row a guard should assert on."""
    assert ["---", "--------"] not in md_table_rows(_DOC)
    assert all(not all(set(c) <= set("-: ") for c in row) for row in md_table_rows(_DOC))


def test_rows_does_not_parse_a_table_inside_a_fenced_code_block():
    """AC1 — the whole point of fence-awareness: a table *shown* in a code sample is
    documentation, not data. A fence-blind walk asserts on the sample."""
    rows = md_table_rows(_DOC)
    assert ["fake", "row"] not in rows
    assert ["not", "real"] not in rows
    assert len(rows) == 5, rows


def test_rows_keeps_ragged_rows_and_escaped_pipes():
    rows = md_table_rows(_DOC)
    assert ["ragged"] in rows
    assert [r"a", r"b \| c"] in rows


def test_rows_reads_a_line_only_when_it_opens_and_closes_with_a_pipe():
    text = "| a | b |\nnot a row | at all\n| c | d |\n"
    assert md_table_rows(text) == [["a", "b"], ["c", "d"]]


def test_rows_of_a_document_with_no_table_is_empty():
    assert md_table_rows("# heading\n\njust prose\n") == []


def test_rows_closes_the_fence_it_opens():
    """An unbalanced fence must not swallow the rest of the document silently — a fence
    opened and closed leaves later tables readable."""
    text = "```\n| x | y |\n```\n| a | b |\n"
    assert md_table_rows(text) == [["a", "b"]]


def test_rows_honours_an_indented_fence():
    text = "  ```\n| x | y |\n  ```\n| a | b |\n"
    assert md_table_rows(text) == [["a", "b"]]


# --------------------------------------------------------------------------- #
# section — the fence-aware slice                                              #
# --------------------------------------------------------------------------- #

_SECTIONED = """\
# Title

intro

## Choose your level

body line

```python
# this comment is NOT a heading
print("| x | y |")
```

more body

## Next section

other body

### A deeper heading

deeper
"""


def test_section_returns_the_heading_and_its_body():
    got = section(_SECTIONED, "## Choose your level")
    assert got.startswith("## Choose your level")
    assert "body line" in got
    assert "more body" in got


def test_section_stops_at_the_next_same_or_higher_heading():
    got = section(_SECTIONED, "## Choose your level")
    assert "## Next section" not in got
    assert "other body" not in got


def test_section_keeps_a_deeper_heading_inside_the_section():
    got = section(_SECTIONED, "## Next section")
    assert "### A deeper heading" in got and "deeper" in got


def test_section_is_fence_aware_so_a_hash_comment_does_not_cut_it_short():
    """AC1 — the LD-132 failure mode: a ``# ``-prefixed comment inside a fenced sample
    looks exactly like an H1 to a line-anchored regex, which truncates the section and
    makes every content guard over it silently vacuous."""
    got = section(_SECTIONED, "## Choose your level")
    assert "# this comment is NOT a heading" in got
    assert "more body" in got, "the fenced comment cut the section short"


def test_section_missing_heading_is_a_loud_failure_not_an_empty_string():
    with pytest.raises(AssertionError) as exc:
        section(_SECTIONED, "## No such heading")
    assert "No such heading" in str(exc.value)


def test_section_of_the_last_section_runs_to_the_end():
    got = section(_SECTIONED, "### A deeper heading")
    assert got.strip().endswith("deeper")


# --------------------------------------------------------------------------- #
# md_tables / md_ragged_rows — the header-keyed accessor (LD-632)              #
# --------------------------------------------------------------------------- #

_TABLES_DOC = """\
# A document

| rule | emits |
|------|-------|
| plain | nothing special |
| escaped | a `\\|` inside one cell |

Prose in between.

| entry point | returns |
|---|---|
| read() | a string |

```markdown
| fake | row |
|------|-----|
| not  | real |
```
"""


def test_tables_keys_each_row_by_its_own_headers():
    tables = md_tables(_TABLES_DOC)
    assert [headers for headers, _rows in tables] == [["rule", "emits"],
                                                      ["entry point", "returns"]]
    assert tables[1][1] == [{"entry point": "read()", "returns": "a string"}]


def test_tables_keeps_the_row_whose_cell_carries_an_escaped_pipe():
    """THE LD-632 REGRESSION, at the seam. A naive ``strip("|").split("|")`` reads the escape
    as a boundary, yields three cells against two headers and drops the row — which is how
    /BASE.md's own **GFM safety** row went unchecked by the guard iterating those rows."""
    rows = md_tables(_TABLES_DOC)[0][1]
    assert [row["rule"] for row in rows] == ["plain", "escaped"]
    assert rows[1]["emits"] == r"a `\|` inside one cell", "the parse must not unescape"


def test_tables_does_not_read_a_table_inside_a_fenced_code_block():
    assert all(headers != ["fake", "row"] for headers, _rows in md_tables(_TABLES_DOC))


def test_tables_drops_the_separator_row():
    for _headers, rows in md_tables(_TABLES_DOC):
        assert all(not all(set(v) <= set("-: ") for v in row.values()) for row in rows)


def test_tables_of_a_document_with_no_table_is_empty():
    assert md_tables("# heading\n\njust prose\n") == []


def test_tables_reports_a_header_only_table_with_no_rows():
    """A table that declares columns and carries no data is a real shape (BASE.md's own
    "empty table" rendering rule is about exactly that), so it is returned with an empty row
    list rather than made to vanish."""
    assert md_tables("| a | b |\n|---|---|\n") == [(["a", "b"], [])]


def test_a_RAGGED_row_is_not_keyed_but_is_REPORTED():
    """The one omission, and the reason it is not a silence. There is no honest way to key a
    row against a header count it does not match — but the LD-632 defect *was* the dropping,
    so the drop is reportable and a guard can assert its own document has none."""
    doc = "| a | b |\n|---|---|\n| one | two |\n| one | two | three |\n"
    assert md_tables(doc) == [(["a", "b"], [{"a": "one", "b": "two"}])]
    assert md_ragged_rows(doc) == [(["a", "b"], ["one", "two", "three"])]


def test_ragged_rows_of_a_well_formed_document_is_empty():
    assert md_ragged_rows(_TABLES_DOC) == []


def test_ragged_rows_never_reports_a_row_inside_a_fence():
    doc = "```\n| a | b |\n|---|---|\n| one | two | three |\n```\n"
    assert md_ragged_rows(doc) == []


def test_tables_and_md_table_rows_agree_on_the_cells_they_share():
    """One splitter under both accessors — the property that makes the seam a seam."""
    from itertools import chain

    keyed = list(chain.from_iterable(
        [list(row.values()) for row in rows] for _headers, rows in md_tables(_TABLES_DOC)))
    assert all(cells in md_table_rows(_TABLES_DOC) for cells in keyed)


# --------------------------------------------------------------------------- #
# The floor — the seam has real users, and an orphaning deletion is visible.   #
# --------------------------------------------------------------------------- #

#: The guards migrated onto the seam by LD-242. A file dropping its import (or the seam
#: losing a user to a deletion) must be a visible decision, not a silent orphaning.
MIGRATED_USERS = (
    # LD-632 enrolled the header-keyed parses onto :func:`guard_kit.md_tables`: base_md.py
    # (whose own splitter dropped BASE.md's escaped-pipe row), test_base_surface_map.py, and
    # test_sheets_md_matrix.py (whose _split_row *was* md_table_cells's ancestor, kept as a
    # second copy of it until then).
    "base_md.py",
    "test_base_md_matrix.py",
    "test_base_surface_map.py",
    "test_sheets_md_matrix.py",
    "test_blocks_md_matrix.py",
    "test_doc_drift_guards.py",
    "test_doctrine_and_recipes.py",
    "test_guide.py",
    "test_levels_delineation.py",
    "test_mermaid_rules_matrix.py",
    "test_sheets_border_write.py",
    "test_sheets_merge_md_asymmetry.py",
)

_IMPORT_RE = re.compile(r"^\s*(?:from\s+guard_kit\s+import|import\s+guard_kit)\b", re.M)


def _importers():
    tests_dir = REPO_ROOT / "tests"
    return {
        p.name
        for p in tests_dir.rglob("*.py")  # LD-654: population must be recursive
        if p.name not in ("test_guard_kit.py", "guard_kit.py")
        and _IMPORT_RE.search(p.read_text(encoding="utf-8"))
    }


def test_every_migrated_guard_still_imports_the_seam():
    missing = sorted(set(MIGRATED_USERS) - _importers())
    assert not missing, (
        f"these guards were migrated onto guard_kit by LD-242 but no longer import it: "
        f"{missing} — if the guard was deleted, delete its entry here in the same change."
    )


def test_the_seam_is_not_an_unused_helper():
    assert len(_importers()) >= len(MIGRATED_USERS), (
        f"guard_kit has {len(_importers())} users in tests/; it landed with "
        f"{len(MIGRATED_USERS)}. A seam with no users is a helper waiting to rot."
    )


def test_the_carve_outs_are_not_migrated():
    """AC5 — the two standing 08-01 carve-outs. ``test_discovery_truth.py`` is the only
    non-fence-aware slicer (migrating it *widens* the guard — a behavior question, not a
    migration), and ``front_door.section_of_line`` / ``test_front_door_doctrine.py`` are
    documented as deliberately fence-blind."""
    for name in ("test_discovery_truth.py", "front_door.py", "test_front_door_doctrine.py"):
        text = (REPO_ROOT / "tests" / name).read_text(encoding="utf-8")
        assert not _IMPORT_RE.search(text), (
            f"{name} is a standing LD-242 carve-out and must not import guard_kit — "
            "migrating it changes what the guard catches."
        )
