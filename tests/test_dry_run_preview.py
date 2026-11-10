"""Offline unit tests for the mandatory dry-run previewer (LD-067).

W1-S3 turns a batch of :class:`~larkdocio.write.model.EditRequest`s + a parsed node
tree into a **plan**: each edit is run through the S2 resolver (LD-066) with **zero
writes**; a resolved edit yields its target ``block_id`` + before/after text, a refused
edit yields its typed :class:`~larkdocio.write.model.Refusal`. The plan is the **only**
input the S4 apply engine (LD-068) will accept — no path applies an unresolved edit
(§ Decision (c), the hard gate; co-verified at S4). Fully offline; goldens ZERO-DRIFT.
"""
import json
import typing

import pytest

from larkdocio.model import (
    CalloutNode,
    HeadingNode,
    ImageNode,
    PageNode,
    SourceSyncedNode,
    Text,
    TextNode,
)
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write.apply import apply
from larkdocio.write.client import WriteClient
from larkdocio.write.model import (
    Anchor,
    DeleteRequest,
    EditRequest,
    InsertPosition,
    InsertRequest,
    NewParagraph,
    RefusalReason,
)
from larkdocio.write.preview import Plan, PlanEntry, dry_run
from larkdocio.write.resolve import ResolvedInsertion

from harness import build_blocks


# --------------------------------------------------------------------------- #
# tiny helpers to build offline node trees + requests (mirrors S2 tests)        #
# --------------------------------------------------------------------------- #

def _para(bid, text):
    return TextNode(content=[Text(text)], block_id=bid)


def _heading(bid, text, level=1):
    return HeadingNode(level=level, content=[Text(text)], block_id=bid)


def _page(*children):
    return PageNode(title=[Text("Doc")], children=list(children), block_id="root")


def _req(quote, replacement="REPLACED", breadcrumb=()):
    return EditRequest(anchor=Anchor(quote=quote, breadcrumb=breadcrumb), replacement=replacement)


# --------------------------------------------------------------------------- #
# AC1 — the plan object: resolved → block_id + before + after; refused → reason #
# --------------------------------------------------------------------------- #

def test_dry_run_returns_a_plan():
    tree = _page(_para("p1", "The sky is blue."))
    plan = dry_run([_req("The sky is blue.")], tree)
    assert isinstance(plan, Plan)


def test_resolved_edit_carries_block_id_before_and_after():
    tree = _page(_para("p1", "Revenue grew 12.4% in Q3."))
    plan = dry_run([_req("Revenue grew 12.4% in Q3.", replacement="Revenue grew 15.0% in Q3.")], tree)
    (entry,) = plan.entries
    assert entry.is_resolved
    assert entry.block_id == "p1"
    assert entry.before == "Revenue grew 12.4% in Q3."   # the resolved block's current plain text
    assert entry.after == "Revenue grew 15.0% in Q3."    # the replacement
    assert entry.refusal is None


def test_refused_edit_carries_the_typed_refusal_reason():
    tree = _page(_para("p1", "hello"))
    plan = dry_run([_req("absent quote")], tree)
    (entry,) = plan.entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.NOT_FOUND
    assert entry.block_id is None and entry.before is None and entry.after is None


def test_plan_enumerates_both_resolved_and_refused_on_a_mixed_batch():
    # Some resolve, some refuse — the plan enumerates BOTH sets (AC1).
    tree = _page(
        _heading("hA", "Alpha"),
        _para("pA", "shared sentence"),
        _heading("hB", "Beta"),
        _para("pB", "shared sentence"),
        _para("uniq", "the unique line"),
    )
    requests = [
        _req("the unique line", replacement="the new line"),   # resolves → uniq
        _req("shared sentence"),                                # ambiguous → refuse
        _req("nowhere at all"),                                 # not-found → refuse
        _req("shared sentence", breadcrumb=("Beta",)),          # breadcrumb narrows → pB
    ]
    plan = dry_run(requests, tree)

    assert len(plan.entries) == 4
    # order is preserved 1:1 with the input batch
    resolved = plan.resolved
    refusals = plan.refusals
    assert {e.block_id for e in resolved} == {"uniq", "pB"}
    assert len(refusals) == 2
    reasons = {e.refusal.reason for e in refusals}
    assert reasons == {RefusalReason.AMBIGUOUS, RefusalReason.NOT_FOUND}
    # the ambiguous refusal carries the candidate ids (never auto-picked)
    ambiguous = next(e for e in refusals if e.refusal.reason is RefusalReason.AMBIGUOUS)
    assert set(ambiguous.refusal.candidate_ids) == {"pA", "pB"}


def test_write_hostile_target_is_a_refusal_in_the_plan():
    tree = _page(ImageNode(caption="quarterly revenue chart", block_id="img"))
    plan = dry_run([_req("quarterly revenue chart")], tree)
    (entry,) = plan.entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.WRITE_HOSTILE


def test_plan_order_matches_the_input_batch_order():
    tree = _page(_para("a", "first"), _para("b", "second"))
    plan = dry_run([_req("second"), _req("first"), _req("gone")], tree)
    outcomes = [(e.is_resolved, e.block_id) for e in plan.entries]
    assert outcomes == [(True, "b"), (True, "a"), (False, None)]


# --------------------------------------------------------------------------- #
# AC2 — zero writes: the previewer calls NO WriteClient mutating method         #
# --------------------------------------------------------------------------- #

class _SpyTransport:
    """A stand-in write transport that records — and forbids — every execution."""

    def __init__(self):
        self.executed = []

    def execute(self, fn):
        self.executed.append(fn)
        raise AssertionError("dry-run must perform ZERO writes — transport was executed")


def test_dry_run_performs_zero_writes_with_an_injected_spy_transport():
    # A WriteClient wired to a spy transport that fails loudly if ANY write is paced
    # through it. The previewer never touches a client, so nothing is executed.
    spy = _SpyTransport()
    _client = WriteClient("app", "secret", transport=spy, token_fetcher=lambda *a, **k: "tok")
    tree = _page(_para("p1", "resolve me"), ImageNode(caption="hostile", block_id="img"))

    plan = dry_run([_req("resolve me"), _req("hostile")], tree)

    assert isinstance(plan, Plan)
    assert spy.executed == []   # not one write was paced through the transport


def test_dry_run_takes_no_write_client_by_signature():
    # Structural proof it CANNOT write: dry_run's signature exposes no client/transport.
    import inspect

    params = set(inspect.signature(dry_run).parameters)
    assert not (params & {"client", "write_client", "transport"})


# --------------------------------------------------------------------------- #
# AC3 — the plan is the ONLY apply input (hard gate): non-trivially forgeable    #
# --------------------------------------------------------------------------- #

def test_a_plan_cannot_be_hand_constructed_directly():
    # The S4 apply engine will accept ONLY a Plan; a Plan must come from the resolver-
    # backed dry_run, not be hand-forged from arbitrary records.
    with pytest.raises(TypeError):
        Plan([])
    with pytest.raises(TypeError):
        Plan(entries=())


def test_dry_run_is_the_producer_of_a_plan():
    plan = dry_run([_req("x")], _page(_para("p1", "x")))
    assert isinstance(plan, Plan)


def test_a_plan_holds_no_unresolved_edits():
    # Every entry is decided — resolved (has a block_id) or refused (has a Refusal);
    # a raw/unresolved EditRequest can never sit in a plan (so cannot reach apply).
    tree = _page(_para("p1", "here"))
    plan = dry_run([_req("here"), _req("gone")], tree)
    for entry in plan.entries:
        if entry.is_resolved:
            assert entry.block_id is not None and entry.refusal is None
        else:
            assert entry.refusal is not None and entry.block_id is None


# --------------------------------------------------------------------------- #
# AC4 — inspectable / serializable (render before/after + refusals downstream)   #
# --------------------------------------------------------------------------- #

def test_plan_is_inspectable_read_before_after_and_refusals_off_it():
    tree = _page(_para("p1", "old text"), _para("dup1", "twin"), _para("dup2", "twin"))
    plan = dry_run(
        [_req("old text", replacement="new text"), _req("twin")], tree
    )
    resolved = plan.resolved[0]
    assert (resolved.block_id, resolved.before, resolved.after) == ("p1", "old text", "new text")
    refused = plan.refusals[0]
    assert refused.refusal.reason is RefusalReason.AMBIGUOUS


def test_plan_serializes_to_a_dict_with_both_arms():
    tree = _page(_para("p1", "old text"), _para("dup1", "twin"), _para("dup2", "twin"))
    plan = dry_run([_req("old text", replacement="new text"), _req("twin")], tree)
    d = plan.to_dict()
    assert [e["outcome"] for e in d["entries"]] == ["resolved", "refused"]
    resolved, refused = d["entries"]
    assert resolved["block_id"] == "p1"
    assert resolved["before"] == "old text"
    assert resolved["after"] == "new text"
    assert refused["refusal"]["reason"] == RefusalReason.AMBIGUOUS.value
    assert set(refused["refusal"]["candidate_ids"]) == {"dup1", "dup2"}


def test_plan_serializes_to_json_round_trippable_at_the_dict_level():
    tree = _page(_para("p1", "old text"))
    plan = dry_run([_req("old text", replacement="new text")], tree)
    s = plan.to_json(sort_keys=True)
    assert json.loads(s) == plan.to_dict()


def test_plan_entry_reuses_the_s1_record_shapes():
    # AC4 "reuse S1's record shapes where sensible": a PlanEntry carries the anchor,
    # block_id, before, after, refusal fields the apply-log record uses.
    tree = _page(_para("p1", "old text"))
    plan = dry_run([_req("old text", breadcrumb=("Doc",), replacement="new")], tree)
    entry = plan.entries[0]
    d = entry.to_dict()
    assert d["anchor"] == {"quote": "old text", "breadcrumb": ["Doc"]}
    assert PlanEntry.from_dict(d) == entry


# --------------------------------------------------------------------------- #
# AC5 — offline; works on the real parsed tree; reader output byte-identical     #
# --------------------------------------------------------------------------- #

def test_dry_run_over_a_parser_built_tree_from_real_sdk_blocks():
    # End-to-end on real SDK Block objects: parse → tree → dry_run → plan.
    block_dicts = [
        {"block_id": "root", "parent_id": "", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc"}}]},
         "children": ["h", "p"]},
        {"block_id": "h", "parent_id": "root", "block_type": 3,
         "heading1": {"elements": [{"text_run": {"content": "Findings"}}]}},
        {"block_id": "p", "parent_id": "root", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "The uptime was 99.9 percent."}}]}},
    ]
    parser = Parser(Config())
    tree = parser.parse_docx_tree("root", build_blocks(block_dicts))
    plan = dry_run(
        [_req("uptime was 99.9 percent", replacement="uptime was 99.99 percent", breadcrumb=("Findings",))],
        tree,
    )
    (entry,) = plan.entries
    assert entry.is_resolved
    assert entry.block_id == "p"
    assert entry.before == "The uptime was 99.9 percent."
    assert entry.after == "uptime was 99.99 percent"


# =========================================================================== #
# LD-075 — insert/delete preview (W3-S2)                                       #
#                                                                             #
# The dry-run plan extends to the two block-level operations. An InsertRequest #
# previews WHAT would be created (the NewParagraph content) and WHERE (the      #
# resolved reference block_id + the position + the computed insertion point —  #
# parent block_id + index). A DeleteRequest previews the text that WOULD be     #
# removed (the resolved target block_id + its current plain text). Both flow    #
# through the SAME non-forgeable Plan; the apply engine still accepts only a    #
# Plan, so an insert/delete can never reach apply except via dry_run. Offline.  #
# =========================================================================== #


def _insert(quote, position, texts=("new para",), breadcrumb=()):
    return InsertRequest(
        reference=Anchor(quote=quote, breadcrumb=breadcrumb),
        position=position,
        content=[NewParagraph(text=t) for t in texts],
    )


def _delete(quote, breadcrumb=()):
    return DeleteRequest(target=Anchor(quote=quote, breadcrumb=breadcrumb))


# --------------------------------------------------------------------------- #
# AC3 — insertion preview: content-that-would-be-created + where                #
# --------------------------------------------------------------------------- #

def test_insert_plan_previews_content_and_location():
    tree = _page(_para("p0", "intro"), _para("p1", "the anchor line"), _para("p2", "tail"))
    plan = dry_run([_insert("the anchor line", InsertPosition.AFTER, texts=("added one", "added two"))], tree)
    (entry,) = plan.entries
    assert entry.is_resolved and entry.is_insert
    # WHAT would be created — the text-bearing paragraph content, in order
    assert [p.text for p in entry.content] == ["added one", "added two"]
    # WHERE — the resolved reference id + position + computed insertion point
    assert entry.block_id == "p1"                 # the resolved reference
    assert entry.position == "after"
    assert isinstance(entry.insertion_point, ResolvedInsertion)
    assert entry.insertion_point.parent_block_id == "root"
    assert entry.insertion_point.index == 2       # p1 index 1 → after = 2


def test_insert_append_into_plan_previews_last_child_point():
    callout = CalloutNode(children=[_para("c0", "existing child")], block_id="cal")
    tree = _page(_heading("h", "Section"), callout)
    plan = dry_run([_insert("Section", InsertPosition.APPEND_INTO, texts=("child para",))], tree)
    (entry,) = plan.entries
    assert entry.is_resolved and entry.is_insert
    assert entry.position == "append-into"
    assert entry.insertion_point.parent_block_id == "h"   # append INTO the heading
    assert entry.insertion_point.index == 0                # heading owns no flat children


def test_insert_refused_plan_still_carries_the_intended_content_and_position():
    # A refused insert (write-hostile reference) still previews WHAT was intended,
    # so a consumer's approval UX can show the rejected op — mirrors edit refusals.
    tree = _page(SourceSyncedNode(content=[Text("synced line")], block_id="sync"))
    plan = dry_run([_insert("synced line", InsertPosition.AFTER, texts=("wont happen",))], tree)
    (entry,) = plan.entries
    assert not entry.is_resolved and entry.is_insert
    assert entry.refusal.reason is RefusalReason.WRITE_HOSTILE
    assert [p.text for p in entry.content] == ["wont happen"]
    assert entry.position == "after"
    assert entry.insertion_point is None                   # no location for a refusal


def test_insert_append_into_leaf_is_a_refusal_in_the_plan():
    tree = _page(_para("p", "a leaf paragraph"))
    plan = dry_run([_insert("a leaf paragraph", InsertPosition.APPEND_INTO)], tree)
    (entry,) = plan.entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.CANNOT_HOLD_CHILDREN


# --------------------------------------------------------------------------- #
# AC4 — deletion preview: the text that WOULD be removed                        #
# --------------------------------------------------------------------------- #

def test_delete_plan_previews_removed_block_id_and_text():
    tree = _page(_para("p1", "keep this"), _para("p2", "Obsolete paragraph to remove."))
    plan = dry_run([_delete("Obsolete paragraph to remove.")], tree)
    (entry,) = plan.entries
    assert entry.is_resolved and entry.is_delete
    assert entry.block_id == "p2"                          # the resolved target
    assert entry.before == "Obsolete paragraph to remove."  # the full text that would be removed


def test_delete_refused_plan_carries_the_target_and_reason():
    tree = _page(_para("p1", "dup"), _para("p2", "dup"))
    plan = dry_run([_delete("dup")], tree)
    (entry,) = plan.entries
    assert not entry.is_resolved and entry.is_delete
    assert entry.refusal.reason is RefusalReason.AMBIGUOUS
    assert entry.anchor.quote == "dup"
    assert entry.block_id is None and entry.before is None


# --------------------------------------------------------------------------- #
# AC5 — plan-gated (non-forgeable): insert/delete flow through the same Plan     #
#       and cannot reach apply except via a dry-run-produced plan                #
# --------------------------------------------------------------------------- #

def test_insert_delete_entries_flow_through_the_non_forgeable_plan():
    tree = _page(_para("p1", "anchor"), _para("p2", "remove me"))
    plan = dry_run(
        [_insert("anchor", InsertPosition.AFTER), _delete("remove me")], tree
    )
    assert isinstance(plan, Plan)
    assert [e.op for e in plan.entries] == ["insert", "delete"]
    # the Plan is still non-forgeable — no op reopens the hand-construction vector
    with pytest.raises(TypeError):
        Plan([])


def test_insert_delete_cannot_reach_apply_except_via_a_plan():
    # A raw bag of insert/delete requests can never be applied — apply accepts ONLY
    # a Plan produced by dry_run (the hard gate is op-agnostic).
    with pytest.raises(TypeError):
        apply([_insert("x", InsertPosition.AFTER)], client=None, document_id="d")
    with pytest.raises(TypeError):
        apply([_delete("x")], client=None, document_id="d")


def test_dry_run_is_the_only_producer_of_an_insert_delete_plan():
    tree = _page(_para("p1", "anchor"))
    plan = dry_run([_insert("anchor", InsertPosition.BEFORE)], tree)
    assert isinstance(plan, Plan)
    # every entry is decided — resolved (has a location) or refused (has a reason)
    for entry in plan.entries:
        if entry.is_resolved:
            assert entry.insertion_point is not None and entry.refusal is None
        else:
            assert entry.refusal is not None


# --------------------------------------------------------------------------- #
# Serialization — insert/delete plan entries round-trip; edit stays byte-compat #
# --------------------------------------------------------------------------- #

def test_insert_plan_entry_round_trips_through_dict():
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert("anchor line", InsertPosition.AFTER, texts=("one", "two"))], tree)
    entry = plan.entries[0]
    d = entry.to_dict()
    assert d["op"] == "insert"
    assert d["position"] == "after"
    assert [c["text"] for c in d["content"]] == ["one", "two"]
    assert PlanEntry.from_dict(d) == entry


def test_delete_plan_entry_round_trips_through_dict():
    tree = _page(_para("p1", "remove me"))
    plan = dry_run([_delete("remove me")], tree)
    entry = plan.entries[0]
    d = entry.to_dict()
    assert d["op"] == "delete"
    assert d["block_id"] == "p1"
    assert d["before"] == "remove me"
    assert PlanEntry.from_dict(d) == entry


def test_edit_plan_entry_serialization_stays_byte_compatible():
    # An edit entry carries NO `op` tag — its W1/W2 serialization is unchanged, so
    # existing edit plans read back exactly (the tagless-EditRequest discipline).
    tree = _page(_para("p1", "old text"))
    plan = dry_run([_req("old text", replacement="new text")], tree)
    d = plan.entries[0].to_dict()
    assert "op" not in d
    assert d["outcome"] == "resolved"
    assert d["replacement"] == "new text"


def test_ld142_the_plan_entry_anchor_annotation_accepts_every_shape_it_really_carries():
    """LD-142 rider — **the public annotations on the write surface are code truth.**

    ``capabilities()`` projects the advertised anchor kinds off ``typing.get_type_hints``, so
    an annotation here is not a comment: a narrower-than-reality hint is a lie a machine can
    read. :class:`PlanEntry` was annotated ``anchor: Anchor`` while it demonstrably carries a
    :class:`TableLocator` (every W2 table-cell entry) and an :class:`AnchorById` (every LD-137
    id-anchored entry). Pinned against its declared sibling record —
    :class:`~larkdocio.write.model.ApplyLogEntry`, the plan entry's apply-time mirror — and
    against the union over all four request families, so widening the model widens this.
    """
    from larkdocio.capabilities import _flatten_anchor_types
    from larkdocio.write.model import ApplyLogEntry
    from larkdocio.write.ops import OPS

    def kinds(annotation):
        return {t.__name__ for t in _flatten_anchor_types(annotation)}

    plan_entry = kinds(typing.get_type_hints(PlanEntry)["anchor"])
    apply_log_entry = kinds(typing.get_type_hints(ApplyLogEntry)["anchor"])
    every_family = set().union(*(
        kinds(typing.get_type_hints(d.request_type)[d.anchor_field]) for d in OPS))

    assert plan_entry == apply_log_entry, (
        "the plan entry and the apply-log entry carry the SAME anchor off the same request; "
        f"plan says {sorted(plan_entry)}, apply-log says {sorted(apply_log_entry)}")
    assert plan_entry == every_family, (
        f"a PlanEntry carries whatever anchor its request family accepted "
        f"{sorted(every_family)}, but its annotation admits only {sorted(plan_entry)}")


def test_ld142_the_plan_entry_content_annotation_matches_what_an_insert_can_create():
    """Same rider, the content half: ``content`` previews what an ``InsertRequest`` would
    create, so its element type must be the request's own ``NewContent`` union — not the
    legacy ``NewParagraph`` alone (LD-134 widened the model and left this hint behind)."""
    from larkdocio.capabilities import _flatten_content_types

    previewed = {t.__name__ for t in _flatten_content_types(
        typing.get_type_hints(PlanEntry)["content"])}
    creatable = {t.__name__ for t in _flatten_content_types(
        typing.get_type_hints(InsertRequest)["content"])}
    assert previewed == creatable, (
        f"the plan previews {sorted(previewed)} but an insert can create {sorted(creatable)}")


@pytest.mark.parametrize(
    "factory,param",
    [
        ("resolved", "anchor"), ("refused", "anchor"),
        ("insert_resolved", "reference"), ("insert_refused", "reference"),
        ("delete_resolved", "target"), ("delete_refused", "target"),
        ("subspan_resolved", "anchor"), ("subspan_refused", "anchor"),
        # LD-202's two families. Their anchors differ from each other AND from every family
        # above, which is exactly the kind of divergence a hand-written annotation gets wrong:
        # a create points at the whole document, a removal at one thread.
        ("comment_create_resolved", "anchor"), ("comment_create_refused", "anchor"),
        ("comment_remove_resolved", "anchor"), ("comment_remove_refused", "anchor"),
    ],
)
def test_ld142_every_plan_entry_factory_declares_its_request_familys_anchor(factory, param):
    """Each op-specific factory takes exactly the anchor family its **request** accepts —
    read off the op registry, never hand-listed. The edit factories additionally admit a
    ``TableLocator``; insert / delete / sub-span do not (they are narrative-only), and
    annotating them all as a bare ``Anchor`` hid both facts."""
    from larkdocio.capabilities import _flatten_anchor_types
    from larkdocio.write.ops import OPS

    kind = {"resolved": "edit", "refused": "edit",
            "insert_resolved": "insert", "insert_refused": "insert",
            "delete_resolved": "delete", "delete_refused": "delete",
            "subspan_resolved": "subspan", "subspan_refused": "subspan",
            "comment_create_resolved": "comment-create",
            "comment_create_refused": "comment-create",
            "comment_remove_resolved": "comment-remove",
            "comment_remove_refused": "comment-remove"}[factory]
    desc = {d.kind: d for d in OPS}[kind]

    declared = {t.__name__ for t in _flatten_anchor_types(
        typing.get_type_hints(getattr(PlanEntry, factory))[param])}
    accepted = {t.__name__ for t in _flatten_anchor_types(
        typing.get_type_hints(desc.request_type)[desc.anchor_field])}
    assert declared == accepted, (
        f"PlanEntry.{factory}({param}=...) declares {sorted(declared)} but a {kind} request "
        f"accepts {sorted(accepted)}")


def test_mixed_edit_insert_delete_batch_preserves_order_and_ops():
    tree = _page(
        _para("e", "edit me"),
        _para("r", "reference"),
        _para("d", "delete me"),
    )
    plan = dry_run(
        [
            _req("edit me", replacement="edited"),
            _insert("reference", InsertPosition.AFTER, texts=("inserted",)),
            _delete("delete me"),
        ],
        tree,
    )
    assert [e.op for e in plan.entries] == ["edit", "insert", "delete"]
    assert [e.is_resolved for e in plan.entries] == [True, True, True]
    assert plan.entries[0].after == "edited"
    assert [p.text for p in plan.entries[1].content] == ["inserted"]
    assert plan.entries[2].before == "delete me"
