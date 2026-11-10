"""LD-600 — the plan entry's ``before`` / ``after`` shape table: GENERATED off
``write/ops.py``'s serializers, landed in the shipped guide behind a bidirectional fence, on
the ``model/node_docs.py`` precedent.

**The trap this file exists to hold shut.** ``write/ops.py`` has FIVE serializer functions but
the write layer has SIX ``before``-bearing shapes: the ``todo_done`` checkbox flip and the
table-cell patch both ride INSIDE ``_serialize_edit``. A generator keyed on serializer
functions emits five rows and silently drops a shape — which is the exact defect class the
issue exists to end. So the derivation basis here is **the shapes**: each ``before``-bearing
serializer contributes its base shape, plus one shape per ``if entry.<field> is not None``
branch inside it, and every such field must be a real ``PlanEntry`` dataclass field.

The bidirectional arms are red-proofed in both directions (a shape with no row, a row with no
shape) and the variant derivation is red-proofed against doctored serializers, so "six rows"
is never a number this file or the generator can assert by typing it.
"""
import ast
import dataclasses
import re

import pytest

from consumer_text import dialect_hits

from larkdocio import guide
from larkdocio.permissions import region_of
from larkdocio.write import ops as write_ops
from larkdocio.write.plan_field_docs import (
    PLAN_FIELD_REGENERATE,
    PLAN_FIELD_REGION_BEGIN,
    PLAN_FIELD_REGION_END,
    BeforeAfterShape,
    before_after_shapes,
    ops_without_before_after,
    plan_field_markdown,
    shape_label,
)
from larkdocio.write import plan_field_docs as pfd
from larkdocio.write.preview import PlanEntry


def _region():
    return region_of(guide(full=True), PLAN_FIELD_REGION_BEGIN.replace(" -->", ""),
                     PLAN_FIELD_REGION_END)


def _row_first_cells(region):
    """The FIRST cell of every body row of the region's table, in document order."""
    cells = []
    for line in region.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        parts = [p.strip() for p in stripped.strip("|").split("|")]
        if not parts or set(parts[0]) <= {"-", ":"} or parts[0].startswith("Plan entry"):
            continue
        cells.append(parts[0])
    return cells


def _ast_of(fn):
    return pfd._serializer_ast(fn)


# --------------------------------------------------------------------------- #
# AC1 — the table ships in the guide, fenced, generated, byte-identical.       #
# --------------------------------------------------------------------------- #

def test_the_region_exists_in_the_shipped_guide():
    assert _region(), "the guide carries no generated before/after-shape region"


def test_the_region_is_BYTE_IDENTICAL_to_the_projection():
    assert _region() == plan_field_markdown(), (
        "the guide's before/after-shape region has drifted from "
        f"larkdocio.write.plan_field_docs — regenerate it with: {PLAN_FIELD_REGENERATE}"
    )


def test_exactly_one_begin_and_one_end_fence_in_order():
    text = guide(full=True)
    begin = PLAN_FIELD_REGION_BEGIN.replace(" -->", "")
    assert text.count(begin) == 1, "expected exactly one BEGIN fence"
    assert text.count(PLAN_FIELD_REGION_END) == 1, "expected exactly one END fence"
    assert text.index(begin) < text.index(PLAN_FIELD_REGION_END)


def test_the_region_carries_its_own_regeneration_command():
    assert PLAN_FIELD_REGENERATE in _region()


def test_the_fence_markers_mirror_the_node_class_precedent():
    """Same shape as the existing generated, fenced, in-guide table — one mechanism, not two."""
    from larkdocio.model.node_docs import NODE_CLASS_REGION_BEGIN, NODE_CLASS_REGION_END

    for ours, theirs in ((PLAN_FIELD_REGION_BEGIN, NODE_CLASS_REGION_BEGIN),
                         (PLAN_FIELD_REGION_END, NODE_CLASS_REGION_END)):
        assert ours.startswith(theirs.split()[0] + " " + theirs.split()[1])
        assert ours.endswith("-->")
    assert PLAN_FIELD_REGION_BEGIN.endswith("(generated -->")


# --------------------------------------------------------------------------- #
# AC2 — the fence is BIDIRECTIONAL, and both arms bite red on doctored input.   #
# --------------------------------------------------------------------------- #

def test_every_derived_shape_has_a_row():
    region = _region()
    missing = [shape_label(s) for s in before_after_shapes() if shape_label(s) not in region]
    assert not missing, f"these serializable shapes have no row in the generated table: {missing}"


def test_every_row_corresponds_to_a_derived_shape():
    labels = {shape_label(s) for s in before_after_shapes()}
    phantom = [cell for cell in _row_first_cells(_region()) if cell not in labels]
    assert not phantom, f"the table has rows matching no real shape: {phantom}"


def test_the_shape_coverage_arm_BITES_RED_on_a_shape_with_no_row():
    """Doctor the derivation with one extra shape; the "every shape has a row" arm must fail."""
    region = _region()
    doctored = before_after_shapes() + (
        BeforeAfterShape(op="ghost-op", variant=None, has_after=True, before_is_text=True),
    )
    missing = [shape_label(s) for s in doctored if shape_label(s) not in region]
    assert missing == [shape_label(doctored[-1])], (
        "the coverage arm did not notice a shape with no row — it cannot bite"
    )


def test_the_row_coverage_arm_BITES_RED_on_a_row_with_no_shape():
    """Doctor the REGION with one phantom row; the "every row is a real shape" arm must fail."""
    labels = {shape_label(s) for s in before_after_shapes()}
    doctored = _region() + '\n| `entry.op == "ghost-op"` | a ghost | nothing | nothing |\n'
    phantom = [cell for cell in _row_first_cells(doctored) if cell not in labels]
    assert phantom == ['`entry.op == "ghost-op"`'], (
        "the row arm did not notice a row matching no shape — it cannot bite"
    )


# --------------------------------------------------------------------------- #
# AC3 — all six shapes, and the sixth DERIVED rather than hard-coded.          #
# --------------------------------------------------------------------------- #

def test_the_row_count_equals_the_DERIVED_shape_count():
    assert len(_row_first_cells(_region())) == len(before_after_shapes())


@pytest.mark.parametrize("op,variant", [
    ("edit", None),          # the whole-block replace
    ("edit", "cell"),        # the table-cell descendant patch
    ("edit", "todo_done"),   # before == after, the change on a separate field
    ("subspan", None),       # the span only
    ("grow-table", None),    # a grid phrase, not text
    ("delete", None),        # no `after` key at all
])
def test_all_six_shapes_are_derived_and_present(op, variant):
    shapes = {(s.op, s.variant) for s in before_after_shapes()}
    assert (op, variant) in shapes, f"the derivation lost the ({op}, {variant}) shape"
    matching = [s for s in before_after_shapes() if (s.op, s.variant) == (op, variant)]
    assert shape_label(matching[0]) in _region()


def test_there_are_SIX_shapes_and_FIVE_serializers_the_counts_deliberately_differ():
    """The trap, pinned: five serializer functions, six shapes. If these ever match again it is
    either a real change to the write layer or a generator that went back to keying on
    functions — both need a human."""
    serializers = {d.serialize for d in write_ops.OPS}
    assert len(before_after_shapes()) == 6
    assert len([s for s in serializers
                if "before" in pfd._emitted_keys(_ast_of(s))]) == 4


def test_the_variant_shapes_FOLLOW_the_serializer_and_are_NOT_hard_coded():
    """The load-bearing red-proof for AC3: a doctored serializer with no ``todo_done`` branch
    derives no ``todo_done`` variant, and one with a third branch derives a third."""
    def _without_todo(entry):
        d = {"replacement": entry.replacement}
        if entry.is_resolved:
            d["before"] = entry.before
            d["after"] = entry.after
            if entry.cell is not None:
                d["cell"] = entry.cell.to_dict()
        return d

    def _with_a_third(entry):
        d = {"replacement": entry.replacement}
        if entry.cell is not None:
            d["cell"] = entry.cell.to_dict()
        if entry.todo_done is not None:
            d["todo_done"] = entry.todo_done
        if entry.grow is not None:
            d["grow"] = entry.grow.to_dict()
        return d

    assert pfd._variant_fields(_ast_of(_without_todo)) == ("cell",)
    assert pfd._variant_fields(_ast_of(_with_a_third)) == ("cell", "todo_done", "grow")


def test_the_todo_done_variant_comes_from_the_REAL_edit_serializer():
    edit = write_ops.BY_KIND["edit"].serialize
    assert pfd._variant_fields(_ast_of(edit)) == ("cell", "todo_done")
    assert "todo_done" in {f.name for f in dataclasses.fields(PlanEntry)}


def test_a_variant_field_that_is_not_a_PlanEntry_field_is_REFUSED_not_silently_rowed():
    """A serializer branching on a field the record does not have is a defect, not a shape."""
    from larkdocio.errors import LarkConfigError

    def _bogus(entry):
        d = {"before": entry.before}
        if entry.no_such_field is not None:
            d["x"] = 1
        return d

    with pytest.raises(LarkConfigError):
        pfd._shapes_for("bogus", _ast_of(_bogus))


def test_the_precondition_helper_is_not_mistaken_for_a_variant():
    """``_serialize_precondition`` guards on ``entry.precondition_text is not None`` too, but it
    is a HELPER call from each serializer — a precondition does not change what ``before``
    holds, and factoring it out is what keeps it off the table."""
    for kind in ("edit", "subspan", "delete"):
        assert "precondition_text" not in pfd._variant_fields(
            _ast_of(write_ops.BY_KIND[kind].serialize))


# --------------------------------------------------------------------------- #
# AC4 — each row says what `before` holds; the three hazards are named.        #
# --------------------------------------------------------------------------- #

def _row_for(op, variant=None):
    shape = next(s for s in before_after_shapes() if (s.op, s.variant) == (op, variant))
    label = shape_label(shape)
    return next(line for line in _region().splitlines()
                if _row_first_cells(line) == [label])


def test_the_delete_row_states_there_is_NO_after_key():
    row = _row_for("delete")
    assert "no `after` key" in row, row


def test_the_no_after_phrase_is_DERIVED_from_the_serializers_emitted_keys():
    delete = write_ops.BY_KIND["delete"].serialize
    keys = pfd._emitted_keys(_ast_of(delete))
    assert "before" in keys and "after" not in keys
    assert not next(s for s in before_after_shapes() if s.op == "delete").has_after


def test_the_grow_table_row_states_before_is_a_grid_phrase_NOT_text():
    row = _row_for("grow-table")
    assert "Not text" in row and "grid phrase" in row, row


def test_the_grow_table_not_text_answer_is_DERIVED_not_typed():
    """A grow rewrites no text, which is exactly why its serializer captures no text
    precondition — that is the code signal the generator reads."""
    shapes = {s.op: s for s in before_after_shapes()}
    assert not shapes["grow-table"].before_is_text
    assert shapes["edit"].before_is_text and shapes["delete"].before_is_text
    assert not pfd._captures_precondition(_ast_of(write_ops.BY_KIND["grow-table"].serialize))
    assert pfd._captures_precondition(_ast_of(write_ops.BY_KIND["delete"].serialize))


def test_the_todo_done_row_says_before_equals_after_and_names_the_carrying_field():
    row = _row_for("edit", "todo_done")
    assert "`before` == `after`" in row, row
    assert "`entry.todo_done`" in row, row


def test_the_table_cell_row_says_the_cell_not_the_container_block():
    row = _row_for("edit", "cell")
    assert "cell" in row and "container" in row, row


def test_the_subspan_row_says_the_span_only():
    row = _row_for("subspan")
    assert "span" in row, row


def test_every_row_answers_both_questions_with_prose():
    for line in _region().splitlines():
        stripped = line.strip()
        if not stripped.startswith("| `entry.op"):
            continue
        parts = [p.strip() for p in stripped.strip("|").split("|")]
        assert len(parts) == 4, f"expected four columns, got {len(parts)}: {stripped}"
        assert all(len(p) > 10 for p in parts[1:]), f"a thin cell in: {stripped}"


# --------------------------------------------------------------------------- #
# The ops that carry NEITHER field are disclosed, and derived too.             #
# --------------------------------------------------------------------------- #

def test_the_ops_with_no_before_or_after_are_named_in_the_region():
    named = ops_without_before_after()
    assert set(named) == {"insert", "comment-create", "comment-remove"}
    for kind in named:
        assert f"`{kind}`" in _region()


def test_the_two_derivations_PARTITION_the_registry():
    """Every registered op is either a before-bearing shape or explicitly on the no-pair list —
    an op cannot join the registry and appear in neither answer."""
    with_before = {s.op for s in before_after_shapes()}
    without = set(ops_without_before_after())
    assert not (with_before & without)
    assert with_before | without == {d.kind for d in write_ops.OPS}


# --------------------------------------------------------------------------- #
# AC7 — the generated region is consumer-reaching text; no internal dialect.   #
# --------------------------------------------------------------------------- #

def test_the_generated_region_carries_NO_internal_dialect():
    hits = dialect_hits(plan_field_markdown())
    assert not hits, f"the generator emits internal dialect: {hits}"


def test_the_authored_prose_is_COMPLETE_for_every_derived_shape():
    """A shape with no sentence must RAISE at generation rather than ship a blank cell —
    the generator refuses a gap instead of a hand-kept table wearing generator clothes."""
    from larkdocio.errors import LarkConfigError

    with pytest.raises(LarkConfigError):
        pfd._prose_for(BeforeAfterShape(op="ghost-op", variant=None, has_after=True,
                                        before_is_text=True))


# --------------------------------------------------------------------------- #
# No public export moved — dotted import only, exactly like node_docs.py.      #
# --------------------------------------------------------------------------- #

def test_plan_field_docs_has_no_all_and_is_not_reexported_from_write():
    import larkdocio.write as write_pkg

    assert not hasattr(pfd, "__all__"), (
        "larkdocio.write.plan_field_docs must carry NO __all__ entry — a public export here "
        "would move larkdocio.capabilities() bytes for a documentation generator"
    )
    for name in ("plan_field_markdown", "before_after_shapes", "shape_label",
                 "ops_without_before_after"):
        assert not hasattr(write_pkg, name), (
            f"larkdocio.write re-exports {name!r} — it must stay reachable only by the dotted "
            f"import larkdocio.write.plan_field_docs"
        )


def test_the_CENSUS_follows_the_REGISTRY_and_is_not_a_list_of_its_own():
    """Doctor the registry with one extra op and BOTH derivations must move — proof the census
    is read off ``write.ops.OPS`` rather than enumerated in the generator."""
    import dataclasses as dc

    def _ghost_with_before(entry):
        d = {}
        d["before"] = entry.before
        d["after"] = entry.after
        return d

    def _ghost_without(entry):
        return {"comment": None}

    edit = write_ops.BY_KIND["edit"]
    added = (
        dc.replace(edit, kind="ghost-paired", serialize=_ghost_with_before),
        dc.replace(edit, kind="ghost-pairless", serialize=_ghost_without),
    )
    saved = write_ops.OPS
    try:
        write_ops.OPS = saved + added
        assert ("ghost-paired", None) in {(s.op, s.variant) for s in before_after_shapes()}
        assert "ghost-pairless" in ops_without_before_after()
        with pytest.raises(Exception):
            plan_field_markdown()   # a new shape with no sentence refuses to generate
    finally:
        write_ops.OPS = saved

    assert ("ghost-paired", None) not in {(s.op, s.variant) for s in before_after_shapes()}
    assert re.search(r"\bOPS\b", __import__("inspect").getsource(pfd)), (
        "the generator does not read the op registry at all")
