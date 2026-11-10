"""LD-152 — guide/recipe completion for the Sheets surface (seat-session F1/F17/F19/F10/F4/F2/F5).

Every claim this issue adds is pinned at **content** level (the LD-132 lesson: a doc guard that
only checks a section *exists* goes vacuous the moment the section is reworded), and wherever a
claim restates something the code knows — a note kind, a poll bound, an op list, a recipe's
import path — the guard **derives** the expected value from the code instead of repeating it.
So a change in the engine reddens the doc, not the other way round.

The recipes themselves are executed by the LD-133 harness (``tests/guide_recipes.py`` +
``tests/test_discovery_truth.py`` §AC7, which parametrizes over ``RECIPE_SPECS``, so each new
recipe is executed, checked against what it produced, and proven to open no socket). The
harness **hole** that let an unrunnable line ship is closed in
``tests/test_guide_recipe_harness_hole.py``. This module is the *content* half.
"""
import re

import pytest

import guide_recipes as gr
from doc_prose import missing_phrases, prose
import capability_rows as rows
from larkdocio import capabilities, guide
from test_doctrine_and_recipes import _section

# --------------------------------------------------------------------------- #
# Shared readers.                                                              #
# --------------------------------------------------------------------------- #

#: The four families that shipped with no recipe (dogfood F1) → the recipe heading each got.
_FAMILY_RECIPES = {
    "structural": "### Recipe: insert and delete rows and columns (a structural write)",
    # LD-185 — the dimension-property family (row height / column width / hide-show).
    "dimension-property": (
        "### Recipe: set a row's height, a column's width, and hide a row "
        "(a dimension-property write)"),
    # LD-186 — the freeze-panes family (view state: which leading rows/columns stay pinned).
    "freeze-panes": (
        "### Recipe: freeze and unfreeze rows and columns (a freeze-panes write)"),
    # LD-188 — the cell-style family (fill / font / number-format), promoted into src/.
    "style": ("### Recipe: set a cell's fill, font, border and number format "
              "(a style write)"),
    "merge": "### Recipe: merge and unmerge cells",
    "dropdown": "### Recipe: add a dropdown list rule to a range",
    "tab": "### Recipe: add, copy and delete a tab",
}

_FIDELITY_HEADING = "### Recipe: read a sheet at style fidelity (the L2 export leg)"
_CLEAR_HEADING = "### Recipe: clear cells (there is no clear operation)"
_SHEETS_WRITE_HEADING = "### Recipe: the sheets write handshake"
_SHEET_READ_HEADING = "### Recipe: read a sheet to Markdown"


def _sheets_write_ops() -> dict:
    return rows.by_name(capabilities(full=True)["surfaces"]["sheets-write"], rows.OPERATION)


def _prose(section: str) -> str:
    """A section with its fenced code blocks removed — so a "the guide SAYS x" assertion
    cannot be satisfied by a code sample that merely mentions x."""
    return re.sub(r"```.*?```", "", section, flags=re.DOTALL)


def _export_bound_arms_missing(section: str) -> list:
    """Which arms of the derived export-bound check ``section`` FAILS — ``[]`` when it states
    the bound properly. The predicate with ONE home (LD-547).

    Extracted for the reason LD-512 extracted the read-back law's predicates: the bite proof
    at the foot of this file used to spell a *second copy* of this check over a string it had
    itself mutated, so it asserted that ``str.replace`` removes what it replaces and never
    asked the check that greens the shipped text.

    **Both arms are load-bearing, and the PROSE arm is why this is two arms and not one:** a
    mutation probe recorded at the original call site found the recipe's *code comment* alone
    satisfying a raw-text check while the paragraph had been paraphrased into "a bounded poll
    loop". A decision to turn the leg on is made while reading prose.
    """
    from larkdocio.sheets.export_reader import DEFAULT_MAX_POLLS

    needle = f"max_polls={DEFAULT_MAX_POLLS}"
    missing = []
    if needle not in _prose(section):
        missing.append("prose")
    if needle not in section:
        missing.append("raw")
    return missing


def _names_the_shipped_kind(section: str, kind: str) -> bool:
    """Does ``section`` quote the shipped note/refusal ``kind`` verbatim? — the doc-to-code
    agreement check, with ONE home (LD-547), called by both the green guard and the bite proof
    at the foot of this file (which used to hand-roll its own copy of it)."""
    return kind in section


# --------------------------------------------------------------------------- #
# AC1 — the four missing families each have a recipe that EXECUTES.             #
# --------------------------------------------------------------------------- #

def test_ac1_every_sheets_write_op_capabilities_projects_has_a_recipe():
    """AC1 (bidirectional, derived): every op in ``capabilities()['sheets-write']`` is
    covered by a recipe, and the covering recipe is one the harness executes.

    Derived from the projection rather than a hand-list, so a **seventh** op added later
    ships with no recipe and reddens here — which is exactly how the four went missing."""
    covered = {
        "value": _SHEETS_WRITE_HEADING,
        "formula": "### Recipe: write a live formula into a sheet",
        **_FAMILY_RECIPES,
    }
    assert sorted(covered) == sorted(_sheets_write_ops()), (
        "a sheets-write op has no recipe (or a recipe claims an op that no longer exists)")
    executed = set(gr.SPEC_BY_SLUG)
    for op, heading in covered.items():
        slug = gr._slug(heading.split("### Recipe: ", 1)[1])
        assert slug in executed, f"the {op!r} recipe {slug!r} is not executed by the harness"


@pytest.mark.parametrize("family,heading", sorted(_FAMILY_RECIPES.items()))
def test_ac1_each_new_recipe_teaches_the_import_path_and_the_gate(family, heading):
    """AC1: each recipe carries the **import path** (dogfood F6: the request classes live in
    ``larkdocio.sheets.write_apply``, and nothing said so), the constructor call, and the
    full ``dry_run`` → ``apply`` flow — in the recipe's own code, not in prose."""
    slug = gr._slug(heading.split("### Recipe: ", 1)[1])
    source = gr.recipe_source(slug)
    assert "from larkdocio.sheets.write_apply import" in source, source
    assert "from larkdocio.sheets.write_client import SheetsWriteClient" in source, source
    assert "init_env(" in source, source
    assert "dry_run(" in source and "apply(" in source, source
    if family == "tab":
        # A tab op has no A1 range: its ids come from the REPLY, which is the same
        # "never a title" discipline in the shape that family actually has.
        assert "new_sheet_id" in source, source
    else:
        assert "query_tabs(" in source, (
            f"the {family!r} recipe must obtain a real sheet_id in-recipe, never a title")


@pytest.mark.parametrize("family,heading", sorted(_FAMILY_RECIPES.items()))
def test_ac1_each_new_recipe_uses_the_request_types_the_projection_names(family, heading):
    """AC1 (derived): the request classes a recipe actually constructs are ones
    ``capabilities()`` projects for that op — so a recipe cannot teach a class the registry
    does not have, and a renamed class reddens the recipe."""
    slug = gr._slug(heading.split("### Recipe: ", 1)[1])
    source = gr.recipe_source(slug)
    projected = _sheets_write_ops()[family]["request_types"]
    used = [name for name in projected if re.search(rf"\b{name}[(.]", source)]
    assert used, (
        f"the {family!r} recipe constructs none of its projected request types {projected}")


def test_ac1_the_recipes_quote_the_shipped_note_kinds_verbatim():
    """AC1: the new recipes speak **LD-150's shipped vocabulary**, and every name is read out
    of the code that produces it — never typed twice.

    This is the doc↔code agreement the AC asks for: if a note's ``kind`` is renamed, the
    string the guide quotes stops matching the string the engine emits, and this reddens."""
    from larkdocio.sheets.formula import OVERWRITES_LIVE_FORMULA_KIND
    from larkdocio.sheets.ops import no_merge_at_range_note, out_of_bounds_dimension_note
    from larkdocio.sheets.plan import Refusal
    from larkdocio.sheets.write_range import parse_write_range

    no_merge = no_merge_at_range_note("s!A1:B2", [])["kind"]
    out_of_bounds = out_of_bounds_dimension_note(
        {"major_dimension": "ROWS", "start_index": 99, "end_index": 100},
        {"row_count": 10},
    )["kind"]
    shape_mismatch = Refusal.shape_mismatch(
        target=parse_write_range("s!A1:B2"), values=[["x"]]).reason

    checks = (
        (_section(_FAMILY_RECIPES["merge"]), no_merge),
        (_section(_FAMILY_RECIPES["structural"]), out_of_bounds),
        (_section(_CLEAR_HEADING), OVERWRITES_LIVE_FORMULA_KIND),
        (_section(_CLEAR_HEADING), shape_mismatch),
    )
    for section, name in checks:
        assert _names_the_shipped_kind(section, name), (
            f"the recipe never names the shipped {name!r}")


def test_ac1_the_structural_recipe_teaches_the_removed_payloads_own_disclosures():
    """AC1: the delete recipe names the removed payload's **own** fields, including the
    ``values_trim`` narrowing (LD-150 / F12) — a trimmed payload that nothing explains is a
    new silence, and the guide is where the explanation belongs.

    The field names are read out of the shipped snapshot function's source rather than typed
    twice (the /SHEETS.md guard's marker-parse posture), so renaming a key in the engine
    reddens the guide."""
    import inspect

    from larkdocio.sheets import ops

    source = inspect.getsource(ops._snapshot_removed_dimension)
    section = _section(_FAMILY_RECIPES["structural"])
    for field in ("values_trim", "removed_merges", "a1_range"):
        assert f'"{field}"' in source, (
            f"{field!r} is no longer part of the removed payload — update the recipe")
        assert field in section, f"the delete recipe never names removed[{field!r}]"

    # ``values_trim`` additionally has to be EXPLAINED in prose, not merely printed: a
    # silently narrowed payload was the finding, so a sample that shows the key while the
    # paragraph explaining the narrowing has been dropped is the same silence again. (A
    # mutation probe removed exactly that paragraph and the section-level check above passed.)
    assert "values_trim" in _prose(section), (
        "the narrowing must be explained in the prose, not only shown in the code sample")


def test_ac1_the_structural_recipe_states_both_index_conventions():
    """AC1: the recipe states the trap the request objects exist to make inexpressible — the
    two endpoints read the same body in **opposite** conventions — and the convention tokens
    it quotes are the ones the request objects really emit."""
    from larkdocio.sheets.write_apply import DeleteRows, InsertRowsAt

    section = _section(_FAMILY_RECIPES["structural"])
    insert = InsertRowsAt("s", before_row=2, count=1).descriptor()["convention"]
    delete = DeleteRows("s", first=2, last=3).descriptor()["convention"]
    assert insert in section and delete in section, (insert, delete)
    low = _prose(section).lower()
    assert "opposite" in low, section
    assert "0-indexed" in low and "1-indexed" in low, section
    assert "inclusive" in low and "half-open" in low, section


def test_ac1_the_destructive_recipes_state_what_is_destroyed():
    """AC1: each destructive recipe says what it destroys **before** it says how to call it —
    a merge discards the covered values, a delete's loss is snapshot, a tab delete is not
    undoable."""
    merge = _prose(_section(_FAMILY_RECIPES["merge"])).lower()
    assert "anchor" in merge and "discard" in merge, merge

    structural = _prose(_section(_FAMILY_RECIPES["structural"])).lower()
    assert "removed payload" in structural, structural
    assert "refused" in structural, (
        "a delete whose loss cannot be snapshot is refused — the recipe must say so")

    tab = _prose(_section(_FAMILY_RECIPES["tab"])).lower()
    assert "not undoable" in tab or "not a backup" in tab, tab
    assert "removed_identity" in _section(_FAMILY_RECIPES["tab"])


def test_ac1_the_tab_recipe_teaches_the_id_comes_from_the_reply():
    """AC1: the tab recipe's load-bearing lesson — ``AddTab``/``CopyTab`` mint a **new**
    ``sheet_id`` you can only learn from the reply, so a create-then-use chain is more than
    one batch. (The sheets echo of the docx one-tree-one-batch rule.)"""
    section = _section(_FAMILY_RECIPES["tab"])
    assert "new_sheet_id" in section, section
    low = _prose(section).lower()
    assert "never the title" in low, section
    assert "three batches" in low or "not one" in low, section


# --------------------------------------------------------------------------- #
# AC2 — the standalone fidelity read, join included.                            #
# --------------------------------------------------------------------------- #

def test_ac2_the_fidelity_recipe_calls_the_shipped_join():
    """AC2 (Dev's documented call — ship the helper): the recipe joins with
    ``exported_by_sheet_id``, imported from the module that defines it, and the symbol
    resolves."""
    from larkdocio.sheets.export_reader import exported_by_sheet_id  # noqa: F401

    source = gr.recipe_source(gr._slug(_FIDELITY_HEADING.split("### Recipe: ", 1)[1]))
    assert "from larkdocio.sheets.export_reader import" in source, source
    assert "exported_by_sheet_id(tabs, workbook)" in source, source
    assert "render_spreadsheet(pairs, fidelity=" in source, source


def test_ac2_the_recipe_runs_the_whole_chain_token_to_render():
    """AC2: token → tabs → used ranges → export → parse → join → render. Every step is in
    the one recipe, so there is no "and then somehow get an ExportedSheet" gap."""
    source = gr.recipe_source(gr._slug(_FIDELITY_HEADING.split("### Recipe: ", 1)[1]))
    for step in ("spreadsheet_token", "query_sheets(", "read_used_range(",
                 "SheetsExportReader.from_read_credentials(", "read_workbook(",
                 "exported_by_sheet_id(", "render_spreadsheet("):
        assert step in source, f"the fidelity recipe never does {step!r}:\n{source}"


def test_ac2_the_join_is_a_row_in_the_sheets_matrix():
    """AC2 (the surface-change discipline): shipping a public helper on the Sheets surface
    means /SHEETS.md gains its row — the matrix is the source of truth for what the surface
    does, and its own guard proves the row's code anchor resolves."""
    from pathlib import Path

    sheets_md = (Path(__file__).resolve().parent.parent / "SHEETS.md").read_text(
        encoding="utf-8")
    assert "larkdocio.sheets.export_reader.exported_by_sheet_id" in sheets_md, (
        "the new public join has no /SHEETS.md row")
    row = next(ln for ln in sheets_md.splitlines()
               if "exported_by_sheet_id" in ln and ln.startswith("|"))
    # ``prose`` drops ``_`` with the other markup markers, so the identifier tokens are
    # checked on the raw row and only the wording goes through the normalizer.
    assert "title" in row and "sheet_id" in row, row
    assert "omitted" in prose(row), "the row must state the degrade rule"


def test_ac2_the_guide_explains_why_the_join_is_needed():
    """AC2: the join is explained where it is used — the export is title-keyed, the renderer
    is id-keyed — because "a title is never a sheet_id" is the trap the guide already teaches
    and this is the one place that trap is *required* work."""
    prose = _prose(_section(_FIDELITY_HEADING)).lower()
    assert "title" in prose and "sheet_id" in prose, prose
    assert "never a `sheet_id`" in prose or "never a sheet_id" in prose, prose
    assert "omitted" in prose or "values-only" in prose, (
        "the degrade path (a tab with no worksheet) must be documented")


# --------------------------------------------------------------------------- #
# AC3 — the flag's REAL cost, with the numbers derived from code.                #
# --------------------------------------------------------------------------- #

def test_ac3_the_export_cost_is_stated_and_the_numbers_match_the_code():
    """AC3: the fidelity section states the cost — an **async whole-workbook export task**
    (create → poll → download → unzip → parse), ~1.2 s measured, ~30 s worst case — and the
    bound is **derived**: the stated worst case equals the shipped
    ``max_polls × poll_interval``, so tightening either in code reddens the guide."""
    from larkdocio.sheets.export_reader import DEFAULT_MAX_POLLS, DEFAULT_POLL_INTERVAL

    section = _section(_FIDELITY_HEADING)
    low = _prose(section).lower()
    for phrase in ("async", "export task", "poll", "download", "unzip", "parse",
                   "whole-workbook"):
        assert phrase in low, f"the cost statement never mentions {phrase!r}"

    assert "1.2 s" in low or "1.2s" in low, "the measured cost is not stated"
    worst_case = int(DEFAULT_MAX_POLLS * DEFAULT_POLL_INTERVAL)
    assert f"{worst_case} s" in low or f"{worst_case}s" in low, (
        f"the guide must state the {worst_case}s worst case (max_polls "
        f"{DEFAULT_MAX_POLLS} x poll_interval {DEFAULT_POLL_INTERVAL})")
    # In the PROSE, not only in the recipe's comments: the decision to turn the leg on is
    # made while reading prose, and a mutation probe showed the code comment alone satisfied
    # this check while the paragraph had been paraphrased into "a bounded poll loop".
    prose_only = _prose(section)
    assert not _export_bound_arms_missing(section), (
        f"the guide does not state max_polls={DEFAULT_MAX_POLLS} in "
        f"{_export_bound_arms_missing(section)}: {prose_only}")
    assert f"poll_interval={DEFAULT_POLL_INTERVAL}" in prose_only, prose_only


def test_ac3_the_third_scope_is_named_where_the_flag_is_described():
    """AC3: ``drive:export`` is a **third** scope, on top of the read scopes — the fact that
    made the flag look free. Named in the recipe *and* in the credentials/matrix rows that
    describe the leg."""
    section = _section(_FIDELITY_HEADING)
    assert "drive:export" in section, section
    assert "third" in _prose(section).lower(), section
    text = guide(full=True)
    assert text.count("drive:export") >= 3, (
        "the third scope must be discoverable from the credentials block and the matrix too")


# --------------------------------------------------------------------------- #
# AC5 — [[None]] is the clear, and there is no clear op.                         #
# --------------------------------------------------------------------------- #

def test_ac5_the_guide_says_there_is_no_clear_op_and_the_projection_agrees():
    """AC5 (derived): the guide states there is **no** clear operation, and
    ``capabilities()`` really has none — the claim is checked against the registry, not
    trusted."""
    assert "clear" not in _sheets_write_ops(), (
        "a clear op now exists — the guide's 'there is no clear operation' is stale")
    prose = _prose(_section(_CLEAR_HEADING)).lower()
    assert "no `clear` op" in prose or "no clear operation" in prose, prose
    assert "[[none]]" in prose, prose
    assert "absent" in prose, (
        "the point of None over '' is that the cell becomes genuinely absent")


def test_ac5_the_clear_snippet_is_a_runnable_recipe_with_a_none_matrix():
    """AC5: the snippet is a real recipe (so the harness runs it), and it writes ``None``
    cells shaped like the target rather than an empty string."""
    slug = gr._slug(_CLEAR_HEADING.split("### Recipe: ", 1)[1])
    assert slug in gr.SPEC_BY_SLUG
    source = gr.recipe_source(slug)
    matrix = "[[None, None], [None, None]]"
    assert matrix in source, source
    assert "read_values(" in source, "the recipe must show that the cells really cleared"
    # The prose's worked example must be the SAME matrix the code writes: a probe changed the
    # example to empty strings and nothing reddened, leaving the paragraph teaching `""` (which
    # does not clear) beside code that writes `None` (which does).
    assert matrix in _prose(_section(_CLEAR_HEADING)), (
        "the prose example and the recipe's matrix disagree")


def test_ac5_the_clear_recipe_warns_about_destroying_a_live_formula():
    """AC5: clearing is the operation that destroys formulas, so the recipe pairs the clear
    with the ``overwrites-live-formula`` note (LD-150's F9 disclosure) — including *why* the
    plan's ``before`` cannot show it."""
    from larkdocio.sheets.formula import COMPUTED_RENDER_OPTION

    section = _section(_CLEAR_HEADING)
    assert "overwrites-live-formula" in section, section
    assert COMPUTED_RENDER_OPTION in section, (
        f"the recipe must name the render option ({COMPUTED_RENDER_OPTION}) under which a "
        f"formula hides as data")
    assert "FormulaWriteRequest" in section, (
        "the recipe must name the alternative for rewriting a formula")


# --------------------------------------------------------------------------- #
# AC6 — write/README.md is reachable (Dev's documented call: an accessor).       #
# --------------------------------------------------------------------------- #

def test_ac6_the_writer_brief_is_a_public_accessor_returning_the_packaged_text():
    """AC6 (Dev's documented call — expose it): the cited document is reachable from an
    installed wheel by the same mechanism ``guide()`` uses.

    Dropping the citation was the alternative and would have been wrong: the claim is TRUE
    (``write/README.md`` really is packaged), so the gap was a missing accessor, not a false
    sentence. This is the ``guide()`` precedent applied a second time."""
    import importlib.resources as ir

    import larkdocio

    assert callable(larkdocio.writer_brief)
    assert "writer_brief" in larkdocio.__all__
    text = larkdocio.writer_brief()
    assert isinstance(text, str) and text.strip()
    packaged = ir.files("larkdocio.write").joinpath("README.md").read_text(encoding="utf-8")
    assert text == packaged, "the accessor must read the PACKAGED resource, not a src/ path"
    assert "The composable Markdown dialect" in text, (
        "the accessor must return the document the guide cites for the long-form dialect")


def test_ac6_the_accessor_reads_a_resource_not_a_filesystem_path():
    """AC6: same contract as ``guide()`` — ``importlib.resources``, so it works from a
    vendored wheel where no ``src/`` tree exists."""
    from pathlib import Path

    import larkdocio

    src = (Path(larkdocio.__file__).parent / "guide.py").read_text(encoding="utf-8")
    assert "larkdocio.write" in src, (
        "writer_brief must resolve the write package's packaged resource")
    assert "open(" not in src and "Path(" not in src


def test_ac6_every_citation_of_the_writer_brief_names_the_accessor():
    """AC6 (block-level, the LD-132 anti-rot rule): **every** paragraph that points at
    ``write/README.md`` also says how to read it. A reachability note somewhere else in the
    guide does not help the consumer reading the paragraph that cites it."""
    blocks = [b for b in re.split(r"\n\n+", guide(full=True)) if "write/README.md" in b]
    assert blocks, "the guide must still cite the writer brief"
    for block in blocks:
        assert "writer_brief()" in block, (
            "a block cites write/README.md without saying how to read it:\n" + block)


def test_ac6_the_writer_brief_ships_in_the_wheel_declaration():
    """AC6: the accessor is only honest if the resource is packaged — the declaration that
    puts it in the wheel is asserted here (the built-wheel RECORD check lives in
    ``test_guide.py``'s packaging test for GUIDE.md and in ``test_packaging.py``)."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'"larkdocio\.write"\s*=\s*\[[^\]]*README\.md', pyproject), pyproject


# --------------------------------------------------------------------------- #
# AC7 — seven request families vs six operations, reconciled.                    #
# --------------------------------------------------------------------------- #

_OP_COUNT_RE = re.compile(r"reports \*\*([a-z]+)\*\* `operations`")

# LD-213 AC6 — this module used to carry its OWN word→number table, topping out at ``"eight"``
# while its sibling in ``test_discovery_truth`` already reached ``"ten"``. The operations count
# WAS eight, so the next family adding a ninth **op** would have made this guard raise
# ``KeyError: 'nine'`` instead of failing with its own message — a guard that explodes tells the
# next Dev nothing about which document is wrong. There is now ONE table, read through ONE
# accessor that asserts.
from test_discovery_truth import count_word  # noqa: E402 - read at use, next to its rationale


def test_ac7_the_guide_reconciles_the_two_arities_against_the_projection():
    """AC7 (F2): the guide states **both** numbers and says why they differ, and both are
    cross-checked against ``capabilities()`` — so the two drift-guarded documents cannot
    disagree again, in either direction.

    The families count is already derived (``test_discovery_truth``); what was missing was
    the *reconciliation*: nothing told a consumer why the projection says six."""
    section = _section(_SHEETS_WRITE_HEADING)
    match = _OP_COUNT_RE.search(section)
    assert match, (
        "the sheets-write section must state how many `operations` capabilities() reports, "
        "in the form 'reports **<word>** `operations`'")
    stated = count_word(match.group(1))
    assert stated == len(_sheets_write_ops()), (
        f"the guide says capabilities() reports {match.group(1)} operations; it reports "
        f"{len(_sheets_write_ops())}")


def test_ac7_the_reconciliation_names_the_folded_request_family():
    """AC7: the *reason* is named — the rich-cell write is a request **type** of the ``value``
    op, not an op of its own — and that fold is verified in the projection itself."""
    ops = _sheets_write_ops()
    assert "RichCellWriteRequest" in ops["value"]["request_types"], ops["value"]
    assert "RichCellWriteRequest" not in ops, "rich-cell is now an op of its own"

    section = _section(_SHEETS_WRITE_HEADING)
    sentence = next(
        (s for s in re.split(r"(?<=\.)\s", _prose(section)) if _OP_COUNT_RE.search(s)), "")
    assert "RichCellWriteRequest" in sentence, (
        "the reconciliation must name the folded request family:\n" + sentence)
    assert "`value`" in sentence, sentence


def test_ac7_the_family_list_and_the_op_list_still_agree_with_the_registry():
    """AC7 (the other direction): the families the prose lists cover every projected op, so
    "seven families" cannot become a stale number when a family is added."""
    from test_discovery_truth import _expected_family_count, _named_families

    assert len(_named_families()) == _expected_family_count()
    assert _expected_family_count() == len(_sheets_write_ops()) + 1


# --------------------------------------------------------------------------- #
# LD-213 AC6 — the count-word table's ceiling, and the failure it used to hide. #
# --------------------------------------------------------------------------- #

def test_ld213_the_count_word_table_is_shared_not_copied():
    """AC6: ONE table. Two copies with two ceilings is the defect — and it is exactly the
    defect this whole issue exists to remove, one layer up in the guards themselves."""
    import test_discovery_truth as tdt

    assert count_word is tdt.count_word
    assert count_word("nine") == 9, "the table's old ceiling ('eight') is gone"
    assert count_word("**Twelve**") == 12, "the shared reader tolerates the bold marker"


def test_ld213_a_ninth_op_fails_this_guard_with_its_own_message_not_a_keyerror(monkeypatch):
    """AC6's evidence: with a ninth **op** simulated, the AC7 guard must fail with the sentence
    it was written to print. Before LD-213 this module's own ``_COUNT_WORDS`` stopped at
    ``"eight"``, so the same simulation raised ``KeyError: 'nine'`` from the lookup and told the
    next Dev nothing about which document was wrong."""
    real = _sheets_write_ops()
    monkeypatch.setitem(globals(), "_sheets_write_ops", lambda: {**real, "dummy-ninth": {}})

    with pytest.raises(AssertionError) as caught:
        test_ac7_the_guide_reconciles_the_two_arities_against_the_projection()
    assert "operations" in str(caught.value)
    assert "9" in str(caught.value), str(caught.value)


# --------------------------------------------------------------------------- #
# AC8 — the sheets URL → token step, and the validator's own message.            #
#                                                                                #
# SUPERSEDED IN PLACE (LD-183). AC8 shipped the two-line hand-rolled URL→token    #
# expression in BOTH sheets entry points on purpose, because the validator         #
# refused a sheets URL and no parser existed to reference — and it recorded the     #
# recommendation that closed the gap: accept /sheets/ and /base/ and return their   #
# type. That landed, so the assertions that pinned the workaround now pin the fix.  #
# Every side that still bites is kept: the recipes must still SHOW the step (it is  #
# the asymmetry with the docx recipes that made it necessary to show), the step is  #
# still EXECUTED rather than shown, the token it produces is pinned to what the     #
# old expression produced, and the message is still held to naming what is          #
# accepted. AC8's own acceptance test — the previously-accepted set and the         #
# ValueError type — is BELOW and untouched, which is what proves the widening did   #
# not move the contract.                                                           #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("heading", [_SHEET_READ_HEADING, _SHEETS_WRITE_HEADING])
def test_ac8_the_sheets_recipes_show_how_to_get_a_token_from_a_url(heading):
    """AC8 (F5), superseded: both sheets entry points still show the URL→token step — the
    docx recipes start from a URL and the sheets ones must not start from a bare token — but
    they now reference the **shipped call** instead of repeating the expression, which is the
    dedupe the parser made possible."""
    section = _section(heading)
    assert "/sheets/" in section, section
    assert "validate_download_url(url)" in section, (
        "the recipe must take the token with the shipped call")
    assert "urlparse" not in section, (
        "the hand-rolled two-liner is superseded — a recipe teaching it would send a "
        "consumer to re-implement the call it just made")


def test_ac8_the_two_lines_actually_produce_the_token():
    """AC8, superseded: the documented step is still EXECUTED rather than shown, against the
    same realistic URL (query string included) — and its result is pinned to what the
    hand-rolled expression produced, so the dedupe is proven behavior-preserving rather than
    assumed to be."""
    import urllib.parse

    from larkdocio.common import validate_download_url

    url = "https://your-domain.larksuite.com/sheets/Shtcn1234567890?sheet=3bf016"
    hand_rolled = urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]
    domain, url_type, token = validate_download_url(url)
    assert token == hand_rolled == "Shtcn1234567890"
    # …and the call answers the two things the expression could not.
    assert url_type == "sheets"
    assert domain == "larksuite.com"

    source = gr.recipe_source(gr._slug(_SHEET_READ_HEADING.split("### Recipe: ", 1)[1]))
    assert "validate_download_url(url)" in source, source


def test_ac8_the_validator_recognises_a_sheets_url_and_names_its_type():
    """AC8's message call, superseded by the fix it recommended: the validator no longer
    refuses a sheets URL at all — it recognises it and says what it is. ``allowHost`` is
    still named (it is the public CLI flag ``--allowHost`` and the function's own parameter,
    so naming it is help, not a leak), and the message is still held to naming **what is
    accepted** — now the wider set."""
    from larkdocio.common import validate_download_url

    assert validate_download_url(
        "https://your-domain.larksuite.com/sheets/Shtcn123") == (
            "larksuite.com", "sheets", "Shtcn123")

    # A genuinely-wrong URL still refuses, still as a ValueError, still actionably.
    with pytest.raises(ValueError) as exc:
        validate_download_url("https://your-domain.larksuite.com/minutes/MIN1")
    message = str(exc.value)
    for expected in ("docx", "wiki", "sheets", "base"):
        assert expected in message, (expected, message)
    assert "allowHost" in message, (
        "allowHost is the real public flag name; naming it is help, not a leak")


def test_ac8_the_validator_still_accepts_every_shape_it_accepted_before():
    """AC8: the message change is a message change — the accepted set is untouched."""
    from larkdocio.common import validate_download_url

    assert validate_download_url(
        "https://your-domain.larksuite.com/docx/ABC123") == ("larksuite.com", "docx", "ABC123")
    assert validate_download_url(
        "https://x.feishu.cn/wiki/WIK1") == ("feishu.cn", "wiki", "WIK1")
    assert validate_download_url(
        "https://x.feishu.cn/docs/DOC1") == ("feishu.cn", "docs", "DOC1")
    assert validate_download_url(
        "https://tenant.example.com/docx/T1", "example.com")[0] == "example.com"


# --------------------------------------------------------------------------- #
# AC9 — the doc-truth riders (backlog § E).                                     #
# --------------------------------------------------------------------------- #

def _sheets_md() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parent.parent / "SHEETS.md").read_text(encoding="utf-8")


def _limits_rows():
    """The rows of SHEETS.md's hard-limits table (found by its own signature column)."""
    from test_sheets_md_matrix import _find_table

    return _find_table("limit")


def test_ac9_sheets_md_documents_the_hard_limits_on_shipped_ops():
    """AC9: the ceilings a consumer hits at scale — and that larkdocio's own gates ride —
    are documented on the surface that claims those ops, not only in an audit doc."""
    rows = _limits_rows()
    assert rows, "/SHEETS.md must carry a hard-limits table"
    # PER ROW, not over the concatenation: a mutation probe deleted the values-write row and
    # the whole-table scan still passed, because another row happened to mention 5000. Each
    # ceiling has to be present ON a row that names the op it bounds.
    required = {
        "5000": "put_values",                      # values per write call
        "100": "put_values",                       # ... x 100 columns
        "50,000": "put_values",                    # chars per cell
        "10 MB": "read_values",                    # response ceiling
        "5000 ": "insert_dimension_range",         # dimension span
        "20/min": "harness",                       # the create tier
    }
    for needle, op in required.items():
        hit = [r for r in rows
               if needle.strip() in f"{r.get('limit','')} {r.get('value','')}"
               and op in r.get("applies to", "")]
        assert hit, (
            f"no hard-limit row states {needle!r} for {op!r} — the ceiling or the op it "
            f"bounds went missing")
    for row in rows:
        assert row.get("evidence", "").strip() not in {"", "—", "-", "n/a"}, (
            f"hard-limit row {row.get('limit')!r} carries no evidence link")


def test_ac9_the_limits_are_tied_to_the_ops_they_bound():
    """AC9: each limit says which shipped op it bounds — a bare number is trivia; a bounded op
    is a capability fact. Every named op really exists on the write client or in the
    projection."""
    from larkdocio.sheets.write_client import SheetsWriteClient

    rows = _limits_rows()
    applies = " ".join(r.get("applies to", "") for r in rows)
    for op in ("put_values", "read_values", "insert_dimension_range"):
        assert op in applies, f"no hard-limit row names {op!r}"
        assert hasattr(SheetsWriteClient, op), op
    assert "gate-scaling" in _sheets_md() or "gate" in applies, (
        "the create-tier limit is a gate-scaling ceiling — say so where it is documented")


def test_the_style_write_claim_reads_as_SHIPPED_and_no_longer_harness_only():
    """The row used to read ``spike-proven`` / **HARNESS-ONLY — there is NO shipped style
    write**, which was the truth: the wheel could READ style and not write it, and the only
    implementation lived in ``tests/sheets_write_harness.py``. LD-188 promoted it, so the same
    guard now holds the OPPOSITE claim — and still checks it against code truth in both
    directions, so neither the row nor the code can drift alone.

    (This is the flip its own predecessor predicted in so many words: *"if a real style write
    ever ships, this test reddens and the row has to be rewritten"*.)
    """
    from larkdocio.sheets.write_client import SheetsWriteClient

    assert sorted(n for n in dir(SheetsWriteClient)
                  if "style" in n.lower() and not n.startswith("_")) == [
        "batch_update_styles", "put_style"], (
        "the shipped client must carry BOTH style seams — the single-range write and the "
        "N-ranges-in-one-call batch")
    assert "style" in _sheets_write_ops(), _sheets_write_ops()

    for label in ("style write", "batch style write"):
        row = next((r for r in _sheets_md().splitlines()
                    if r.startswith(f"| {label} ")), None)
        assert row, f"/SHEETS.md has no `{label}` row"
        low = row.lower()
        assert "harness-only" not in low, (
            f"the `{label}` row still says HARNESS-ONLY after the promotion:\n{row}")
        assert "spike-proven" not in low, (
            f"the `{label}` row still reads spike-proven after the promotion:\n{row}")
        assert "shipped-ld-188" in low, (
            f"the `{label}` row must carry the shipped slug:\n{row}")


@pytest.mark.parametrize("doc", ["SHEETS.md", "GUIDE.md"])
def test_ac9_the_generic_90204_is_never_presented_as_a_specific_meaning(doc):
    """AC9: ``90204`` is Lark's **generic** ``WrongRequestBody`` code — the accompanying
    ``msg`` is what names the cause. Two of our docs over-specified it.

    Line-level, so a corrected sentence elsewhere cannot cover for a row that still reads
    "``90204`` = the colors error": every line naming the code must either mark it generic or
    carry the ``msg`` that distinguishes the case."""
    text = _sheets_md() if doc == "SHEETS.md" else guide(full=True)
    lines = [ln for ln in text.splitlines() if "90204" in ln]
    assert lines, f"{doc} no longer mentions 90204 — this guard has gone vacuous"
    for line in lines:
        assert re.search(r"generic|WrongRequestBody|id[- ]not[- ]found|id not found", line), (
            f"{doc} presents the bare 90204 as a specific meaning:\n{line}")
    assert "WrongRequestBody" in text, (
        f"{doc} must state once that 90204 is the generic WrongRequestBody code")


def test_ac9_the_writer_brief_credential_note_carries_the_test_suite_correction():
    """AC9: ``write/README.md``'s credential paragraph still carried the pre-LD-147 reading —
    that writes only ever go to a disposable — as if it were an engine restriction, in a
    document that **ships in the wheel**. It now states the same correction the two capability
    notes and the guide already state."""
    import larkdocio

    blocks = [b for b in re.split(r"\n\n+", larkdocio.writer_brief())
              if "Write credentials are used" in b]
    assert blocks, "the writer brief no longer describes write-credential use"
    for block in blocks:
        missing = missing_phrases(block, [
            "not an engine restriction",          # whose rule it is
            "this project's own test-suite policy",
            "may write to any document",          # what a consumer MAY do
        ])
        assert not missing, (
            f"the credential note still reads as an engine restriction (missing {missing}):"
            f"\n{block}")


def test_ac9_the_writer_brief_keeps_this_projects_own_rule():
    """AC9: the correction is about **whose** rule it is, not about relaxing it — larkdocio's
    own write gates still only ever touch a disposable the harness provisioned."""
    import larkdocio

    text = prose(larkdocio.writer_brief())
    for phrase in ("never a real document", "disposable"):
        assert phrase in text, f"the writer brief lost its own rule: {phrase!r}"


# --------------------------------------------------------------------------- #
# AC10 — the guards are not vacuous: one proven red-then-green.                  #
# --------------------------------------------------------------------------- #

def test_ac10_the_content_guards_bite_on_a_paraphrase():
    """AC10: the same comparison the live guards make is run against a **mutated** copy of
    the guide text and fails — so a reworded claim cannot pass silently.

    Both directions of the two riskiest couplings are exercised: the derived export bound
    (the numbers) and the derived note-kind vocabulary.

    **TRANSFORMED by LD-547**, for the reason LD-512 transformed the four ``…_BITES`` proofs
    in ``tests/test_read_back_law_and_restructure.py``. Both halves used to end on a
    hand-rolled second copy of the predicate — ``needle not in paraphrased`` — over a string
    this test had itself mutated, which asserts that ``str.replace`` removes what it replaces
    and says nothing about either guard. Each half now calls the predicate its green guard
    calls (:func:`_export_bound_arms_missing`, :func:`_names_the_shipped_kind`), so a
    loosening of either — dropping the prose arm, folding case, accepting a near-match —
    reddens HERE.
    """
    from larkdocio.sheets.export_reader import DEFAULT_MAX_POLLS
    from larkdocio.sheets.formula import OVERWRITES_LIVE_FORMULA_KIND

    section = _section(_FIDELITY_HEADING)
    assert not _export_bound_arms_missing(section), (
        "the shipped fidelity recipe does not state the bound even before crippling")
    paraphrased = section.replace(f"max_polls={DEFAULT_MAX_POLLS}", "a bounded poll loop")
    assert paraphrased != section, (
        "the mutation did not change anything — the guard would be vacuous")
    assert _export_bound_arms_missing(paraphrased) == ["prose", "raw"], (
        "the export-bound check ACCEPTED a paragraph paraphrased into 'a bounded poll loop' "
        "— the exact shape the probe recorded at its call site")

    clear = _section(_CLEAR_HEADING)
    assert _names_the_shipped_kind(clear, OVERWRITES_LIVE_FORMULA_KIND)
    renamed = clear.replace(OVERWRITES_LIVE_FORMULA_KIND, "a destructive note")
    assert renamed != clear, "nothing was renamed — the proof would be vacuous"
    assert not _names_the_shipped_kind(renamed, OVERWRITES_LIVE_FORMULA_KIND), (
        "the doc-to-code kind check ACCEPTED a recipe that no longer quotes the shipped kind")


def test_ac10_every_new_recipe_is_covered_by_the_execution_harness():
    """AC10: the recipes this issue adds are all in ``RECIPE_SPECS`` — the 1:1 guard in
    ``test_discovery_truth`` then forces every guide recipe to have an execution spec and
    vice-versa, so none of them can decay into an unexecuted sample."""
    added = [
        _FIDELITY_HEADING, _CLEAR_HEADING, *_FAMILY_RECIPES.values(),
    ]
    for heading in added:
        slug = gr._slug(heading.split("### Recipe: ", 1)[1])
        assert slug in gr.SPEC_BY_SLUG, f"{slug!r} has no execution spec"
        assert gr.recipe_source(slug).strip(), f"{slug!r} has no code"
