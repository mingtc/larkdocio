"""LD-607 — the shipped guide says WHICH text it means: the reduction ladder, the node-class
index's basis, sub-span segmentation permanence, and the id a whole-cell patch writes.

Four disclosures, each a place the document was true in principle and unusable in practice:

* **AC1 — the ladder.** The guide documented **two** of the library's block-text reductions
  where the code performs **five**, and never named the one that decides a sub-span edit: the
  **``content`` text runs only**. The row count here is **derived from the code** (every
  block-level ``*_plain_text`` reduction in ``model/tree.py`` + ``write/resolve.py``), so a
  sixth reduction reddens the guide's table instead of quietly making it a lie. The three
  private bases are named by the **question they answer** and never by their ``_``-prefixed
  identifier — the guide is a supported surface and a private name in it is a promise.
* **AC2 — segmentation permanence.** A sub-span edit splits runs and this library re-merges
  nothing, so a ``snapshot()`` digest never returns to its pre-edit value. Two precisions the
  claim is false without: only a **proper** substring segments a block, and a **whole-block**
  edit is the one path that re-merges. The library's no-coalescing half is guarded here as a
  live grep; the server's behaviour is labelled **unmeasured, not refuted** — and the label is
  held to that spelling because the futurity guard's corpus includes the guide.
* **AC3 — the index's basis, outside the fence.** The generated node-class index answers
  ``model.plain_text``'s question, which is a **different** question from what a sub-span edit
  can reach. The sentence saying so must survive a regeneration of that generated region, so it
  is asserted to live **outside** the fence, addressed by the fence's marker strings.
* **AC4 — the id.** ``entry.cell.target_text_block_id`` — the block a whole-cell patch actually
  writes — appeared **0 times** in every shipped document.

Every assertion reads the **shipped** text (``larkdocio.guide``), never a source file, so a
guard cannot pass against a document the wheel does not carry.
"""
import ast
import dataclasses
import pathlib
import pydoc
import re

import pytest

import larkdocio
import larkdocio.model
import larkdocio.write
from larkdocio.model.node_docs import (
    NODE_CLASS_REGION_BEGIN,
    NODE_CLASS_REGION_END,
    node_class_markdown,
)
from larkdocio.permissions import region_of
from larkdocio.write.plan_field_docs import (
    PLAN_FIELD_REGION_BEGIN,
    PLAN_FIELD_REGION_END,
)
from larkdocio.write.preview import PlanEntry
from larkdocio.write.resolve import ResolvedCell

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The three sections the four disclosures land in, by slug — addressed by section, never by
#: line, because every line number in this file's issue moved between two shas.
TREE_TYPES = "the-tree-s-own-types-which-node-is-a-heading-at-what-level"
SUBSPAN = "recipe-edit-part-of-a-paragraph-a-sub-span-edit"
PLAN_SHAPES = "what-a-plan-entry-s-before-and-after-hold-one-row-per-shape"

#: The two modules that hold every block-level reduction.
_REDUCTION_MODULES = ("src/larkdocio/model/tree.py", "src/larkdocio/write/resolve.py")


def _prose(text):
    """Collapse wrapping and emphasis so a line break can never decide a test."""
    return re.sub(r"\s+", " ", text.replace("**", "").replace("`", "").replace("*", ""))


def _section(slug):
    return larkdocio.guide(section=slug)


def _guide():
    return larkdocio.guide(full=True)


def block_level_reductions():
    """Every **block-level** text reduction the library performs, derived from the two source
    modules rather than listed here.

    The rule is the one the code itself draws: a reduction whose name carries ``inline``
    reduces an inline *sequence*, not a block, and is not a rung of the ladder
    (``_inline_plain_text``, ``_text_run_inlines_plain_text``). Everything else ending in
    ``plain_text`` answers a question **about a block** and owes the guide a row.

    Returns ``{qualified_name: is_public}``.
    """
    found = {}
    for rel in _REDUCTION_MODULES:
        path = REPO_ROOT / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = rel.split("src/")[1][:-3].replace("/", ".")
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = node.name
            if not name.endswith("plain_text") or "inline" in name:
                continue
            found[f"{module}.{name}"] = not name.startswith("_")
    return found


def _ladder_table(section_text):
    """The reduction ladder's rows, found by its header row rather than by position — the
    section carries a generated table too and a positional slice would grab the wrong one."""
    lines = section_text.splitlines()
    for i, line in enumerate(lines):
        if _prose(line).strip().startswith("| The question it answers |"):
            rows = []
            for later in lines[i + 2:]:
                if not later.lstrip().startswith("|"):
                    break
                rows.append(later)
            return rows
    return []


# --------------------------------------------------------------------------- #
# AC1 — the ladder: five rungs, derived; no private name; the right citations.  #
# --------------------------------------------------------------------------- #

def test_the_derivation_finds_five_block_level_reductions():
    """The premise of the guard below, pinned so a change to the rule is visible as one."""
    assert len(block_level_reductions()) == 5, block_level_reductions()


def test_the_ladder_has_one_row_per_block_level_reduction():
    rows = _ladder_table(_section(TREE_TYPES))
    assert rows, "the reduction ladder table is not in the guide's tree-types section"
    assert len(rows) == len(block_level_reductions()), (
        f"the guide's ladder has {len(rows)} rows; the code performs "
        f"{len(block_level_reductions())} block-level reductions: "
        f"{sorted(block_level_reductions())}"
    )


def test_the_ladder_names_both_public_reductions():
    prose = _prose(_section(TREE_TYPES))
    for public in ("plain_text", "block_plain_text"):
        assert public in prose


@pytest.mark.parametrize(
    "private", sorted(n.rsplit(".", 1)[1] for n, pub in block_level_reductions().items()
                      if not pub))
def test_no_private_reduction_NAME_reaches_the_shipped_guide(private):
    """A ``_``-prefixed name in a supported document is a promise nobody agreed to keep. The
    three private bases are described by the question they answer instead."""
    assert private not in _guide(), (
        f"{private} is private and must not be spelled in the shipped guide; describe the "
        f"question it answers instead"
    )


def test_the_ladder_cites_the_two_help_targets_that_ANSWER_the_question():
    prose = _prose(_section(TREE_TYPES))
    for target in ("help(larkdocio.model.plain_text)",
                   "help(larkdocio.write.block_plain_text)"):
        assert _prose(target) in prose, f"the ladder does not cite {target}"


def test_the_two_cited_help_targets_really_do_render_their_own_reduction():
    """Executed, not assumed — the citation is only worth shipping if it answers the question
    it is cited for."""
    for target, needle in ((larkdocio.model.plain_text, "mention"),
                           (larkdocio.write.block_plain_text, "mention")):
        rendered = pydoc.render_doc(target)
        assert target.__name__ in rendered
        assert needle in rendered


def test_help_on_the_shadowed_write_resolve_NAME_is_never_cited():
    """``larkdocio.write.resolve`` is the re-exported dispatcher **function**, not the
    submodule of the same name: ``help()`` on it renders op dispatch and names none of the five
    reductions. Citing it would point a reader at a different question."""
    assert callable(larkdocio.write.resolve)
    assert not hasattr(larkdocio.write.resolve, "__file__")
    rendered = pydoc.render_doc(larkdocio.write.resolve)
    for needle in ("plain_text", "basis", "sub-span"):
        assert needle not in rendered, (
            f"help(larkdocio.write.resolve) unexpectedly mentions {needle!r} — re-check "
            f"whether it is still the wrong citation target"
        )
    assert "help(larkdocio.write.resolve)" not in _guide()


def test_the_sub_span_splitting_basis_is_named_as_content_text_runs_only():
    prose = _prose(_section(TREE_TYPES))
    assert "sub-span splitting basis" in prose
    assert "content text runs only" in prose


# --------------------------------------------------------------------------- #
# AC2 — segmentation permanence, with both precisions and the honest label.     #
# --------------------------------------------------------------------------- #

def test_the_recipe_states_that_a_sub_span_edit_leaves_the_block_segmented():
    prose = _prose(_section(SUBSPAN))
    assert "permanently segmented" in prose
    assert "never returns to its pre-edit value" in prose
    assert "snapshot" in prose


def test_the_recipe_states_the_PROPER_SUBSTRING_precision():
    prose = _prose(_section(SUBSPAN))
    assert "proper substring" in prose


def test_the_recipe_states_that_a_WHOLE_BLOCK_edit_is_the_one_path_that_re_merges():
    prose = _prose(_section(SUBSPAN))
    assert "re-merges" in prose
    assert "single run" in prose


def test_the_servers_own_behaviour_is_labelled_unmeasured_not_refuted():
    prose = _prose(_section(SUBSPAN))
    assert "unmeasured, not refuted" in prose


def test_the_recipe_writes_no_futurity_claim_the_shipped_guard_forbids():
    """``not yet`` is a registered futurity phrase over a corpus that includes the guide, so
    the honest label had to be spelled without it."""
    assert "not yet" not in _section(SUBSPAN).lower()


def test_the_library_STILL_has_no_run_coalescing_step():
    """The permanence claim's own evidence, as a live guard: if a coalescing step ever lands,
    the shipped sentence becomes false and this reddens instead."""
    hits = sorted(
        str(p.relative_to(REPO_ROOT))
        for p in (REPO_ROOT / "src").rglob("*.py")
        if "coalesc" in p.read_text(encoding="utf-8").lower()
    )
    assert hits == [], f"the guide claims the library re-merges no runs; found: {hits}"


# --------------------------------------------------------------------------- #
# AC3 — the index's basis: the RULE, outside the generated fence.               #
# --------------------------------------------------------------------------- #

_BASIS_NEEDLE = "does not predict a sub-span refusal"


def test_the_guide_says_the_index_does_not_predict_a_sub_span_refusal():
    prose = _prose(_section(TREE_TYPES))
    assert _BASIS_NEEDLE in prose


def test_the_basis_sentence_states_the_RULE_by_field_not_by_class_name():
    prose = _prose(_section(TREE_TYPES))
    for field in ("title", "caption", "url", "markup", "content"):
        assert field in prose, f"the basis rule does not name the {field} field"


def test_the_basis_sentence_lands_OUTSIDE_the_generated_node_class_region():
    text = _guide()
    region = region_of(text, NODE_CLASS_REGION_BEGIN.replace(" -->", ""),
                       NODE_CLASS_REGION_END)
    assert region, "the node-class region is not in the shipped guide"
    assert _BASIS_NEEDLE not in _prose(region), (
        "the basis sentence is INSIDE the generated node-class region — the generator "
        "rewrites that region and would eat it"
    )


def test_the_basis_sentence_SURVIVES_a_regeneration_of_the_node_class_region():
    text = _guide()
    region = region_of(text, NODE_CLASS_REGION_BEGIN.replace(" -->", ""),
                       NODE_CLASS_REGION_END)
    body = node_class_markdown()
    regenerated = text.replace(region, body)
    assert _BASIS_NEEDLE in _prose(regenerated), (
        "regenerating the node-class region removed the basis sentence"
    )


def test_the_generated_index_still_asks_exactly_its_TWO_questions():
    """No third column: a ``write/`` fact stated by ``model/`` would invert the dependency."""
    header = [
        line for line in node_class_markdown().splitlines()
        if line.startswith("| Node class |")
    ]
    assert len(header) == 1, header
    assert header[0].count("|") == 4, header[0]


# --------------------------------------------------------------------------- #
# AC4 — the id a whole-cell patch writes, named once, outside the other fence.  #
# --------------------------------------------------------------------------- #

def test_the_guide_names_the_id_a_whole_cell_patch_writes():
    assert "target_text_block_id" in _guide()


def test_the_guide_says_which_of_the_two_ids_is_the_CONTAINER():
    prose = _prose(_section(PLAN_SHAPES))
    assert "entry.cell.target_text_block_id" in prose
    assert "entry.block_id" in prose
    assert "container" in prose


def test_the_id_line_lands_OUTSIDE_the_generated_plan_shapes_region():
    text = _guide()
    region = region_of(text, PLAN_FIELD_REGION_BEGIN.replace(" -->", ""),
                       PLAN_FIELD_REGION_END)
    assert region, "the plan-shapes region is not in the shipped guide"
    assert "target_text_block_id" not in region, (
        "the id line is INSIDE the generated plan-shapes region and would be regenerated away"
    )


def test_the_id_really_is_reachable_from_a_plan_entry():
    """The sentence is only true because ``PlanEntry`` carries the resolved cell and the cell
    carries the id — checked against the dataclasses, not against prose."""
    entry_fields = {f.name for f in dataclasses.fields(PlanEntry)}
    cell_fields = {f.name for f in dataclasses.fields(ResolvedCell)}
    assert "cell" in entry_fields and "block_id" in entry_fields
    assert "target_text_block_id" in cell_fields
    assert "target_text_block_id" in ResolvedCell(row=1, column=2, row_key="k").to_dict()


# --------------------------------------------------------------------------- #
# AC5 — one home for every sentence: the guide, and nowhere else.               #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("needle", [
    "target_text_block_id", "unmeasured, not refuted", "sub-span splitting basis",
    "does not predict a sub-span refusal",
])
def test_no_sentence_is_duplicated_into_the_writer_brief(needle):
    brief = (REPO_ROOT / "src/larkdocio/write/README.md").read_text(encoding="utf-8")
    assert needle not in brief, (
        f"{needle!r} is stated in the guide; a second copy is a second thing to keep true"
    )
