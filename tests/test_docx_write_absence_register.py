"""LD-563 — THE DOCX-WRITE ABSENCE REGISTER, and the two claims it corrects.

Three defects on one surface, all about **how the docx write path describes itself**:

1. the surface named ONE of its absences (no move / no reorder) and none of the four a
   consumer of round 5 actually hit — a mention, character styling, growing an existing
   table, flipping a ``todo``'s checkbox — plus a document retitle;
2. ``NewBlock.table``'s docstring promised *rich cell content* through a path typed ``str``
   whose sub-span sibling takes narrative anchors only — a claim green in prose and wrong
   against the shipped shapes;
3. the kinds that accept ``spans=`` were enumerated in a private constant and in **no**
   shipped document, so the one caller who used a span paid a source-read to find it.

**Not one absent verb is implemented here.** Every test below is a claim about what the
shipped bytes SAY, and each row's own truth is re-derived from the code it describes rather
than trusted — which is why this file greps ``src`` for ``update_text_style`` and drives a
real checkbox edit through the shipped ``dry_run`` → ``apply`` gate instead of quoting the
issue that reported them.

The register is authored as data in :mod:`larkdocio.write.absences` and projected onto the
docx-write surface's **existing** ``Surface.absences`` contract — the fourth absence
vocabulary this repo nearly grew is the defect this file guards against, not the shape it
ships.
"""
import pathlib
import re

import pytest

import consumer_text
from harness import build_blocks
from write_harness import RoutingOpener, _block_payload, _client, _parent_payload

from larkdocio import capabilities, guide_sections
from larkdocio.model import project_block_ids
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import compile_reconciliation
from larkdocio.write.absences import (
    ABSENCE_VERIFICATION_LABELS,
    DOCX_WRITE_ABSENCES,
    ABSENCE_ROW_KEYS,
)
from larkdocio.write.apply import apply
from larkdocio.write.client import WriteClient
from larkdocio.write.model import NewBlock, TextSpan
from larkdocio.write.model.requests import _SPANNABLE_KINDS, NewBlockKind
from larkdocio.write.preview import dry_run
from larkdocio.write.reconcile import reconcile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "larkdocio"
WRITER_BRIEF = SRC / "write" / "README.md"


def _rows():
    return {row["id"]: row for row in DOCX_WRITE_ABSENCES}


def _projected():
    return capabilities(full=True)["surfaces"]["docx-write"]["absences"]


# --------------------------------------------------------------------------- #
# AC1 — the register is DATA in write/**, on the EXISTING contract, projected   #
#       onto the surface under a guard that bites in BOTH directions.           #
# --------------------------------------------------------------------------- #

def test_ac1_the_register_is_authored_as_data_in_the_write_package():
    assert isinstance(DOCX_WRITE_ABSENCES, tuple) and DOCX_WRITE_ABSENCES
    for row in DOCX_WRITE_ABSENCES:
        assert isinstance(row, dict), row
        assert tuple(row) == ABSENCE_ROW_KEYS, (
            f"{row.get('id')!r} does not carry the shipped Surface.absences contract "
            f"({ABSENCE_ROW_KEYS}) in order — a second absence vocabulary is the defect "
            f"this register exists to avoid")
        for key, value in row.items():
            assert isinstance(value, str) and value.strip(), (key, row.get("id"))


def test_ac1_every_row_id_is_unique_and_slug_shaped():
    ids = [row["id"] for row in DOCX_WRITE_ABSENCES]
    assert len(set(ids)) == len(ids), ids
    for row_id in ids:
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", row_id), row_id


def test_ac1_every_verification_label_is_drawn_from_the_ONE_named_enumeration():
    """A free string here is how the fourth vocabulary arrives."""
    for row in DOCX_WRITE_ABSENCES:
        assert row["verification"] in ABSENCE_VERIFICATION_LABELS, row["id"]


def test_ac1_the_enumeration_is_not_dead_vocabulary():
    """Every label in the enumeration is actually READ — as a row's own label or as the
    strength of a clause inside a row's evidence. An enumeration nobody projects from is a
    documented token, which is the F1 shape this issue is about."""
    used = {row["verification"] for row in DOCX_WRITE_ABSENCES}
    evidence = " ".join(row["evidence"] for row in DOCX_WRITE_ABSENCES).lower()
    for label in ABSENCE_VERIFICATION_LABELS:
        assert label in used or label in evidence, label


def test_ac1_every_register_row_is_projected_onto_the_docx_write_surface():
    projected = {row["id"]: row for row in _projected()}
    for row in DOCX_WRITE_ABSENCES:
        assert row["id"] in projected, f"{row['id']} is authored and not projected"
        assert projected[row["id"]] == row, row["id"]


def test_ac1_every_projected_row_is_authored_in_the_register():
    """The other direction, and the one that keeps the register the single authoring: a row
    hand-typed into the assembly would be a second place to look."""
    assert _projected() == [dict(row) for row in DOCX_WRITE_ABSENCES]


def test_ac1_no_absence_row_is_hand_typed_in_the_capabilities_assembly():
    source = (SRC / "capabilities" / "_assembly.py").read_text(encoding="utf-8")
    assert '"verification":' not in source and "'verification':" not in source, (
        "an absence row is authored inside the capabilities assembly again — the register "
        "in larkdocio.write.absences is the one authoring")


def test_ac1_no_row_carries_internal_dialect():
    """The rows ship inside ``capabilities()``; an issue id or a role name resolves only on
    this repo's board."""
    for row in DOCX_WRITE_ABSENCES:
        for key, value in row.items():
            assert not consumer_text.dialect_hits(value), (row["id"], key,
                                                           consumer_text.dialect_hits(value))


def test_ac1_every_guide_section_a_row_points_at_EXISTS():
    slugs = {row["slug"] for row in guide_sections()}
    for row in DOCX_WRITE_ABSENCES:
        for named in re.findall(r'guide\(section="([^"]+)"\)', row["instead"]):
            assert named in slugs, (row["id"], named)


# --------------------------------------------------------------------------- #
# AC2 — the seed rows, each one re-derived from the code it describes.          #
# --------------------------------------------------------------------------- #

#: The row LD-575 narrowed. Named once so the tests below follow the move in one place —
#: the same discipline ``CHECKBOX_ABSENCE_ID`` records in the router's own guard.
TABLE_GRID_ROW_ID = "no-table-grid-change-beyond-appending-a-row"

SEED_IDS = (
    "no-move-or-reorder-operation",
    "no-mention-authoring",
    "no-character-style-operation",
    # LD-575 took this SLOT from ``no-grow-operation-for-an-existing-table``, whose statement
    # (no operation adds or removes a row or a column of an existing table) became false in
    # part the moment appending a row shipped. The reason it was recorded — the grow mechanism
    # shipped and was measured while being unreachable as an operation, and the only
    # identity-preserving route consumers found was outside the plan gate — is preserved inside
    # the successor's ``evidence`` and is exactly why the operation exists.
    "no-table-grid-change-beyond-appending-a-row",
    # LD-574 took this SLOT from ``todo-done-bit-is-not-editable``, whose statement (the done
    # bit cannot be changed, and an edit that tries reports SUCCESS) became false the moment
    # the bit shipped. The reason LD-563 recorded it — a silent success is worse than a
    # refusal, and a register claiming a hole beside a capability is the same defect inverted
    # — is preserved inside the successor's ``evidence`` and is why the residual now refuses.
    "no-block-property-edit-beyond-text",
    "no-document-retitle-operation",
)


@pytest.mark.parametrize("row_id", SEED_IDS)
def test_ac2_the_seed_row_is_present_and_says_something(row_id):
    row = _rows()[row_id]
    assert len(row["statement"]) > 80 and len(row["evidence"]) > 80, row_id
    assert len(row["instead"]) > 20, row_id


@pytest.mark.parametrize("row_id", [i for i in SEED_IDS if i != "no-move-or-reorder-operation"])
def test_ac2_every_new_row_names_the_shipped_symbol_its_reason_reads_off(row_id):
    """A reason a reader cannot follow back to code is a memory, not a fact."""
    row = _rows()[row_id]
    text = row["statement"] + row["evidence"]
    assert "larkdocio." in text, row_id


def test_ac2_the_character_style_row_is_TRUE_of_the_tree_it_describes():
    """Re-derived, not quoted — and NARROWED by LD-574 rather than struck.

    LD-563's reason for this guard stands unchanged: a row claiming this library applies no
    character styling must be checkable against the tree, or it is a memory. What moved is the
    conclusion. The docx text-style operation now has **exactly one** call site, writing
    **exactly one** field — a todo block's ``done`` bit, which is block state and not
    character styling — so the guard counts the call sites instead of requiring zero. A second
    one, or a first one that assembles a ``text_element_style``, reddens here.
    """
    register = SRC / "write" / "absences.py"
    #: The operation as a **request key** — the shape that is a call rather than a mention.
    #: A prose reference in a docstring is a description of Lark's surface, which is exactly
    #: what the original guard's own comment said about the write brief's route table.
    key = '"update_text_style"'
    hits = sorted(str(path.relative_to(SRC))
                  for path in SRC.rglob("*.py")
                  if path != register and key in path.read_text(encoding="utf-8"))
    assert hits == ["write/apply.py"], (
        f"{hits} BUILD a docx text-style body. The register row is scoped to ONE call site "
        f"writing ONE field (the checkbox); a second is a capability the row does not "
        f"describe. The register itself is excluded because DESCRIBING the operation is what "
        f"it is for")
    apply_src = (SRC / "write" / "apply.py").read_text(encoding="utf-8")
    assert apply_src.count('"update_text_style"') == 1
    assert '"fields": [2]' in apply_src, (
        "the one call site writes the done field's mask and nothing wider")
    assert "text_element_style" not in apply_src.split("update_text_style")[1][:400]
    assert "update_text_style" in _rows()["no-character-style-operation"]["evidence"]


def test_ac2_the_mention_row_is_TRUE_of_the_types_it_describes():
    """A created run carries a link anchor and nothing else — there is no mention carrier."""
    import dataclasses

    assert [f.name for f in dataclasses.fields(TextSpan)] == ["text", "link_url"]
    encoder = (SRC / "write" / "encode.py").read_text(encoding="utf-8")
    assert "mention_user" not in encoder and "mention_doc" not in encoder


def test_ac2_the_retitle_row_is_TRUE_of_the_client_it_describes():
    """No verb on the write client renames or retitles an existing document."""
    named = [name for name in dir(WriteClient)
             if not name.startswith("__")
             and any(word in name.lower() for word in ("retitle", "rename"))]
    assert named == [], named


# --------------------------------------------------------------------------- #
# AC3 — the todo.done row states the LIVE BEHAVIOUR, and the behaviour is       #
#       measured here rather than asserted.                                     #
# --------------------------------------------------------------------------- #

def _todo_tree(done=False, text="ship the thing"):
    page = {"block_id": "doc1", "parent_id": "", "block_type": 1,
            "page": {"elements": [{"text_run": {"content": "T"}}]},
            "children": ["t1"]}
    todo = {"block_id": "t1", "parent_id": "doc1", "block_type": 17,
            "todo": {"elements": [{"text_run": {"content": text}}],
                     "style": {"done": done}},
            "children": []}
    return Parser(Config()).parse_docx_tree("doc1", build_blocks([page, todo]))


def test_ac3_flipping_a_checkbox_MOVES_THE_BIT_through_the_shipped_gate():
    """This test is LD-563's own reproduction of the defect, INVERTED by LD-574.

    Its reason is preserved verbatim: the row must be re-derived from the code it describes
    rather than quoted, which is why this drives project → edit the marker → reconcile →
    compile → dry_run → apply end to end instead of asserting prose. Only the expected
    outcome moved. It used to assert that the compiled replacement was the block's own
    unchanged text and that **no** request body carried a ``done`` field — the silent
    no-op. It now asserts the opposite, on the same path.
    """
    tree = _todo_tree()
    projection = project_block_ids(tree)
    edited = projection.markdown.replace("[ ]", "[x]")
    plan = reconcile(projection, edited)
    assert plan.ok

    requests = compile_reconciliation(plan, projection)
    assert len(requests) == 1
    assert requests[0].todo_done is True, "the checkbox state now reaches the request"

    opener = RoutingOpener(blocks={
        "doc1": _parent_payload("doc1", ["t1"]),
        "t1": _block_payload("t1", [{"text_run": {"content": "ship the thing"}}],
                             block_type=17, key="todo", parent_id="doc1",
                             style={"done": False}),
    })
    log = apply(dry_run(requests, tree), _client(opener), "doc1")

    assert [entry.outcome for entry in log.entries] == ["applied"]
    assert [entry.todo_done for entry in log.entries] == [True], (
        "the apply log is a receipt: a flip that leaves before == after must say what moved")
    assert [c["body"] for c in opener.writes] == [
        {"update_text_style": {"style": {"done": True}, "fields": [2]}}], opener.writes


def test_ac3_the_row_states_the_RESIDUAL_and_keeps_the_defects_reason():
    """LD-563's rule, unchanged: the row may not dress a silence as a design. LD-574 removed
    the silence — the residual refuses, typed — so the row now has to say THAT, while carrying
    the superseded conclusion's reason so the argument is not re-litigated."""
    row = _rows()["no-block-property-edit-beyond-text"]
    blob = (row["statement"] + " " + row["evidence"]).lower()
    assert "change-not-expressible" in blob, "the row must name the typed refusal"
    assert "never reported as applied" in blob or "not reported as applied" in blob
    assert "todo-done-bit-is-not-editable" in blob and "superseded" in blob, (
        "a rationale-free strike is what gets a settled argument re-litigated")
    for dressing in ("by design", "deliberate boundary", "designed absence"):
        assert dressing not in blob, dressing


# --------------------------------------------------------------------------- #
# AC4 — the table-grow row cites the measurement that EXISTS.                   #
# --------------------------------------------------------------------------- #

def test_ac4_the_table_grow_row_cites_the_measured_append_and_its_scope():
    row = _rows()[TABLE_GRID_ROW_ID]
    evidence = row["evidence"].lower()
    assert "measured" in evidence
    assert "row_index" in evidence and "-1" in evidence
    assert "200" in evidence
    assert "201" in evidence and "500" in evidence
    assert "unmeasured" in evidence


def test_ac4_the_row_names_the_PLAN_GATED_CALL_SITES_not_only_the_mechanism():
    """TRANSFORMED, not struck (LD-575). What this guard exists to hold is unchanged: the
    row's reason must be followable back to code rather than asserted. What changed is the
    code it points at. It used to hold that the grow helper had exactly ONE call site, inside
    ``_apply_insert`` — the structural fact that made the grow unreachable as an operation.
    That is now the wrong shape to demand, because the whole point of the change is that a
    SECOND call site exists; so the guard holds the successor fact instead: there is ONE append
    primitive, it has exactly TWO callers, and the row names it."""
    row = _rows()[TABLE_GRID_ROW_ID]
    assert "_append_table_lines" in row["evidence"]

    source = (SRC / "write" / "apply.py").read_text(encoding="utf-8").splitlines()
    starts = [n for n, line in enumerate(source, 1) if line.startswith("def ")]

    def enclosing_def(lineno):
        return source[max(n for n in starts if n < lineno) - 1]

    calls = [n for n, line in enumerate(source, 1)
             if "_append_table_lines(" in line and not line.lstrip().startswith("def ")]
    assert sorted(enclosing_def(n).split("(")[0] for n in calls) == [
        "def _apply_grow_table", "def _grow_table_grid"], [enclosing_def(n) for n in calls]

    # ...and the create path's own grow is still reached from the plan-gated insert alone.
    grow_calls = [n for n, line in enumerate(source, 1)
                  if "_grow_table_grid(" in line and not line.lstrip().startswith("def ")]
    assert len(grow_calls) == 1, grow_calls
    assert enclosing_def(grow_calls[0]).startswith("def _apply_insert(")


def test_ac4_mid_table_insertion_is_labelled_unmeasured_and_not_attributed_to_the_docstring():
    row = _rows()[TABLE_GRID_ROW_ID]
    blob = row["evidence"]
    assert "mid-table" in blob.lower()
    docstring = __import__("larkdocio.write.apply", fromlist=["_grow_table_grid"])
    assert "mid-table" not in (docstring._grow_table_grid.__doc__ or "").lower(), (
        "if the docstring ever measures mid-table insertion, this row's label is the thing "
        "to correct — it may not borrow a measurement that does not exist")


# --------------------------------------------------------------------------- #
# AC5 — the retitle row is written from the TREE.                               #
# --------------------------------------------------------------------------- #

def test_ac5_the_retitle_row_labels_its_route_unmeasured_rather_than_recommending_one():
    row = _rows()["no-document-retitle-operation"]
    blob = row["statement"] + " " + row["evidence"]
    assert "unmeasured" in blob.lower()
    assert "document_id" in blob, (
        "the root Page block's id equals the document id — an ADDRESSING fact the row states "
        "so a reader does not re-derive it as a route")
    lowered = blob.lower()
    for confident in ("simply patch", "just patch", "you can retitle", "workaround"):
        assert confident not in lowered, confident


def test_ac5_the_absence_register_is_pointed_at_from_the_shipped_writer_brief():
    """A register a consumer cannot find is a list they will not read. The brief's Non-goals
    section names the machine-readable form."""
    brief = " ".join(WRITER_BRIEF.read_text(encoding="utf-8").split())
    assert '["absences"]' in brief and "larkdocio/write/absences.py" in brief


def test_ac5_the_row_reads_the_BLOCKS_matrix_columns_correctly():
    """The page row's Write cell is ``not-creatable``; ``full`` is the read-lossiness
    column. A row asserting otherwise would be a fifth finding, minted by us."""
    row = _rows()["no-document-retitle-operation"]
    assert "write: full" not in (row["statement"] + row["evidence"]).lower()
    matrix = (REPO_ROOT / "BLOCKS.md").read_text(encoding="utf-8")
    page_row = next(line for line in matrix.splitlines()
                    if line.startswith("| 1 ") and "| page " in line)
    cells = [c.strip() for c in page_row.split("|")]
    assert cells[4] == "not-creatable", page_row
    assert cells[5] == "full", page_row          # read-lossiness, NOT the write column
    assert cells[6] == "opaque", page_row


# --------------------------------------------------------------------------- #
# AC6(a) — NewBlock.table stops promising what the types cannot carry.          #
# --------------------------------------------------------------------------- #

def test_ac6a_the_table_docstring_no_longer_promises_rich_cell_content():
    doc = " ".join((NewBlock.table.__doc__ or "").split())
    assert "Rich cell content (styled runs, a nested list) is authored" not in doc
    assert "styled runs" in doc or "nested" in doc, (
        "the correction states what the types DO carry — deleting the sentence without "
        "answering the question sends the next caller to the source")


def test_ac6a_the_correction_is_true_of_the_two_shapes_that_refute_the_old_claim():
    import dataclasses

    from larkdocio.write.model.requests import EditRequest, SubSpanEditRequest

    edit = {f.name: f.type for f in dataclasses.fields(EditRequest)}
    assert edit["replacement"] == "str" or edit["replacement"] is str, edit
    from larkdocio.write.model.requests import NarrativeAnchor
    from larkdocio.write.model.anchors import TableLocator

    subspan = {f.name: f.type for f in dataclasses.fields(SubSpanEditRequest)}
    assert subspan["anchor"] == NarrativeAnchor, subspan
    assert TableLocator not in getattr(NarrativeAnchor, "__args__", ()), (
        "a sub-span within a table cell is out of scope on the shipped type — the docstring "
        "may not promise what the annotation refuses")

    doc = " ".join((NewBlock.table.__doc__ or "").split())
    assert "plain" in doc.lower()
    assert "TableLocator" in doc
    assert "SubSpanEditRequest" in doc or "sub-span" in doc.lower()


# --------------------------------------------------------------------------- #
# AC6(b) — the spannable kinds are a PROJECTION of the constant, bidirectional. #
# --------------------------------------------------------------------------- #

_BEGIN = "<!-- spannable-kinds: begin -->"
_END = "<!-- spannable-kinds: end -->"


def _brief_region():
    text = WRITER_BRIEF.read_text(encoding="utf-8")
    assert _BEGIN in text and _END in text, "the writer brief lost the projected region"
    return text.split(_BEGIN, 1)[1].split(_END, 1)[0]


def _documented_kinds():
    return [m.group(1) for m in re.finditer(r"^\|\s*`([a-z]+)`\s*\|", _brief_region(),
                                            re.MULTILINE)]


def test_ac6b_every_spannable_kind_is_named_in_the_shipped_writer_brief():
    documented = _documented_kinds()
    for kind in _SPANNABLE_KINDS:
        assert kind.value in documented, kind.value


def test_ac6b_every_documented_kind_is_really_in_the_constant():
    spannable = {kind.value for kind in _SPANNABLE_KINDS}
    for value in _documented_kinds():
        assert value in spannable, value


def test_ac6b_the_projected_order_is_the_constants_own():
    assert _documented_kinds() == [kind.value for kind in _SPANNABLE_KINDS]


def test_ac6b_the_three_absent_kinds_are_named_WITH_the_constants_own_reasons():
    region = _brief_region().lower()
    for kind in (NewBlockKind.CODE, NewBlockKind.MERMAID, NewBlockKind.TABLE):
        assert kind.value in region, kind.value
    assert "fence" in region and "json record" in region and "rows" in region


def test_ac6b_a_span_really_is_accepted_on_a_kind_the_brief_documents():
    """The projection is only worth anything if the claim behind it holds."""
    for kind in _SPANNABLE_KINDS:
        extra = {"level": 2} if kind is NewBlockKind.HEADING else {}
        block = NewBlock(kind=kind, spans=(TextSpan("see ", ),
                                           TextSpan("here", link_url="https://x")), **extra)
        assert block.text == "see here"
    with pytest.raises(ValueError):
        NewBlock(kind=NewBlockKind.CODE, spans=(TextSpan("x"),))


# --------------------------------------------------------------------------- #
# LD-586 — the family enumeration is a REAL derivation, and a guard proves the  #
#          property that makes it one: a new body-writing family joins the      #
#          answer BY EXISTING, and a review-conversation family does not.       #
#                                                                              #
# The docstring of ``_docx_body_request_families`` promised exactly this while  #
# the body hand-typed a four-name tuple; ``GrowTableRequest`` shipped at LD-575 #
# and did not join, so GUIDE.md shipped a false closed set wearing a            #
# ``derived from the shipped surface`` label for a whole release. Nothing       #
# pinned the enumeration, which is why it rotted silently (S9.3).              #
# --------------------------------------------------------------------------- #

def test_ld586_the_shipped_enumeration_is_the_registrys_own_body_writing_families():
    from larkdocio.write import ops
    from larkdocio.write.absences import _docx_body_request_families

    expected = tuple(sorted(d.request_type.__name__ for d in ops.OPS
                            if d.writes == ops.DOCUMENT_BODY))
    assert _docx_body_request_families() == expected
    # …and the fifth family that rotted this row is really in the answer now.
    assert "GrowTableRequest" in expected
    # …while neither comment family is: they write the review conversation, not the body.
    assert "CreateCommentRequest" not in expected
    assert "RemoveCommentRequest" not in expected


def test_ld586_a_NEW_body_writing_family_joins_the_answer_BY_EXISTING(monkeypatch):
    """The property the docstring promises, driven rather than asserted."""
    from dataclasses import replace as _replace

    from larkdocio.write import ops
    from larkdocio.write.absences import _docx_body_request_families

    class ImaginaryReflowRequest:  # a family that does not exist today
        anchor = None

    body = _replace(ops.OPS[0], kind="imaginary-reflow",
                    request_type=ImaginaryReflowRequest, writes=ops.DOCUMENT_BODY)
    monkeypatch.setattr(ops, "OPS", ops.OPS + (body,))
    assert "ImaginaryReflowRequest" in _docx_body_request_families()


def test_ld586_a_new_REVIEW_CONVERSATION_family_does_NOT_join(monkeypatch):
    from dataclasses import replace as _replace

    from larkdocio.write import ops
    from larkdocio.write.absences import _docx_body_request_families

    class ImaginaryReactionRequest:
        anchor = None

    review = _replace(ops.OPS[0], kind="imaginary-reaction",
                      request_type=ImaginaryReactionRequest,
                      writes=ops.REVIEW_CONVERSATION)
    monkeypatch.setattr(ops, "OPS", ops.OPS + (review,))
    assert "ImaginaryReactionRequest" not in _docx_body_request_families()


def test_ld586_every_registered_op_declares_a_write_target_from_the_ONE_enumeration():
    """The criterion is carried on the registry, so it cannot be forgotten silently."""
    from larkdocio.write import ops

    assert ops.WRITE_TARGETS == (ops.DOCUMENT_BODY, ops.REVIEW_CONVERSATION)
    for desc in ops.OPS:
        assert desc.writes in ops.WRITE_TARGETS, desc.kind
    # A typo is refused at construction rather than silently excluding a family.
    with pytest.raises(Exception):
        ops.OpDescriptor(kind="x", request_type=object, anchor_field="anchor",
                         writes="body", resolve=None, preview=None, apply=None,
                         serialize=None, deserialize=None)


def test_ld586_the_shipped_no_move_row_names_all_five_families_and_KEEPS_its_conclusion():
    row = _rows()["no-move-or-reorder-operation"]
    for name in ("DeleteRequest", "EditRequest", "GrowTableRequest", "InsertRequest",
                 "SubSpanEditRequest"):
        assert name in row["statement"], name
    # the conclusion the enumeration serves is UNCHANGED
    assert "NO move or reorder operation" in row["statement"]
    assert "DELETE-AND-RECREATE" in row["statement"]
