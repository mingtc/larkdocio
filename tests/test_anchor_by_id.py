"""LD-137 — ``AnchorById`` across the request families.

``apply()`` already handed back ``created_block_ids``, but anchors were **quote-only**, so
following up on a block you just created meant round-tripping a verbatim quote copied out of
a fresh read — needless indirection *and* a staleness risk (dogfood **F19**). This story adds
:class:`~larkdocio.write.model.AnchorById`: **insert / edit / delete** (and, as a consequence
of the ONE shared resolution seam, sub-span) may target a **``block_id``** directly, under the
**same exactly-one-or-refuse** discipline, with a **vanished id refusing with ``detail``**
(LD-131) and **live re-validation still applying** (→ ``stale-anchor`` on drift).

The AC sections below are the contract:

* **AC1** — the type exists, is frozen, JSON-round-trips under its own ``kind`` discriminator,
  and is accepted by insert / edit / delete (one test per family).
* **AC2** — exactly-one-or-refuse: an id resolves to exactly one block or refuses; ids are
  **never** prefix-matched, suffix-matched, case-folded or otherwise guessed.
* **AC3** — a vanished id refuses **with a detail naming the id**; a **write-hostile** id
  refuses *hostile* (not not-found); the document **root** with ``before``/``after`` refuses
  ``cannot-hold-siblings`` (the LD-131 parity), and a leaf with ``append-into`` refuses
  ``cannot-hold-children``.
* **AC4** — live re-validation: an id-anchored apply re-reads the block right before writing
  and refuses ``stale-anchor`` with **no write** on drift (a drifting transport proves it),
  including the **stale race** where the id is deleted *between plan and apply*.
* **AC5** — truth rows: ``capabilities()`` documents both anchor kinds **per request family**,
  projected off the op registry (never hand-listed), and the guide's matrix + recipes agree.

Plus the maintainer's rigor amplifier: an id that never existed, an id from a **different document**,
an id of a **deleted** block, the root-anchor interplay, and a **batch mixing** quote-anchored
and id-anchored requests.
"""
import dataclasses
import json
import typing

import pytest

from log_reading_apply import reading_the_log
import capability_rows as rows
from larkdocio import capabilities
from larkdocio.errors import LarkAPIError
from larkdocio.model import ImageNode, MentionDoc, Text, TextNode
from larkdocio.write.apply import apply
apply = reading_the_log(apply)
from larkdocio.write.model import (
    Anchor,
    AnchorById,
    DeleteRequest,
    EditRequest,
    InsertPosition,
    InsertRequest,
    NewParagraph,
    RefusalReason,
    SubSpanEditRequest,
    TableLocator,
    _anchor_from_dict,
    _request_from_dict,
)
from larkdocio.write.preview import PlanEntry, dry_run
from larkdocio.write.resolve import ResolvedTarget, resolve
from larkdocio.write.ops import OPS

from write_harness import (
    StubOpener,
    _block_payload,
    _by_method,
    _cell,
    _client,
    _heading,
    _methods,
    _page,
    _para,
    _parent_payload,
    _patch_ok,
    _run,
    _table,
)


# --------------------------------------------------------------------------- #
# file-local builders — the by-id request shapes + the create/delete responses   #
# (the quote-anchored equivalents live in write_harness; these are LD-137's).     #
# --------------------------------------------------------------------------- #

def _req_by_id(block_id, replacement="REPLACED"):
    return EditRequest(anchor=AnchorById(block_id=block_id), replacement=replacement)


def _insert_by_id(block_id, position, texts):
    return InsertRequest(
        reference=AnchorById(block_id=block_id),
        position=position,
        content=tuple(NewParagraph(t) for t in texts),
    )


def _delete_by_id(block_id):
    return DeleteRequest(target=AnchorById(block_id=block_id))


def _create_ok(created_ids):
    return {"code": 0, "data": {
        "children": [{"block_id": bid} for bid in created_ids],
        "document_revision_id": 200,
    }}


def _delete_ok():
    return {"code": 0, "data": {"document_revision_id": 201}}


def _not_found(block_id):
    """A get_block reply for a block that is GONE — the stale-race payload.

    Lark answers a read of a deleted block with a non-zero ``code``, which the shared
    transport turns into a :class:`~larkdocio.errors.LarkAPIError`. This is the payload the
    engine must convert into a ``stale-anchor`` refusal rather than abort the whole batch.
    """
    return {"code": 1770002, "msg": f"block {block_id} not found"}


def _tree():
    """The shared fixture tree: a page → heading → two paragraphs, plus a flat third."""
    return _page(
        _heading("h1", "Overview", children=[_para("p1", "first line")]),
        _para("p2", "second line"),
        _para("p3", "third line"),
    )


# =========================================================================== #
# AC1 — AnchorById exists, is frozen, JSON-round-trips, discriminates cleanly.  #
# =========================================================================== #

def test_ac1_anchor_by_id_is_frozen_and_carries_the_block_id():
    anchor = AnchorById(block_id="doxcnABC123")
    assert anchor.block_id == "doxcnABC123"
    with pytest.raises(dataclasses.FrozenInstanceError):
        anchor.block_id = "other"


def test_ac1_anchor_by_id_is_hashable_and_compares_by_value():
    assert AnchorById("a") == AnchorById("a")
    assert AnchorById("a") != AnchorById("b")
    assert len({AnchorById("a"), AnchorById("a")}) == 1


def test_ac1_anchor_by_id_json_round_trips_under_its_own_kind_tag():
    anchor = AnchorById(block_id="doxcnABC123")
    d = anchor.to_dict()
    assert d == {"kind": "by-id", "block_id": "doxcnABC123"}
    assert json.loads(json.dumps(d)) == d
    assert AnchorById.from_dict(d) == anchor


def test_ac1_the_anchor_dispatcher_tells_all_three_shapes_apart():
    """One dispatcher, three shapes: the tagless W1 :class:`Anchor` (byte-unchanged), the
    ``kind: table`` :class:`TableLocator`, and the new ``kind: by-id``."""
    assert isinstance(_anchor_from_dict({"quote": "q", "breadcrumb": []}), Anchor)
    assert isinstance(
        _anchor_from_dict({"kind": "table", "row_key": "r", "column_index": 0}), TableLocator)
    by_id = _anchor_from_dict({"kind": "by-id", "block_id": "b1"})
    assert isinstance(by_id, AnchorById) and by_id.block_id == "b1"


def test_ac1_an_empty_block_id_is_refused_at_construction():
    """An empty id locates nothing, so it is refused where it is built — never carried into
    a plan to fail later."""
    with pytest.raises(ValueError) as ei:
        AnchorById(block_id="")
    assert "block_id" in str(ei.value)
    with pytest.raises(ValueError):
        AnchorById(block_id="   ")


def test_ac1_a_non_string_block_id_is_refused_at_construction():
    with pytest.raises(TypeError):
        AnchorById(block_id=123)


def test_ac1_edit_request_accepts_an_id_anchor_and_round_trips():
    """AC1 (family 1/3 — edit)."""
    request = _req_by_id("p2", replacement="NEW")
    assert isinstance(request.anchor, AnchorById)
    d = request.to_dict()
    assert d["anchor"] == {"kind": "by-id", "block_id": "p2"}
    back = _request_from_dict(json.loads(json.dumps(d)))
    assert isinstance(back, EditRequest) and back == request


def test_ac1_insert_request_accepts_an_id_reference_and_round_trips():
    """AC1 (family 2/3 — insert)."""
    request = _insert_by_id("p2", InsertPosition.AFTER, ["hello"])
    assert isinstance(request.reference, AnchorById)
    d = request.to_dict()
    assert d["op"] == "insert"
    assert d["reference"] == {"kind": "by-id", "block_id": "p2"}
    back = _request_from_dict(json.loads(json.dumps(d)))
    assert isinstance(back, InsertRequest) and back == request


def test_ac1_delete_request_accepts_an_id_target_and_round_trips():
    """AC1 (family 3/3 — delete). Dogfood F19's headline: "deletes cannot target block ids"."""
    request = _delete_by_id("p2")
    assert isinstance(request.target, AnchorById)
    d = request.to_dict()
    assert d == {"op": "delete", "target": {"kind": "by-id", "block_id": "p2"}}
    back = _request_from_dict(json.loads(json.dumps(d)))
    assert isinstance(back, DeleteRequest) and back == request


def test_ac1_subspan_request_accepts_an_id_anchor_and_round_trips():
    """The fourth family comes free from the ONE shared resolution seam (documented
    extension — the AC names insert/edit/delete, and forking the resolver to *withhold*
    by-id from sub-span would be the drift the op registry exists to prevent)."""
    request = SubSpanEditRequest(anchor=AnchorById("p2"), span="second", replacement="2nd")
    d = request.to_dict()
    assert d["op"] == "subspan"
    assert d["anchor"] == {"kind": "by-id", "block_id": "p2"}
    back = _request_from_dict(json.loads(json.dumps(d)))
    assert isinstance(back, SubSpanEditRequest) and back == request


def test_ac1_the_quote_anchor_wire_form_is_byte_unchanged():
    """Zero-churn: the tagless W1 anchor serialization is untouched by the new kind."""
    assert Anchor(quote="q", breadcrumb=("H",)).to_dict() == {
        "quote": "q", "breadcrumb": ["H"]}


# =========================================================================== #
# AC2 — exactly-one-or-refuse; ids are never guessed / fuzzy-matched.           #
# =========================================================================== #

def test_ac2_an_id_resolves_to_exactly_that_block():
    tree = _tree()
    result = resolve(_req_by_id("p3"), tree)
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "p3"
    assert result.node.block_id == "p3"
    assert result.cell is None and result.insertion is None


def test_ac2_an_id_resolves_a_block_a_quote_would_find_ambiguous():
    """The point of by-id: three blocks share text, so no quote resolves — the id does."""
    tree = _page(_para("a1", "same text"), _para("a2", "same text"), _para("a3", "same text"))
    quoted = resolve(EditRequest(anchor=Anchor(quote="same text"), replacement="x"), tree)
    assert quoted.reason is RefusalReason.AMBIGUOUS
    by_id = resolve(_req_by_id("a2"), tree)
    assert isinstance(by_id, ResolvedTarget) and by_id.block_id == "a2"


@pytest.mark.parametrize("probe", ["p", "p3x", "P3", " p3", "p3 ", "3"])
def test_ac2_no_partial_prefix_suffix_or_case_variant_ever_resolves(probe):
    """AC2's negative half: id matching is **exact string equality**. A prefix, a suffix, a
    case variant or a whitespace-padded id must refuse — never resolve to the near match."""
    tree = _tree()
    result = resolve(_req_by_id(probe), tree)
    assert not isinstance(result, ResolvedTarget), (
        f"{probe!r} must NOT resolve — ids are never guessed")
    assert result.reason is RefusalReason.NOT_FOUND


def test_ac2_an_id_from_a_different_document_refuses():
    """The amplifier: an id that is perfectly real — in ANOTHER document — is not in this
    tree, so it refuses (the engine never reaches across documents)."""
    other_doc = _page(_para("zzz-other-doc", "content over there"))
    assert isinstance(resolve(_req_by_id("zzz-other-doc"), other_doc), ResolvedTarget)
    result = resolve(_req_by_id("zzz-other-doc"), _tree())
    assert result.reason is RefusalReason.NOT_FOUND
    assert "zzz-other-doc" in result.detail


def test_ac2_an_id_that_never_existed_refuses():
    result = resolve(_req_by_id("never-existed-anywhere"), _tree())
    assert result.reason is RefusalReason.NOT_FOUND
    assert "never-existed-anywhere" in result.detail


def test_ac2_duplicate_ids_refuse_ambiguous_and_never_auto_pick():
    """Defensive exactly-one-or-refuse: a malformed tree carrying the same id twice must
    refuse with BOTH candidates, never silently take the first."""
    tree = _page(_para("dup", "first copy"), _para("dup", "second copy"))
    result = resolve(_req_by_id("dup"), tree)
    assert result.reason is RefusalReason.AMBIGUOUS
    assert result.candidate_ids == ("dup", "dup")
    assert result.candidate_count == 2


def test_ac2_an_id_resolves_a_block_nested_inside_a_container():
    """The walk is the shared one, so a nested block is addressable (p1 lives under h1)."""
    result = resolve(_req_by_id("p1"), _tree())
    assert isinstance(result, ResolvedTarget) and result.block_id == "p1"


def test_ac2_an_id_resolves_a_table_cell_for_a_delete_but_not_for_a_text_edit():
    """A container carries no text of its OWN, so a whole-block text replacement has
    nothing to patch — that refuses. Deleting it by id is legitimate and resolves."""
    tree = _page(_table("t1", [[("c1", "Metric"), ("c2", "Value")]]))
    edit = resolve(_req_by_id("c1"), tree)
    assert edit.reason is RefusalReason.WRITE_HOSTILE
    assert "c1" in edit.detail
    deleted = resolve(_delete_by_id("t1"), tree)
    assert isinstance(deleted, ResolvedTarget) and deleted.block_id == "t1"


# =========================================================================== #
# AC3 — a vanished id refuses WITH detail; the typed-reason discipline holds.   #
# =========================================================================== #

@pytest.mark.parametrize("build", [
    pytest.param(lambda bid: _req_by_id(bid), id="edit"),
    pytest.param(lambda bid: _insert_by_id(bid, InsertPosition.AFTER, ["x"]), id="insert"),
    pytest.param(lambda bid: _delete_by_id(bid), id="delete"),
    pytest.param(lambda bid: SubSpanEditRequest(anchor=AnchorById(bid), span="s",
                                                replacement="r"), id="subspan"),
])
def test_ac3_a_vanished_id_refuses_with_a_detail_naming_the_id(build):
    """AC3 — every family: the refusal is typed, carries a NON-EMPTY detail, and that detail
    NAMES the id (the LD-131 mandatory-detail contract: an agent that reads
    ``{"reason": "not-found"}`` has nothing to recover from)."""
    result = resolve(build("doxcnGONE999"), _tree())
    assert result.reason is RefusalReason.NOT_FOUND
    assert result.detail and result.detail.strip()
    assert "doxcnGONE999" in result.detail


def test_ac3_the_vanished_id_detail_is_actionable_not_decorative():
    """The detail must say WHY and WHAT TO DO — that the match is exact (so hunting for a
    near-miss id is pointless) and that the repair is a re-read/re-plan."""
    detail = resolve(_req_by_id("doxcnGONE999"), _tree()).detail.lower()
    assert "exact" in detail, detail
    assert "re-read" in detail or "re-plan" in detail, detail


def test_ac3_an_id_of_a_deleted_block_refuses_with_detail():
    """The amplifier: the id WAS real. The block is gone from the tree, so it refuses —
    with the id named, which is what tells the consumer their id is stale."""
    tree_before = _tree()
    assert isinstance(resolve(_req_by_id("p2"), tree_before), ResolvedTarget)

    tree_after = _page(
        _heading("h1", "Overview", children=[_para("p1", "first line")]),
        _para("p3", "third line"),
    )
    result = resolve(_delete_by_id("p2"), tree_after)
    assert result.reason is RefusalReason.NOT_FOUND
    assert "p2" in result.detail


def test_ac3_a_write_hostile_id_refuses_hostile_not_not_found():
    """The amplifier: the id RESOLVED — it is an image. Saying ``not-found`` would send the
    consumer hunting for a better id when the block simply is not text-patchable."""
    tree = _page(ImageNode(caption="revenue chart", block_id="img"))
    result = resolve(_req_by_id("img"), tree)
    assert result.reason is RefusalReason.WRITE_HOSTILE
    assert "img" in result.detail
    assert "ImageNode" in result.detail


def test_ac3_the_root_id_with_before_or_after_refuses_cannot_hold_siblings():
    """The LD-131 parity the issue calls out: the root resolved (the anchor was FOUND), it
    just has no sibling position — so it is a POSITION failure, not a resolution one, and
    the detail must point at the position that works."""
    tree = _tree()
    for position in (InsertPosition.BEFORE, InsertPosition.AFTER):
        result = resolve(_insert_by_id("root", position, ["x"]), tree)
        assert result.reason is RefusalReason.CANNOT_HOLD_SIBLINGS, position
        assert "root" in result.detail
        assert "append-into" in result.detail
        assert "block_id" in result.detail, (
            "the detail must name the anchor kind that was used, not a phantom quote")


def test_ac3_the_root_id_with_append_into_resolves():
    """The mirror half of the LD-131 contract: the identical anchor WORKS with append-into,
    which is exactly why refusing before/after as ``not-found`` would be a lie."""
    result = resolve(_insert_by_id("root", InsertPosition.APPEND_INTO, ["x"]), _tree())
    assert isinstance(result, ResolvedTarget)
    assert result.insertion.parent_block_id == "root"
    assert result.insertion.index == 3


def test_ac3_a_leaf_id_with_append_into_refuses_cannot_hold_children():
    result = resolve(_insert_by_id("p3", InsertPosition.APPEND_INTO, ["x"]), _tree())
    assert result.reason is RefusalReason.CANNOT_HOLD_CHILDREN
    assert "p3" in result.detail
    assert "block_id" in result.detail


def test_ac3_a_subspan_by_id_whose_span_is_absent_refuses_naming_the_id():
    result = resolve(
        SubSpanEditRequest(anchor=AnchorById("p3"), span="nowhere", replacement="x"), _tree())
    assert result.reason is RefusalReason.NOT_FOUND
    assert "p3" in result.detail and "nowhere" in result.detail


# =========================================================================== #
# AC3/AC1 — id-anchored insert positions: BEFORE / AFTER / APPEND_INTO.         #
# =========================================================================== #

@pytest.mark.parametrize("position,parent,index", [
    (InsertPosition.BEFORE, "root", 1),
    (InsertPosition.AFTER, "root", 2),
])
def test_ac1_id_anchored_insert_computes_the_same_point_a_quote_anchor_would(
        position, parent, index):
    """An id-anchored insert computes its insertion point through the SAME resolver, so
    before/after/append-into semantics are identical to the quote path."""
    tree = _tree()
    by_id = resolve(_insert_by_id("p2", position, ["x"]), tree)
    by_quote = resolve(
        InsertRequest(reference=Anchor(quote="second line"), position=position,
                      content=(NewParagraph("x"),)),
        tree,
    )
    assert by_id.insertion.to_dict() == by_quote.insertion.to_dict()
    assert by_id.insertion.parent_block_id == parent
    assert by_id.insertion.index == index


def test_ac1_id_anchored_append_into_a_container_appends_last():
    result = resolve(_insert_by_id("h1", InsertPosition.APPEND_INTO, ["x"]), _tree())
    assert result.insertion.parent_block_id == "h1"
    assert result.insertion.index == 1


# =========================================================================== #
# Preview — the plan carries the id anchor + the captured live-basis precondition#
# =========================================================================== #

def test_the_plan_entry_carries_the_id_anchor_and_round_trips():
    plan = dry_run([_req_by_id("p3", "NEW")], _tree())
    (entry,) = plan.entries
    assert entry.is_resolved and entry.block_id == "p3"
    assert entry.anchor == AnchorById("p3")
    d = entry.to_dict()
    assert d["anchor"] == {"kind": "by-id", "block_id": "p3"}
    assert PlanEntry.from_dict(json.loads(json.dumps(d))) == entry


def test_the_plan_captures_the_live_basis_precondition_for_an_id_anchor():
    """A quote anchor re-validates against its own quote; an id anchor has none, so the plan
    captures the block's **text-run-basis** text (the offline mirror of what the apply engine
    reads live) as the by-id staleness precondition."""
    plan = dry_run([_req_by_id("p3", "NEW")], _tree())
    (entry,) = plan.entries
    assert entry.precondition_text == "third line"
    assert entry.to_dict()["precondition_text"] == "third line"


def test_a_quote_anchored_entry_carries_no_precondition_and_its_json_is_unchanged():
    """Zero-drift on the shipped wire format: a quote-anchored entry gains no field."""
    plan = dry_run(
        [EditRequest(anchor=Anchor(quote="third line"), replacement="NEW")], _tree())
    (entry,) = plan.entries
    assert entry.precondition_text is None
    assert "precondition_text" not in entry.to_dict()


@pytest.mark.parametrize("build,expected", [
    pytest.param(lambda: _insert_by_id("p3", InsertPosition.AFTER, ["x"]), "third line",
                 id="insert"),
    pytest.param(lambda: _delete_by_id("p3"), "third line", id="delete"),
])
def test_every_id_anchored_op_captures_its_precondition(build, expected):
    plan = dry_run([build()], _tree())
    (entry,) = plan.entries
    assert entry.precondition_text == expected
    assert PlanEntry.from_dict(entry.to_dict()).precondition_text == expected


# --------------------------------------------------------------------------- #
# THE PRECONDITION BASIS — the trap that makes an UNCHANGED block look drifted.  #
# --------------------------------------------------------------------------- #

def _tree_with_a_mention():
    """A paragraph carrying a text run **and a doc mention**.

    The two plain-text bases disagree on exactly this shape: ``block_plain_text`` counts a
    mention's ``title`` (it is visible text a consumer would quote), while the apply engine's
    live basis counts **only** ``text_run`` elements — which is all a mention contributes to a
    ``get_block`` payload's runs. So capturing the by-id precondition on the wrong basis makes
    an untouched block look drifted.
    """
    return _page(_para("m1", None, inlines=[Text("see "), MentionDoc("Spec", "https://x/y")]))


def test_the_precondition_uses_the_LIVE_basis_not_the_richer_quote_basis():
    """The plan must capture what the apply engine will actually read back."""
    plan = dry_run([_req_by_id("m1", "NEW")], _tree_with_a_mention())
    (entry,) = plan.entries
    assert entry.before == "see Spec", (
        "`before` is the consumer-facing preview and DOES include the mention's title")
    assert entry.precondition_text == "see ", (
        "the precondition must be the text-run-only basis the live block reads back as — "
        "counting the mention's title here would make an unchanged block look drifted")


def test_an_unchanged_block_with_a_mention_is_not_falsely_stale():
    """The regression this basis choice exists for: an id-anchored edit of an untouched
    paragraph that happens to contain a **mention** must APPLY, not refuse stale-anchor.

    The live payload's runs carry only ``"see "`` (a mention is not a ``text_run``), so a
    precondition captured on the richer quote basis (``"see Spec"``) would never match and the
    write would refuse forever — a silent, permanent false negative on a perfectly ordinary
    paragraph.
    """
    plan = dry_run([_req_by_id("m1", "NEW")], _tree_with_a_mention())
    opener = StubOpener([
        _block_payload("m1", [_run("see "), {"mention_doc": {"title": "Spec"}}]),
        _patch_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")
    (entry,) = log.entries
    assert entry.outcome == "applied", (
        f"an UNCHANGED block containing a mention was reported stale: {entry.to_dict()}")
    assert _methods(opener) == ["GET", "PATCH"]


def test_a_genuinely_changed_block_with_a_mention_still_refuses():
    """…and the guard is not simply defanged: change the text run and it still refuses."""
    plan = dry_run([_req_by_id("m1", "NEW")], _tree_with_a_mention())
    opener = StubOpener([
        _block_payload("m1", [_run("EDITED "), {"mention_doc": {"title": "Spec"}}]),
        _patch_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")
    assert log.entries[0].refusal.reason is RefusalReason.STALE_ANCHOR
    assert _methods(opener) == ["GET"]


# =========================================================================== #
# AC4 — live re-validation: drift → stale-anchor, NO write.                     #
# =========================================================================== #

def test_ac4_an_id_anchored_edit_applies_when_the_block_is_unchanged():
    plan = dry_run([_req_by_id("p3", "REWRITTEN")], _tree())
    opener = StubOpener([_block_payload("p3", [_run("third line")]), _patch_ok()])
    log = apply(plan, _client(opener), "doc123")
    (entry,) = log.entries
    assert entry.outcome == "applied"
    assert entry.block_id == "p3"
    assert entry.before == "third line" and entry.after == "REWRITTEN"
    assert _methods(opener) == ["GET", "PATCH"]


def test_ac4_an_id_anchored_edit_refuses_stale_anchor_when_the_block_drifted():
    """AC4 — the drifting transport: the live block no longer carries what the plan
    previewed, so the write is refused and **never issued**."""
    plan = dry_run([_req_by_id("p3", "REWRITTEN")], _tree())
    opener = StubOpener([
        _block_payload("p3", [_run("somebody else rewrote this")]), _patch_ok()])
    log = apply(plan, _client(opener), "doc123")
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR
    assert "p3" in entry.refusal.detail
    assert _methods(opener) == ["GET"], "a stale id-anchored edit must issue NO write"


def test_ac4_the_stale_detail_names_the_expected_and_the_live_text():
    plan = dry_run([_req_by_id("p3", "REWRITTEN")], _tree())
    opener = StubOpener([_block_payload("p3", [_run("drifted away")]), _patch_ok()])
    log = apply(plan, _client(opener), "doc123")
    detail = log.entries[0].refusal.detail
    assert "third line" in detail and "drifted away" in detail
    assert "re-plan" in detail.lower()


def test_ac4_an_id_anchored_delete_refuses_stale_anchor_on_drift_and_removes_nothing():
    plan = dry_run([_delete_by_id("p3")], _tree())
    opener = StubOpener([
        _block_payload("p3", [_run("changed under us")], parent_id="root"),
        _parent_payload("root", ["p1", "p2", "p3"]),
        _delete_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR
    assert not _by_method(opener, "DELETE"), "a stale delete must remove nothing"


def test_ac4_an_id_anchored_delete_applies_and_captures_the_removed_payload():
    plan = dry_run([_delete_by_id("p3")], _tree())
    opener = StubOpener([
        _block_payload("p3", [_run("third line", bold=True)], parent_id="root"),
        _parent_payload("root", ["p1", "p2", "p3"]),
        _delete_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")
    (entry,) = log.entries
    assert entry.outcome == "deleted"
    assert entry.block_id == "p3"
    assert entry.removed_payload["elements"][0]["text_run"]["content"] == "third line"
    assert _by_method(opener, "DELETE")


def test_ac4_an_id_anchored_insert_refuses_stale_anchor_when_the_reference_drifted():
    plan = dry_run([_insert_by_id("p3", InsertPosition.AFTER, ["brand new"])], _tree())
    opener = StubOpener([
        _block_payload("p3", [_run("the reference changed")]), _create_ok(["newX"])])
    log = apply(plan, _client(opener), "doc123")
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR
    assert not _by_method(opener, "POST"), "a stale insert must create nothing"


def test_ac4_an_id_anchored_insert_applies_and_reports_the_created_ids():
    plan = dry_run([_insert_by_id("p3", InsertPosition.AFTER, ["brand new"])], _tree())
    # LD-453: an insert reads its LIVE parent for the index, so the reference payload
    # carries its parent_id (as the real API always does) and the parent answers next.
    opener = StubOpener([
        _block_payload("p3", [_run("third line")], parent_id="root"),
        _parent_payload("root", ["p1", "p2", "p3"]),
        _create_ok(["newX"]),
    ])
    log = apply(plan, _client(opener), "doc123")
    (entry,) = log.entries
    assert entry.outcome == "inserted"
    assert entry.created_block_ids == ("newX",)


@pytest.mark.parametrize("build,reads", [
    pytest.param(lambda: _req_by_id("p3", "x"), 1, id="edit"),
    pytest.param(lambda: _insert_by_id("p3", InsertPosition.AFTER, ["x"]), 1, id="insert"),
    pytest.param(lambda: _delete_by_id("p3"), 1, id="delete"),
    pytest.param(lambda: SubSpanEditRequest(anchor=AnchorById("p3"), span="third",
                                            replacement="3rd"), 1, id="subspan"),
])
def test_ac4_the_stale_race_an_id_deleted_between_plan_and_apply_refuses(build, reads):
    """The amplifier's stale race: the block is **deleted between plan and apply**, so the
    pre-write re-validation read itself fails. That is staleness — the engine must record a
    typed ``stale-anchor`` refusal (with the id and Lark's own code/msg in the detail) and
    issue **no write**, never abort the batch with an exception and no apply-log."""
    plan = dry_run([build()], _tree())
    opener = StubOpener([_not_found("p3")])
    log = apply(plan, _client(opener), "doc123")
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR
    assert "p3" in entry.refusal.detail
    assert "1770002" in entry.refusal.detail, "Lark's own code must ride in the detail"
    assert _methods(opener) == ["GET"] * reads, "no write may be issued for a vanished block"


@pytest.mark.parametrize("build,payloads,outcome", [
    pytest.param(lambda: _req_by_id("p3", "x"),
                 [_block_payload("p3", [_run("third line")]), _patch_ok()],
                 "applied", id="applied"),
    pytest.param(lambda: _delete_by_id("p3"),
                 [_block_payload("p3", [_run("third line")], parent_id="root"),
                  _parent_payload("root", ["p1", "p2", "p3"]), _delete_ok()],
                 "deleted", id="deleted"),
    pytest.param(lambda: _insert_by_id("p3", InsertPosition.AFTER, ["x"]),
                 [_block_payload("p3", [_run("third line")], parent_id="root"),
                  _parent_payload("root", ["p1", "p2", "p3"]), _create_ok(["newX"])],
                 "inserted", id="inserted"),
    pytest.param(lambda: _req_by_id("p3", "x"),
                 [_block_payload("p3", [_run("drifted")]), _patch_ok()],
                 "refused", id="refused"),
])
def test_the_apply_log_round_trips_an_id_anchored_entry(build, payloads, outcome):
    """The apply-log is the consumer-facing record, so an id-anchored outcome must survive
    JSON both ways — the anchor comes back as an ``AnchorById``, not a mangled quote anchor."""
    from larkdocio.write.model import ApplyLog

    plan = dry_run([build()], _tree())
    log = apply(plan, _client(StubOpener(payloads)), "doc123")
    assert [e.outcome for e in log.entries] == [outcome]
    assert log.entries[0].anchor == AnchorById("p3")
    back = ApplyLog.from_json(log.to_json())
    assert back == log
    assert isinstance(back.entries[0].anchor, AnchorById)


def test_ac4_the_stale_race_also_protects_a_quote_anchored_entry():
    """The same protection, one engine: a quote-anchored entry whose block vanished between
    plan and apply refuses instead of raising — a batch is never left half-applied with no
    apply-log to show for it."""
    plan = dry_run(
        [EditRequest(anchor=Anchor(quote="third line"), replacement="x")], _tree())
    opener = StubOpener([_not_found("p3")])
    log = apply(plan, _client(opener), "doc123")
    assert log.entries[0].refusal.reason is RefusalReason.STALE_ANCHOR
    assert _methods(opener) == ["GET"]


def test_ac4_a_rate_limit_on_the_revalidation_read_is_not_swallowed_as_staleness():
    """The narrow half of the same rule: throttling is NOT staleness, so it can never be
    misreported as a drifted anchor.

    **TRANSFORMED, NOT STRUCK (LD-643).** The rule above is unchanged and is still what this
    test checks — the assertion that the reason is not ``stale-anchor`` is the first line
    below. What LD-643 supersedes is the parenthesis that used to follow it, *"a rate-limit
    error must still propagate (the transport owns backoff)"*: the transport still owns
    backoff and still retries, and what changed is only where the survivor lands. It no
    longer escapes ``apply()`` leaving the caller no record of the entries that already wrote;
    it is classified ``rate-limited`` in a log 1:1 with the plan.
    """
    plan = dry_run([_req_by_id("p3", "x")], _tree())
    opener = StubOpener([{"code": 99991400, "msg": "too many requests"}] * 12)
    log = apply(plan, _client(opener), "doc123")

    entry = log.entries[0]
    assert entry.refusal.reason is not RefusalReason.STALE_ANCHOR
    assert entry.refusal.reason is RefusalReason.RATE_LIMITED
    assert entry.outcome == "refused"
    assert _by_method(opener, "PATCH") == [], "no write after a rate limit"


def test_ac4_an_id_anchored_subspan_edit_patches_only_the_span():
    plan = dry_run(
        [SubSpanEditRequest(anchor=AnchorById("p3"), span="third", replacement="3rd")],
        _tree())
    opener = StubOpener([_block_payload("p3", [_run("third line")]), _patch_ok()])
    log = apply(plan, _client(opener), "doc123")
    (entry,) = log.entries
    assert entry.outcome == "applied"
    body = _by_method(opener, "PATCH")[0]["body"]
    runs = [e["text_run"]["content"] for e in body["update_text_elements"]["elements"]]
    assert runs == ["3rd", " line"]


# =========================================================================== #
# The mixed batch — quote-anchored and id-anchored requests in ONE plan.        #
# =========================================================================== #

def test_a_batch_mixing_quote_anchored_and_id_anchored_requests_applies_in_order():
    """The amplifier's mixed batch: one ``dry_run``, three ops, two anchor kinds. The
    apply-log stays 1:1 with the plan, in order, and each op issues its own write."""
    tree = _tree()
    requests = [
        InsertRequest(reference=Anchor(quote="first line", breadcrumb=("Overview",)),
                      position=InsertPosition.AFTER, content=(NewParagraph("added"),)),
        _delete_by_id("p2"),
        _req_by_id("p3", "REWRITTEN BY ID"),
    ]
    plan = dry_run(requests, tree)
    assert len(plan.refusals) == 0, plan.refusals
    assert [e.op for e in plan.entries] == ["insert", "delete", "edit"]
    assert [e.precondition_text for e in plan.entries] == [None, "second line", "third line"]

    opener = StubOpener([
        _block_payload("p1", [_run("first line")], parent_id="h1"),   # insert reference
        _parent_payload("h1", ["p1"]),                                # its LIVE parent (LD-453)
        _create_ok(["newA"]),
        _block_payload("p2", [_run("second line")], parent_id="root"),  # delete target
        _parent_payload("root", ["h1", "p2", "p3"]),
        _delete_ok(),
        _block_payload("p3", [_run("third line")]),                   # edit target
        _patch_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")
    assert [e.outcome for e in log.entries] == ["inserted", "deleted", "applied"]
    assert _methods(opener) == ["GET", "GET", "POST", "GET", "GET", "DELETE", "GET", "PATCH"]


def test_a_mixed_batch_refuses_only_the_bad_entry():
    """One refusal does not poison its neighbours: the id that never existed refuses at
    dry-run while the quote-anchored edit still resolves and applies."""
    plan = dry_run([_req_by_id("nope"), _req_by_id("p3", "OK")], _tree())
    assert [e.outcome for e in plan.entries] == ["refused", "resolved"]
    opener = StubOpener([_block_payload("p3", [_run("third line")]), _patch_ok()])
    log = apply(plan, _client(opener), "doc123")
    assert [e.outcome for e in log.entries] == ["refused", "applied"]
    assert _methods(opener) == ["GET", "PATCH"]


# =========================================================================== #
# The consumer loop — apply() returns created ids; a follow-up anchors by them.  #
# =========================================================================== #

def test_the_consumer_loop_created_ids_feed_an_id_anchored_follow_up():
    """Dogfood F19's ask, end to end offline: insert → ``created_block_ids`` → re-parse →
    anchor the follow-up **by id** (no re-quoting the text you just wrote)."""
    tree = _tree()
    insert_plan = dry_run(
        [_insert_by_id("p3", InsertPosition.AFTER, ["a freshly authored line"])], tree)
    opener = StubOpener([
        _block_payload("p3", [_run("third line")], parent_id="root"),
        _parent_payload("root", ["p1", "p2", "p3"]), _create_ok(["newP"]),   # LD-453
    ])
    insert_log = apply(insert_plan, _client(opener), "doc123")
    (created_id,) = insert_log.entries[0].created_block_ids

    # the re-read the consumer does anyway — now with the created block in the tree.
    refreshed = _page(
        _heading("h1", "Overview", children=[_para("p1", "first line")]),
        _para("p2", "second line"),
        _para("p3", "third line"),
        _para(created_id, "a freshly authored line"),
    )
    follow_up = dry_run([_req_by_id(created_id, "revised by id")], refreshed)
    (entry,) = follow_up.entries
    assert entry.is_resolved and entry.block_id == created_id
    opener2 = StubOpener([
        _block_payload(created_id, [_run("a freshly authored line")]), _patch_ok()])
    log = apply(follow_up, _client(opener2), "doc123")
    assert log.entries[0].outcome == "applied"


# =========================================================================== #
# AC5 — truth rows: capabilities() documents both anchor kinds per family.       #
# =========================================================================== #

def _anchor_field_annotation(desc):
    return typing.get_type_hints(desc.request_type)[desc.anchor_field]


def _docx_write_ops():
    return rows.by_name(capabilities(full=True)["surfaces"]["docx-write"], rows.OPERATION)


def test_ac5_every_docx_write_op_declares_which_field_carries_its_anchor():
    """The projection needs code truth to read, so each ``OpDescriptor`` names its anchor
    field — and that name must be a real dataclass field of its request type."""
    for desc in OPS:
        fields = {f.name for f in dataclasses.fields(desc.request_type)}
        assert desc.anchor_field in fields, (
            f"op {desc.kind!r} declares anchor_field={desc.anchor_field!r}, which is not a "
            f"field of {desc.request_type.__name__} ({sorted(fields)})")


def test_ac5_capabilities_documents_both_anchor_kinds_per_request_family():
    ops = _docx_write_ops()
    for family in ("insert", "delete", "subspan", "edit"):
        kinds = ops[family]["anchor_kinds"]
        assert "Anchor" in kinds, f"{family} must document the quote+breadcrumb anchor"
        assert "AnchorById" in kinds, f"{family} must document the by-id anchor"
    assert "TableLocator" in ops["edit"]["anchor_kinds"], (
        "the edit family also takes the table-cell locator")
    assert "TableLocator" not in ops["insert"]["anchor_kinds"]


def test_ac5_the_anchor_kinds_are_projected_off_the_request_annotations():
    """AC5's discipline: ``anchor_kinds`` is a PROJECTION over each request family's own
    anchor-field annotation — widening a union widens the projection automatically, so the
    registry can never advertise an anchor kind the model does not accept."""
    from larkdocio.capabilities import _flatten_anchor_types

    ops = _docx_write_ops()
    for desc in OPS:
        truth = sorted(
            t.__name__ for t in _flatten_anchor_types(_anchor_field_annotation(desc)))
        assert truth, f"op {desc.kind!r} projects no anchor kind at all"
        assert ops[desc.kind]["anchor_kinds"] == truth, desc.kind


def test_ac5_the_anchor_kinds_drift_guard_bites_red_then_green():
    """The same bidirectional check that guards must bite on drift (the test_capabilities
    red-then-green pattern)."""
    from test_capabilities import _phantom_and_missing
    from larkdocio.capabilities import _flatten_anchor_types

    desc = {d.kind: d for d in OPS}["delete"]
    truth = sorted(t.__name__ for t in _flatten_anchor_types(_anchor_field_annotation(desc)))
    documented = _docx_write_ops()["delete"]["anchor_kinds"]

    phantom, missing = _phantom_and_missing(documented, truth)
    assert not phantom and not missing, (documented, truth)
    p1, m1 = _phantom_and_missing(documented + ["AnchorByVibes"], truth)
    assert p1 == ["AnchorByVibes"] and not m1
    p2, m2 = _phantom_and_missing(["Anchor"], truth)
    assert not p2 and m2 == ["AnchorById"]


def test_ac5_every_projected_anchor_kind_resolves_to_a_real_model_symbol():
    import larkdocio.write.model as model

    for op in _docx_write_ops().values():
        for kind in op["anchor_kinds"]:
            assert hasattr(model, kind), f"anchor kind {kind!r} does not resolve"


def test_ac5_capabilities_round_trips_with_the_new_field():
    caps = capabilities(full=True)
    assert json.loads(json.dumps(caps)) == caps


def test_ac5_the_stale_anchor_contract_states_the_by_id_precondition():
    """The safety-contract descriptor must not keep claiming the quote is the only
    precondition — an id anchor has no quote, and a silent gap in a safety descriptor is a
    lie about the engine."""
    summary = capabilities(full=True)["safety_contracts"]["STALE_ANCHOR"]["summary"].lower()
    assert "quote" in summary
    assert "block_id" in summary or "by-id" in summary, summary


# --------------------------------------------------------------------------- #
# AC5 — the guide's matrix + its recipes.                                       #
# --------------------------------------------------------------------------- #

def _guide_anchor_kinds():
    """``{request family: sorted[anchor kind tokens]}`` from the guide's matrix table."""
    from test_guide import _find_table, _first_token, _TOKEN_RE

    out = {}
    for row in _find_table("request family", "anchor kinds"):
        family = _first_token(row["request family"])
        assert family, f"an anchor-kinds row names no request family: {row}"
        out[family] = sorted(_TOKEN_RE.findall(row["anchor kinds"]))
    return out


def test_ac5_the_guide_matrix_documents_the_anchor_kinds_bidirectionally():
    from test_guide import _phantom_and_missing

    ops = _docx_write_ops()
    documented = _guide_anchor_kinds()
    phantom, missing = _phantom_and_missing(documented.keys(), ops.keys())
    assert not phantom, f"the guide names request families code lacks: {phantom}"
    assert not missing, f"code has request families the guide omits: {missing}"
    for family, kinds in documented.items():
        p, m = _phantom_and_missing(kinds, ops[family]["anchor_kinds"])
        assert not p, f"{family}: guide claims anchor kinds code lacks: {p}"
        assert not m, f"{family}: code has anchor kinds the guide omits: {m}"


def test_ac5_the_guide_explains_the_two_anchor_kinds_in_prose():
    from larkdocio import guide

    text = guide(full=True)
    assert "AnchorById" in text
    assert "created_block_ids" in text, (
        "the guide must show the loop apply() → created_block_ids → anchor by id (F19)")


def test_ac5_a_recipe_anchors_by_a_returned_created_block_id():
    import guide_recipes as gr

    src = gr.recipe_source("anchor-a-follow-up-by-a-created-block-id")
    assert "created_block_ids" in src, src
    assert "AnchorById" in src, src
    assert "parse_docx_tree" in src, (
        "the follow-up must resolve against a FRESH tree — a plan always resolves offline")


def test_ac5_the_by_id_recipe_executes_offline(monkeypatch, tmp_path):
    """The load-bearing half of AC5: the recipe is extracted from the shipped guide
    VERBATIM and executed against the offline doubles — a by-id recipe that stops running
    reddens the suite (the LD-133 execution-harness contract)."""
    import guide_recipes as gr

    st = gr.stage(monkeypatch, tmp_path)
    ns = st.run("anchor-a-follow-up-by-a-created-block-id")
    gr._check_anchor_by_id(ns)


# =========================================================================== #
# Zero-drift — the quote-anchored engine is byte-unchanged.                      #
# =========================================================================== #

def test_the_quote_anchored_plan_wire_format_is_byte_unchanged():
    """A representative ENTRY per op, serialized: no new key appears for a quote anchor.

    Scoped to ``["entries"]`` since LD-139: the plan's own wire form additionally carries the
    **whole-document** staleness disclosure (``document_revision_id`` / ``revision_guard`` /
    ``revision_guard_detail``), which is a deliberate, document-level addition required by
    that story's never-silent contract — and is asserted separately in
    ``tests/test_stale_document_guard.py``. The per-entry bytes this test exists to pin are
    unchanged, and the assertion still bites on any entry-level drift."""
    tree = _tree()
    plan = dry_run([
        EditRequest(anchor=Anchor(quote="third line"), replacement="x"),
        InsertRequest(reference=Anchor(quote="third line"),
                      position=InsertPosition.AFTER, content=(NewParagraph("y"),)),
        DeleteRequest(target=Anchor(quote="second line")),
        SubSpanEditRequest(anchor=Anchor(quote="third line"), span="third", replacement="3"),
    ], tree)
    assert {"entries": plan.to_dict()["entries"]} == {"entries": [
        {"outcome": "resolved", "anchor": {"quote": "third line", "breadcrumb": []},
         "replacement": "x", "block_id": "p3", "before": "third line", "after": "x"},
        {"outcome": "resolved", "anchor": {"quote": "third line", "breadcrumb": []},
         "op": "insert", "position": "after", "content": [{"text": "y"}],
         "block_id": "p3", "insertion_point": {"position": "after",
                                               "parent_block_id": "root", "index": 3}},
        {"outcome": "resolved", "anchor": {"quote": "second line", "breadcrumb": []},
         "op": "delete", "block_id": "p2", "before": "second line"},
        {"outcome": "resolved", "anchor": {"quote": "third line", "breadcrumb": []},
         "op": "subspan", "span": "third", "replacement": "3", "block_id": "p3",
         "before": "third", "after": "3"},
    ]}


# =========================================================================== #
# LD-141 — the document ROOT by id. The by-id precondition and the apply-time    #
# live read must share ONE basis per node kind; the page node's own text lives   #
# in `title`, which the old capture (`content` only) could not see — so every    #
# id-anchored write against the root refused a FALSE stale-anchor, forever.      #
# =========================================================================== #

def _live_root(title="Doc"):
    """The **real** live payload shape of a document root (QA's live capture, LD-141):
    block type 1, its own text under the ``page`` container's ``elements`` — which is
    exactly what ``apply._content_container`` finds and reads back."""
    return _block_payload("root", [_run(title)], block_type=1, key="page")


def test_ld141_an_id_anchored_append_into_the_root_applies_on_an_untouched_document():
    """THE BUG, and the coverage hole the filing names: ``test_ac3_the_root_id_with_append_into_resolves``
    asserted only the **resolve** half, so a plan that resolved cleanly and then refused at
    **apply** — on an untouched document, with no write issued — kept the suite green.

    The root node is the only anchor target in an empty document (``GUIDE.md`` § "Recipe:
    write into an empty document"), so this is the one anchor a from-scratch authoring pass
    reaches for by id."""
    plan = dry_run(
        [_insert_by_id("root", InsertPosition.APPEND_INTO, ["brand new line"])], _tree())
    opener = StubOpener([_live_root(), _create_ok(["newA"])])
    log = apply(plan, _client(opener), "root")
    (entry,) = log.entries
    assert entry.outcome == "inserted", (
        f"an id-anchored APPEND_INTO against the UNTOUCHED document root was refused: "
        f"{entry.to_dict()}")
    assert entry.created_block_ids == ("newA",)
    assert _methods(opener) == ["GET", "POST"]


def test_ld141_the_root_id_precondition_is_the_TITLE_the_live_read_returns():
    """The basis rule, asserted directly: for the page node the precondition is its
    ``title`` — the one thing ``apply._elements_plain_text`` can return for a root block.
    Capturing ``''`` (the ``content``-only basis) is what made ``'' != '<title>'``
    unconditional."""
    plan = dry_run(
        [_insert_by_id("root", InsertPosition.APPEND_INTO, ["brand new line"])], _tree())
    (entry,) = plan.entries
    assert entry.is_resolved
    assert entry.precondition_text == "Doc", (
        "the page node's own text lives in `title`; a precondition captured off `content` "
        "alone can never match the live read")
    assert entry.to_dict()["precondition_text"] == "Doc"


def test_ld141_the_root_id_and_the_title_quote_reach_the_same_outcome():
    """The parity promise ``GUIDE.md`` makes ("``AnchorById`` … is **interchangeable** with
    it"): the same insert, the same tree, the same live payload — the quote-anchored control
    the filing used must not be the only one that works."""
    requests = {
        "by-id": _insert_by_id("root", InsertPosition.APPEND_INTO, ["brand new line"]),
        "quote": InsertRequest(reference=Anchor(quote="Doc"),
                               position=InsertPosition.APPEND_INTO,
                               content=(NewParagraph("brand new line"),)),
    }
    outcomes, methods = {}, {}
    for kind, request in requests.items():
        opener = StubOpener([_live_root(), _create_ok(["newA"])])
        log = apply(dry_run([request], _tree()), _client(opener), "root")
        outcomes[kind] = [e.outcome for e in log.entries]
        methods[kind] = _methods(opener)
    assert outcomes["by-id"] == outcomes["quote"] == ["inserted"], outcomes
    assert methods["by-id"] == methods["quote"] == ["GET", "POST"], methods


def test_ld141_a_root_whose_title_really_changed_still_refuses_stale_anchor():
    """The guard is moved, not defanged: the compare-and-swap on the root stays meaningful,
    so a title that genuinely drifted under the plan still refuses with **no write**."""
    plan = dry_run([_insert_by_id("root", InsertPosition.APPEND_INTO, ["x"])], _tree())
    opener = StubOpener([_live_root("Renamed by somebody else"), _create_ok(["newA"])])
    log = apply(plan, _client(opener), "root")
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR
    assert "Doc" in entry.refusal.detail
    assert "Renamed by somebody else" in entry.refusal.detail
    assert not _by_method(opener, "POST"), "a stale root insert must create nothing"


def test_ld141_the_precondition_basis_mirrors_the_live_read_for_a_REAL_page_payload():
    """The root-cause invariant itself, pinned against a **real payload shape** (PROJECT.md
    § "API-drift is an expected hazard"): whatever the plan captures for the page node must
    be byte-equal to what the apply engine reads back off the same live block — including
    the **mention-immunity** the live basis exists for (a mention is not a ``text_run``, so
    neither side counts its title)."""
    from harness import build_blocks
    from larkdocio.read.config import Config
    from larkdocio.read.parser import Parser
    from larkdocio.write.apply import _elements_plain_text, _live_elements

    page_elements = [
        {"text_run": {"content": "Quarterly review "}},
        {"mention_doc": {"token": "tok", "obj_type": 22, "url": "https://x/y",
                         "title": "Spec"}},
        {"text_run": {"content": " v2"}},
    ]
    blocks = [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": page_elements}, "children": ["t1"]},
        {"block_id": "t1", "parent_id": "root", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "body"}}]}, "children": []},
    ]
    root = Parser(Config()).parse_docx_tree("root", build_blocks(blocks))
    live_block = {"block_id": "root", "block_type": 1, "page": {"elements": page_elements}}

    (entry,) = dry_run(
        [_insert_by_id("root", InsertPosition.APPEND_INTO, ["x"])], root).entries
    assert entry.precondition_text == _elements_plain_text(_live_elements(live_block)), (
        "the offline capture and the live read must agree for the page node — that "
        "disagreement IS LD-141")
    assert entry.precondition_text == "Quarterly review  v2", entry.precondition_text


def test_ld141_the_subspan_offset_basis_is_deliberately_untouched():
    """Scope discipline. The fix moves the by-id **precondition** basis only; the sub-span
    **splitting** basis (``_text_run_plain_text``, whose character offsets must line up with
    the live run split) still reads ``content`` alone. So a sub-span edit of the document
    TITLE keeps refusing on **both** anchor kinds exactly as it does today — newly allowing
    one would be an untested write against ``page.elements``, outside LD-141."""
    from larkdocio.write.resolve import _live_basis_plain_text, _text_run_plain_text

    page = _page()
    assert _text_run_plain_text(page) == "", "the sub-span basis must not gain a title arm"
    assert _live_basis_plain_text(page) == "Doc", "the live-read mirror must have one"
    for anchor in (AnchorById("root"), Anchor(quote="Doc")):
        result = resolve(
            SubSpanEditRequest(anchor=anchor, span="Do", replacement="X"), _tree())
        assert result.reason is RefusalReason.NOT_FOUND, anchor


def test_ld141_before_after_against_the_root_id_still_refuses_cannot_hold_siblings():
    """LD-131 unchanged at the very layer this fix edits: the refusal comes from ``resolve``,
    so a root-id BEFORE/AFTER never reaches the precondition capture at all and carries no
    ``precondition_text`` in the wire form."""
    for position in (InsertPosition.BEFORE, InsertPosition.AFTER):
        (entry,) = dry_run([_insert_by_id("root", position, ["x"])], _tree()).entries
        assert not entry.is_resolved
        assert entry.refusal.reason is RefusalReason.CANNOT_HOLD_SIBLINGS, position
        assert entry.precondition_text is None
        assert "precondition_text" not in entry.to_dict()


@pytest.mark.parametrize("block_id,position,expected", [
    pytest.param("p3", InsertPosition.AFTER, "third line", id="leaf-paragraph"),
    pytest.param("h1", InsertPosition.APPEND_INTO, "Overview", id="heading-container"),
    pytest.param("h1", InsertPosition.AFTER, "Overview", id="heading-sibling"),
])
def test_ld141_non_root_by_id_preconditions_are_byte_unchanged(block_id, position, expected):
    """The LD-137 matrix must not shift. Only the **page** node's basis moves — it is the
    only node kind whose own text lives in ``title`` — so every other by-id precondition is
    the value LD-137 shipped."""
    (entry,) = dry_run([_insert_by_id(block_id, position, ["x"])], _tree()).entries
    assert entry.is_resolved, entry.to_dict()
    assert entry.precondition_text == expected


def test_ld141_the_by_id_plan_wire_shape_is_unchanged_for_a_non_root_entry():
    """Zero-drift on the shipped by-id wire form: the fix adds and removes no key, and
    changes no value, for any entry that is not the page node."""
    plan = dry_run([_insert_by_id("p3", InsertPosition.AFTER, ["y"])], _tree())
    assert plan.to_dict()["entries"] == [{
        "outcome": "resolved",
        "anchor": {"kind": "by-id", "block_id": "p3"},
        "op": "insert",
        "position": "after",
        "content": [{"text": "y"}],
        "block_id": "p3",
        "insertion_point": {"position": "after", "parent_block_id": "root", "index": 3},
        "precondition_text": "third line",
    }]


def test_block_plain_text_is_unchanged_by_the_own_text_refactor():
    """``block_plain_text`` is the reader-facing quote basis; the by-id target check shares
    its source lookup, so this pins that the shared refactor changed nothing."""
    from larkdocio.write.resolve import block_plain_text

    assert block_plain_text(_para("x", "hello")) == "hello"
    assert block_plain_text(TextNode(content=[Text("a"), Text("b")], block_id="y")) == "ab"
    assert block_plain_text(ImageNode(caption="cap", block_id="i")) == "cap"
    assert block_plain_text(_page()) == "Doc"
    assert block_plain_text(_cell("c", "inner")) == ""
