"""LD-574 — the checkbox that reported success and did not move: ship the bit, refuse the rest.

**One change, two halves, and neither ships alone** (maintainer ruling, dev handoff 2026-08-25 § 2.1
ruling 1). Half A makes a ``todo``'s ``done`` bit writable through the plan-gated route, as the
block ``PATCH`` endpoint's **fifth** oneof. Half B refuses — typed — every plan entry the
reconciler accepts as a *change* but whose compiled request set writes bytes identical to what
is already live: the class the checkbox lived in, so closing only the instance would leave the
mechanism intact under another property.

**The wire spelling is CITED, never re-derived here.**
``{"update_text_style": {"style": {"done": <bool>}, "fields": [2]}}`` and its blast radius come
from round 5's own measurement — ``dev/dogfood5/verdict-grid.md`` § 5 **M4** lines 579-583 and
``:966-972`` (a throwaway document, masks ``[1]``/``[2]``/``[3]`` swept, probe deleted with the
deletion independently verified): mask ``2`` moves ``done`` and leaves ``align``, ``folded``,
the item's own text and the nested child's id / text / state untouched. This file proves the
**shipped body** is that spelling; the live gate (``pytest -m live_write``) is what re-proves
the mask against a real document.

Every test below is either an end-to-end drive through the shipped ``reconcile`` →
``compile_reconciliation`` → ``dry_run`` → ``apply`` gate, or a bidirectional projection check.
The two failures the issue weights hardest each have their own section: a refusal predicate
re-derived in a **second** place (F9's shape) and a **false refusal** on a document nobody
edited (F1's shape as a refusal).
"""
import dataclasses
import pathlib

import pytest

from harness import build_blocks
from write_harness import RoutingOpener, _block_payload, _client, _parent_payload

from larkdocio import capabilities, guide
from larkdocio.model import project_block_ids
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import compile_reconciliation
from larkdocio.write.absences import DOCX_WRITE_ABSENCES
from larkdocio.write.apply import apply, build_todo_done_update
from larkdocio.write.compiler import (
    EDIT_UNWRITABLE_BLOCK_FIELDS,
    EDIT_WRITABLE_BLOCK_FIELDS,
)
from larkdocio.write.model import EditRequest, NewBlock, Refusal, RefusedError
from larkdocio.write.model.refusal import RefusalReason
from larkdocio.write.preview import dry_run
from larkdocio.write.reconcile import RECONCILIATION_REFUSAL_REASONS, reconcile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "larkdocio"

#: The register row LD-563 minted for the defect this issue closes, and the row that replaces
#: it in the same slot — the reason preserved, only the conclusion superseded.
RETIRED_ROW_ID = "todo-done-bit-is-not-editable"
SUCCESSOR_ROW_ID = "no-block-property-edit-beyond-text"


# --------------------------------------------------------------------------- #
# Trees. One todo, one bullet, one code block — the three shapes the two halves #
# are about.                                                                    #
# --------------------------------------------------------------------------- #

def _tree(blocks):
    return Parser(Config()).parse_docx_tree("doc1", build_blocks(blocks))


def _page(children):
    return {"block_id": "doc1", "parent_id": "", "block_type": 1,
            "page": {"elements": [{"text_run": {"content": "T"}}]},
            "children": list(children)}


def _todo_tree(done=False, text="ship the thing"):
    todo = {"block_id": "t1", "parent_id": "doc1", "block_type": 17,
            "todo": {"elements": [{"text_run": {"content": text}}],
                     "style": {"done": done}},
            "children": []}
    return _tree([_page(["t1"]), todo])


def _todo_opener(done=False, text="ship the thing"):
    return RoutingOpener(blocks={
        "doc1": _parent_payload("doc1", ["t1"]),
        "t1": _block_payload("t1", [{"text_run": {"content": text}}],
                             block_type=17, key="todo", parent_id="doc1",
                             style={"done": done}),
    })


def _bullet_tree(text="alpha"):
    bullet = {"block_id": "b1", "parent_id": "doc1", "block_type": 12,
              "bullet": {"elements": [{"text_run": {"content": text}}]}, "children": []}
    return _tree([_page(["b1"]), bullet])


def _code_tree(body="x = 1"):
    code = {"block_id": "c1", "parent_id": "doc1", "block_type": 14,
            "code": {"elements": [{"text_run": {"content": body}}],
                     "style": {"language": 49}}, "children": []}
    return _tree([_page(["c1"]), code])


def _compile(tree, replace_pairs):
    """``(requests, projection)`` for a projection edited by literal substitution."""
    projection = project_block_ids(tree)
    edited = projection.markdown
    for old, new in replace_pairs:
        assert old in edited, f"{old!r} is not in the projection: {edited!r}"
        edited = edited.replace(old, new)
    plan = reconcile(projection, edited)
    assert plan.ok, [r.to_dict() for r in plan.refusals]
    return compile_reconciliation(plan, projection), projection, plan


def _refusal_of(tree, replace_pairs):
    with pytest.raises(RefusedError) as excinfo:
        _compile(tree, replace_pairs)
    return excinfo.value.refusal


# --------------------------------------------------------------------------- #
# AC1 — SHIP: the done bit is writable through the plan-gated route.            #
# --------------------------------------------------------------------------- #

def test_ac1_flipping_a_checkbox_compiles_to_a_request_that_carries_the_BIT():
    """The defect's own reproduction, inverted. The compiled edit now carries ``todo_done``;
    before this change the compiled replacement was the block's own unchanged text and no
    request body carried a ``done`` field at all."""
    requests, _projection, _plan = _compile(_todo_tree(), [("[ ]", "[x]")])
    assert len(requests) == 1
    assert isinstance(requests[0], EditRequest)
    assert requests[0].todo_done is True
    assert requests[0].replacement == "ship the thing"


def test_ac1_the_bit_reaches_lark_as_the_CITED_field_mask():
    """``dev/dogfood5/verdict-grid.md:580`` — cited, not re-derived. The body carries the
    ``done`` key and NOTHING else under ``style``, so ``align`` / ``folded`` are untouched
    by construction rather than by a promise (``:581-583`` / ``:966-972``)."""
    requests, _projection, _plan = _compile(_todo_tree(), [("[ ]", "[x]")])
    opener = _todo_opener()
    log = apply(dry_run(requests, _todo_tree()), _client(opener), "doc1")

    assert [e.outcome for e in log.entries] == ["applied"]
    bodies = [c["body"] for c in opener.writes]
    assert {"update_text_style": {"style": {"done": True}, "fields": [2]}} in bodies, bodies


def test_ac1_the_builder_is_the_one_place_the_mask_is_spelled():
    assert build_todo_done_update(True) == {
        "update_text_style": {"style": {"done": True}, "fields": [2]}}
    assert build_todo_done_update(False) == {
        "update_text_style": {"style": {"done": False}, "fields": [2]}}


def test_ac1_unticking_is_the_same_route():
    requests, _projection, _plan = _compile(_todo_tree(done=True), [("[x]", "[ ]")])
    assert requests[0].todo_done is False
    opener = _todo_opener(done=True)
    apply(dry_run(requests, _todo_tree(done=True)), _client(opener), "doc1")
    assert {"update_text_style": {"style": {"done": False}, "fields": [2]}} in [
        c["body"] for c in opener.writes]


def test_ac1a_a_PURE_flip_does_not_rewrite_the_blocks_text():
    """The style-flattening trap. ``build_whole_paragraph_update`` collapses a block to a
    single run and drops every trailing run's style, so writing the block's own text back
    for a flip nobody asked to reword would silently flatten inline styling. One write."""
    requests, _projection, _plan = _compile(_todo_tree(), [("[ ]", "[x]")])
    opener = _todo_opener()
    apply(dry_run(requests, _todo_tree()), _client(opener), "doc1")

    assert len(opener.writes) == 1, opener.writes
    assert "update_text_elements" not in str(opener.writes[0]["body"])


def test_ac1a_a_flip_AND_a_reword_writes_both_halves():
    requests, _projection, _plan = _compile(
        _todo_tree(), [("- [ ] ship the thing", "- [x] ship the other thing")])
    assert requests[0].todo_done is True
    assert requests[0].replacement == "ship the other thing"

    opener = _todo_opener()
    apply(dry_run(requests, _todo_tree()), _client(opener), "doc1")
    bodies = [c["body"] for c in opener.writes]
    assert len(bodies) == 2, bodies
    assert "update_text_elements" in bodies[0]
    assert "update_text_style" in bodies[1]


def test_ac9_a_text_only_todo_edit_is_EXACTLY_what_it_always_was():
    """Zero drift on the path this issue did not come for: one write, the element body, and
    no ``todo_done`` on the request at all."""
    requests, _projection, _plan = _compile(
        _todo_tree(), [("- [ ] ship the thing", "- [ ] ship something else")])
    assert requests[0].todo_done is None

    opener = _todo_opener()
    apply(dry_run(requests, _todo_tree()), _client(opener), "doc1")
    assert len(opener.writes) == 1
    assert "update_text_elements" in opener.writes[0]["body"]


def test_ac1a_the_state_travels_the_WHOLE_chain():
    """Reconcile → compile → dry_run preview → apply → apply-log. A preview that shows a
    text edit while the apply moves a bit is the same silent-success defect one layer over."""
    requests, _projection, _plan = _compile(_todo_tree(), [("[ ]", "[x]")])
    plan = dry_run(requests, _todo_tree())
    assert [e.todo_done for e in plan.entries] == [True]

    log = apply(plan, _client(_todo_opener()), "doc1")
    assert [e.todo_done for e in log.entries] == [True]


@pytest.mark.parametrize("live_done", (False, True))
def test_ac1a_every_serialization_on_the_chain_round_trips_the_bit(live_done):
    """A consumer that persists a plan or a log and brings it back must not lose it — the
    ``snapshot`` / ``load`` shape. Absent ⇒ the key is omitted, so every log and plan written
    before this shipped stays byte-identical."""
    from larkdocio.write.model.applylog import ApplyLog, ApplyLogEntry
    from larkdocio.write.preview import PlanEntry

    flipped_to = not live_done
    old, new = ("[x]", "[ ]") if live_done else ("[ ]", "[x]")
    requests, _projection, _plan = _compile(_todo_tree(done=live_done), [(old, new)])
    assert EditRequest.from_dict(requests[0].to_dict()).todo_done is flipped_to

    plan = dry_run(requests, _todo_tree(done=live_done))
    entry = plan.entries[0]
    assert PlanEntry.from_dict(entry.to_dict()).todo_done is flipped_to

    log = apply(plan, _client(_todo_opener(done=live_done)), "doc1")
    assert ApplyLog.from_dict(log.to_dict()).entries[0].todo_done is flipped_to

    bare = ApplyLogEntry.applied(anchor=log.entries[0].anchor, block_id="t1",
                                 before="a", after="b")
    assert "todo_done" not in bare.to_dict()
    assert bare.todo_done is None


def test_ac1b_it_rides_the_EXISTING_gate_not_a_new_door_beside_it():
    """Inside the plan gate and inside the whole-document compare-and-swap: a plan whose
    document revision moved refuses the WHOLE batch with zero writes, checkbox included."""
    requests, _projection, _plan = _compile(_todo_tree(), [("[ ]", "[x]")])
    opener = RoutingOpener(blocks=_todo_opener().blocks,
                           document_revisions=("rev-2",))
    plan = dry_run(requests, _todo_tree(), document_revision_id="rev-1")
    with pytest.raises(Exception) as excinfo:
        apply(plan, _client(opener), "doc1")
    assert "stale-document" in str(excinfo.value)
    assert opener.writes == []


def test_ac1c_no_new_endpoint_and_no_new_scope():
    """PROVED, not asserted: every call the flip makes is on an endpoint the permissions
    registry already knows, so the registry guard staying green is the whole claim."""
    from larkdocio.permissions import ENDPOINT_SCOPES

    requests, _projection, _plan = _compile(_todo_tree(), [("[ ]", "[x]")])
    opener = _todo_opener()
    apply(dry_run(requests, _todo_tree()), _client(opener), "doc1")

    stems = {row[0].split("/:")[0] for row in ENDPOINT_SCOPES}
    assert opener.writes, "the flip issued no call at all"
    for call in opener.writes:
        assert call["method"] == "PATCH", call
        assert any(stem in call["path"] for stem in stems), (
            f"{call['method']} {call['path']} is on no endpoint the permissions registry "
            f"knows — that would be a new endpoint, and a new scope question with it")


# --------------------------------------------------------------------------- #
# AC2 — REFUSE, TYPED: the compiled-no-op class, and nothing wider.             #
# --------------------------------------------------------------------------- #

def test_ac2a_a_change_the_compiler_writes_NOTHING_for_refuses():
    """Arm (a) — a compiled request whose write is byte-identical to the live pre-image.
    A code block's fence token is the residual instance: same kind, same level, same text,
    and ``EditRequest`` carries text only, so the compiled request would rewrite the body
    with itself and the language would not move."""
    refusal = _refusal_of(_code_tree(), [("```python", "```javascript")])
    assert refusal.reason is RefusalReason.CHANGE_NOT_EXPRESSIBLE


def test_ac2a_a_markdown_only_respelling_refuses_rather_than_reporting_success():
    """Two spellings of the same block. ``- alpha`` and ``* alpha`` are the same bullet with
    the same text, so the reconciler counts a change (the raw Markdown differs) that compiles
    to a rewrite of the block with its own bytes."""
    refusal = _refusal_of(_bullet_tree(), [("- alpha", "* alpha")])
    assert refusal.reason is RefusalReason.CHANGE_NOT_EXPRESSIBLE


@pytest.mark.parametrize("added", ("[ref]: http://example.com", "[^1]: note"))
def test_ac2b_change_count_above_zero_with_an_EMPTY_compiled_batch_refuses(added):
    """**Arm (b), answered in writing rather than assumed** (AC2(b)).

    *Reachable through the public plan API, and this test fires the branch.* An
    ``INSERTED`` entry whose content composes to ZERO blocks makes ``_inserts_for`` emit no
    request at all — it emits one per ``MAX_CHILDREN_PER_CALL`` chunk of content — so
    ``change_count`` counted a change and the batch came out empty. A link-reference
    definition and a footnote definition are exactly that content: CommonMark reads them as
    document metadata, so ``compose()`` returns an empty tuple and raises nothing. A plan
    reaches this shape the same way it reaches :func:`_decoded_verbatim`'s own guard —
    hand-built through the public classmethod, or reloaded through
    ``ReconciliationPlan.from_dict``. The branch is not decorative: this test executes it.

    *NOT reachable through* ``reconcile()`` *with these constructs, and that is derived
    rather than hoped.* Every ``EDITED`` entry compiles to exactly one ``EditRequest`` or
    raises and every ``DELETED`` entry to exactly one ``DeleteRequest``
    (``compile_reconciliation``'s change loop over ``reconcile.py``'s ``_CHANGE_STATES``),
    so ``INSERTED`` is the only arm that can yield zero — and an inserted entry's Markdown
    is always a ``_units`` chunk, cut from markdown-it's own top-level token maps by the
    same parser ``compose()`` uses, so content that produces no block produced no token and
    was never a chunk. Appended to a real segment these two are consumed as definitions and
    nothing is planned for them (``change_count == 0``, which the paved road already refuses
    by naming the zero). ``test_ac2b_no_change_entry_...`` is the guard that reddens if that
    ever stops being true."""
    from larkdocio.write.compose import compose
    from larkdocio.write.reconcile import ReconciliationEntry, ReconciliationPlan

    assert compose(added) == (), "the premise, re-derived rather than trusted"
    projection = project_block_ids(_bullet_tree())

    reconciled = reconcile(projection, projection.markdown.replace(
        "- alpha", f"- alpha\n\n{added}"))
    assert reconciled.ok and reconciled.change_count == 0, (
        "reconcile() plans nothing for content markdown-it consumes as a definition")

    hand_built = ReconciliationPlan(entries=(
        ReconciliationEntry.inserted(added, added, "b1", "after"),))
    assert hand_built.change_count == 1
    reloaded = ReconciliationPlan.from_dict(hand_built.to_dict())

    for plan in (hand_built, reloaded):
        with pytest.raises(RefusedError) as excinfo:
            compile_reconciliation(plan, projection)
        assert excinfo.value.refusal.reason is RefusalReason.CHANGE_NOT_EXPRESSIBLE
        assert "composes to no block" in excinfo.value.refusal.detail


def test_ac2b_no_change_entry_the_reconciler_produces_compiles_to_an_empty_batch():
    """The guard that reddens if the arm above ever becomes reachable from ``reconcile()``:
    a counted change either compiles to at least one request or refuses. Never both zero."""
    corpus = (
        "- alpha edited", "- alpha\n\nadded para", "[ref]: http://x", "[^1]: note",
        "- alpha\n\n[ref]: http://x", "* alpha", "- alpha\n\n- beta",
    )
    projection = project_block_ids(_bullet_tree())
    for edited_body in corpus:
        plan = reconcile(projection, projection.markdown.replace("- alpha", edited_body))
        if not plan.ok or plan.change_count == 0:
            continue
        try:
            requests = compile_reconciliation(plan, projection)
        except RefusedError:
            continue
        assert requests, (
            f"{edited_body!r} counted {plan.change_count} change(s) and compiled to an "
            f"EMPTY batch — the second arm of the compiled-no-op class is now reachable "
            f"from reconcile() and needs its own coverage")


def test_ac2c_the_predicate_is_derived_by_the_SAME_path_that_produces_the_request(monkeypatch):
    """F9's shape, refused. The pre-image is read through the dialect's own ``compose()`` —
    the one place that knows what a block's text is — not through a second pattern of the
    compiler's own. Re-derive either side with a regex and this count drops."""
    from larkdocio.write import compiler as compiler_module

    seen = []
    real = compiler_module.compose

    def counting(markdown):
        seen.append(markdown)
        return real(markdown)

    monkeypatch.setattr(compiler_module, "compose", counting)
    _compile(_todo_tree(), [("[ ]", "[x]")])

    assert any("[x]" in md for md in seen), seen
    assert any("[ ]" in md for md in seen), (
        "the pre-image was not composed through the dialect — a second definition of what a "
        "block's text is has appeared: " + repr(seen))


def test_ac2d_the_residual_is_ENUMERATED_against_the_composed_blocks_own_fields():
    """A negative claim dies with its enumeration. Every field of ``NewBlock`` is classified
    exactly once, and the classification is read off the dataclass — so a tenth field cannot
    join the authoring surface without being placed."""
    names = {f.name for f in dataclasses.fields(NewBlock)}
    assert EDIT_WRITABLE_BLOCK_FIELDS | EDIT_UNWRITABLE_BLOCK_FIELDS == names
    assert not (EDIT_WRITABLE_BLOCK_FIELDS & EDIT_UNWRITABLE_BLOCK_FIELDS)
    assert EDIT_WRITABLE_BLOCK_FIELDS == {"text", "done"}, (
        "the writable set is the request's own reach: ``replacement`` and, since this "
        "change, the fifth oneof's bit")


def test_ac2e_the_refusal_NAMES_the_block_the_property_and_a_route():
    """F8's mirror: the difference between a refusal a consumer can act on and one that
    sends them source-diving is whether it says what to DO."""
    refusal = _refusal_of(_code_tree(), [("```python", "```javascript")])
    detail = refusal.detail
    assert "'c1'" in detail or "c1" in detail
    assert "language" in detail
    assert "delete" in detail.lower() and "insert" in detail.lower()


def test_ac2f_a_document_NOBODY_changed_is_not_refused():
    """F1's shape as a refusal — the trap DIGEST § 7 P1c documents for ``start is None``.
    An unedited projection is a no-op reconciliation: zero changes, an empty batch, and no
    refusal anywhere."""
    for tree in (_todo_tree(), _todo_tree(done=True), _bullet_tree(), _code_tree()):
        projection = project_block_ids(tree)
        plan = reconcile(projection, projection.markdown)
        assert plan.ok and plan.change_count == 0
        assert compile_reconciliation(plan, projection) == ()


def test_ac2f_a_real_text_edit_beside_a_literal_asterisk_is_not_refused():
    """The escaping asymmetry that would produce a false refusal if the pre-image were read
    out of the DECODED text instead of the projection's own Markdown: a block whose live text
    is ``a *b*`` projects as ``a \\*b\\*``, and a consumer who really does rewrite it to
    ``a b`` is making a change the compiler can express."""
    requests, _projection, _plan = _compile(_bullet_tree(text="a *b*"),
                                            [("- a \\*b\\*", "- a b")])
    assert len(requests) == 1
    assert requests[0].replacement == "a b"


def test_ac2f_the_refusal_fires_on_no_other_reconciliation_shape():
    """A plain text edit and a plain insert are untouched: the refusal is the compiled-no-op
    class and nothing wider."""
    from larkdocio.write.model import InsertRequest

    edits, _projection, _plan = _compile(_bullet_tree(), [("- alpha", "- alpha edited")])
    assert [type(r) for r in edits] == [EditRequest]

    inserts, _projection, _plan = _compile(
        _bullet_tree(), [("- alpha", "- alpha\n\nan added paragraph")])
    assert [type(r) for r in inserts] == [InsertRequest]


# --------------------------------------------------------------------------- #
# AC3 — ONE constant, both registries, a guard in BOTH directions.              #
# --------------------------------------------------------------------------- #

def test_ac3_the_reason_is_in_the_enum_and_in_the_CLOSED_reconciliation_registry():
    assert RefusalReason.CHANGE_NOT_EXPRESSIBLE.value == "change-not-expressible"
    assert RefusalReason.CHANGE_NOT_EXPRESSIBLE in RECONCILIATION_REFUSAL_REASONS


def test_ac3_the_factory_is_the_only_way_the_reason_is_spelled_in_src():
    """Round 4's ``STALE_SHEET`` is the precedent: the documented spelling did not equal the
    wire value, ``if reason == "STALE_SHEET"`` never fired, and writes dropped silently. The
    literal appears in ``src`` only where the enum defines it — everywhere else is the
    constant."""
    literal = f'"{RefusalReason.CHANGE_NOT_EXPRESSIBLE.value}"'
    hits = [
        f"{path.relative_to(SRC)}"
        for path in SRC.rglob("*.py")
        if literal in path.read_text(encoding="utf-8")
    ]
    assert hits == ["write/model/refusal.py"], hits


def test_ac3_the_documented_spelling_EQUALS_the_wire_value_both_directions():
    """Bidirectional: the shipped guide states the reason, and what it states is the
    constant's own value."""
    value = RefusalReason.CHANGE_NOT_EXPRESSIBLE.value
    reasons = capabilities(full=True)["surfaces"]["docx-write"]
    text = guide(full=True)
    assert value in text, "a reason absent from every shipped document is undiscoverable"
    assert "change_not_expressible" not in text, (
        "the documented spelling must be the WIRE value, not the enum member name")
    assert value in str(reasons) or value in text


def test_ac3_a_consumer_can_discover_the_reason_from_the_registry_alone():
    values = [r.value for r in RECONCILIATION_REFUSAL_REASONS]
    assert len(values) == len(set(values))
    assert "change-not-expressible" in values


# --------------------------------------------------------------------------- #
# AC4 — NO NEW SUCCESS TOKEN. Present where it fires, absent everywhere else.    #
# --------------------------------------------------------------------------- #

def test_ac4_the_reason_is_PRESENT_on_the_refusal_it_describes():
    """An absence-only guard proves nothing about the field being where it should be."""
    refusal = _refusal_of(_code_tree(), [("```python", "```javascript")])
    assert RefusalReason.CHANGE_NOT_EXPRESSIBLE.value in str(refusal.to_dict())


def test_ac4_the_reason_is_ABSENT_from_every_success_output():
    value = RefusalReason.CHANGE_NOT_EXPRESSIBLE.value
    requests, _projection, plan_reconciled = _compile(_todo_tree(), [("[ ]", "[x]")])
    preview = dry_run(requests, _todo_tree())
    log = apply(preview, _client(_todo_opener()), "doc1")

    for blob in (str(plan_reconciled.to_dict()), str(preview.to_dict()),
                 str(log.to_dict()), str(preview.summary()) if hasattr(preview, "summary")
                 else ""):
        assert value not in blob, blob


# --------------------------------------------------------------------------- #
# AC5 — SAME-CHANGE REGISTER DUTY, reason preserved, conclusion superseded.      #
# --------------------------------------------------------------------------- #

def _rows():
    return {row["id"]: row for row in DOCX_WRITE_ABSENCES}


def test_ac5_the_register_no_longer_claims_the_bit_cannot_be_changed():
    assert RETIRED_ROW_ID not in _rows(), (
        "the register claiming an absence beside a shipped op is F16's shape inverted")


def test_ac5_the_successor_row_occupies_the_SAME_SLOT_and_no_other_row_moves():
    """The tuple's ORDER is load-bearing (``absences.py`` — a consumer's stored index must
    not move for a reason that is not a capability change). The successor takes the retired
    row's slot, so every other row's index is byte-unchanged."""
    ids = [row["id"] for row in DOCX_WRITE_ABSENCES]
    assert ids == [
        "no-move-or-reorder-operation",
        "no-mention-authoring",
        "no-character-style-operation",
        # LD-575 narrowed THIS neighbour in its own slot, on the same terms this row did.
        # Its index is unchanged, which is what this guard is about.
        "no-table-grid-change-beyond-appending-a-row",
        SUCCESSOR_ROW_ID,
        "no-document-retitle-operation",
    ], ids


def test_ac5_the_successor_row_PRESERVES_the_reason_and_supersedes_only_the_conclusion():
    row = _rows()[SUCCESSOR_ROW_ID]
    blob = " ".join(row[k] for k in ("statement", "evidence", "instead"))
    assert RETIRED_ROW_ID in blob, (
        "a rationale-free strike is what gets a settled argument re-litigated")
    assert "supersede" in blob.lower()
    assert "reported success" in blob.lower(), (
        "the preserved reason is the DANGEROUS half of the old row: the engine answered "
        "'applied' while the bit did not move. Drop that and the successor reads as a "
        "boundary somebody chose, which is the sentence LD-563 existed to forbid")


def test_ac5_the_successor_row_is_TRUE_of_the_code_it_describes():
    """Its own claim, re-derived rather than trusted: the residual it names refuses, and the
    property it says now ships really does move the bit."""
    row = _rows()[SUCCESSOR_ROW_ID]
    assert "change-not-expressible" in " ".join(row.values())
    refusal = _refusal_of(_code_tree(), [("```python", "```javascript")])
    assert refusal.reason is RefusalReason.CHANGE_NOT_EXPRESSIBLE
    requests, _p, _pl = _compile(_todo_tree(), [("[ ]", "[x]")])
    assert requests[0].todo_done is True


def test_ac5_the_successor_row_is_projected_verbatim_onto_the_surface():
    projected = capabilities(full=True)["surfaces"]["docx-write"]["absences"]
    assert _rows()[SUCCESSOR_ROW_ID] in projected


# --------------------------------------------------------------------------- #
# AC6 — the shipped surfaces that described the earlier state.              #
# --------------------------------------------------------------------------- #

def test_ac6_the_guides_dialect_todo_row_no_longer_says_write_once():
    row = [ln for ln in guide(full=True).splitlines() if ln.startswith("| `todo` |")]
    assert len(row) == 1, row
    assert "WRITE-ONCE" not in row[0].upper()
    assert "done=True" in row[0] or "done" in row[0]


def test_ac6_the_blocks_matrix_type_17_row_no_longer_states_the_defect():
    line = [ln for ln in (REPO_ROOT / "BLOCKS.md").read_text(encoding="utf-8").splitlines()
            if ln.startswith("| 17 |")]
    assert len(line) == 1
    assert "the `done` bit is not" not in line[0], "the false clause must be gone"
    assert "change-not-expressible" in line[0], "the residual's typed refusal is named"
    assert "open defect" in line[0].lower() and "it is fixed" in line[0].lower(), (
        "the reason is PRESERVED and only the conclusion superseded — a rationale-free "
        "strike is what gets a settled argument re-litigated")


def test_ac6_the_writer_briefs_absence_banner_no_longer_lists_the_checkbox():
    brief = (SRC / "write" / "README.md").read_text(encoding="utf-8")
    assert "no edit of a todo's checkbox" not in brief


# --------------------------------------------------------------------------- #
# AC10 — every measured claim cites where the measurement lives.                 #
# --------------------------------------------------------------------------- #

def test_ac10_the_field_mask_claim_cites_its_measurement_in_the_source():
    """The spelling is round 5's, and the code that carries it says so — nobody re-derives
    it, and nobody has to wonder whether this repo guessed.

    SUPERSEDED IN PART by LD-676: round 5's ``verdict-grid.md`` was pruned on 2026-09-18, so the
    source names the measurement (round 5's verdict grid, § 5 M4) and says it was retired,
    instead of citing a path that leads nowhere. The reason — the spelling is CITED, not
    guessed — is unchanged."""
    text = (SRC / "write" / "apply.py").read_text(encoding="utf-8")
    assert "Round 5 measured them" in text and "verdict grid (§ 5 **M4**)" in text
    assert "update_text_style" in text


def test_ac10_no_bare_universal_in_the_successor_register_row():
    row = _rows()[SUCCESSOR_ROW_ID]
    assert row["verification"] == "derived-from-shipped-code"
    assert "DERIVED-FROM-SHIPPED-CODE" in row["evidence"]
