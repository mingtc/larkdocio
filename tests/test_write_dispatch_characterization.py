"""Characterization safety net for the write-side per-op dispatch chains (LD-097).

LD-097 unifies the **four parallel per-op dispatch chains** the writer grew arm-by-arm —
``resolve()`` (request-kind → resolver), ``dry_run()`` (request-kind → previewer),
``PlanEntry.to_dict``/``from_dict`` (op-string → serialize fields), and ``apply()``
(entry → apply-fn) — behind **one** op-descriptor registry. That is a HIGH-risk,
strictly **behavior-preserving** refactor: the chains ARE the core write contract, and a
mis-dispatch (routing one op through another op's arm) would corrupt a document silently.

This module is the **safety net that lands BEFORE any move** (safety-net-check). It pins,
for **every** op (narrative-edit / table-cell-edit / insert / delete / sub-span), the full
``resolve → dry_run → apply`` round-trip **plus** the JSON wire format:

* the **resolve** result (``ResolvedTarget`` block-id + cell/insertion context, or the typed
  ``Refusal``) — proving the request routed to the correct resolver arm;
* the **plan entry** (``op`` discriminator + payload fields) — proving ``dry_run`` built the
  right entry shape;
* the **JSON serialization** (``PlanEntry.to_dict`` byte-for-byte + a ``from_dict``
  round-trip) — the non-forgeable wire contract a consumer's approval UX reads;
* the **apply-log** + the HTTP method/URL the write actually issued — proving ``apply``
  dispatched to the correct write path (a PATCH vs a POST-children vs a DELETE is how a
  cross-wired op would show itself).

These tests characterize **current** behavior (they pass on the pre-refactor code). If any
one reddens after the refactor, dispatch drifted — which is exactly the failure this net
exists to catch. They are intentionally op-distinct so mis-routing op A through op B's arm
breaks an assertion.
"""
import json

import pytest

from larkdocio.errors import LarkDocIOError
from larkdocio.write.model import (
    Anchor,
    InsertPosition,
    Refusal,
    RefusalReason,
    SubSpanEditRequest,
)
from larkdocio.write.preview import PlanEntry, dry_run
from larkdocio.write.resolve import (
    NOT_FOUND_REMEDY,
    ResolvedCell,
    ResolvedInsertion,
    ResolvedTarget,
    resolve,
)
from larkdocio.write.apply import apply

from write_harness import (
    StubOpener,
    _block_payload,
    _by_method,
    _client,
    _delete,
    _insert,
    _methods,
    _page,
    _para,
    _parent_payload,
    _patch_ok,
    _req,
    _run,
    _table,
    _treq,
)


# --------------------------------------------------------------------------- #
# file-local apply-response payloads (mirrors test_insert_delete_apply)          #
# --------------------------------------------------------------------------- #

def _create_ok(created_ids):
    return {"code": 0, "data": {
        "children": [{"block_id": bid} for bid in created_ids],
        "document_revision_id": 200,
    }}


def _delete_ok():
    return {"code": 0, "data": {"document_revision_id": 201}}


def _subspan(quote, span, replacement, *, breadcrumb=()):
    return SubSpanEditRequest(
        anchor=Anchor(quote=quote, breadcrumb=breadcrumb), span=span, replacement=replacement
    )


# --------------------------------------------------------------------------- #
# LD-131 — every docx refusal now carries a MANDATORY, actionable `detail`.      #
# These characterization pins previously asserted the detail-LESS wire record    #
# `{"reason": "not-found"}`; the dogfood report § F5 named that the bug ("with    #
# no `detail` field at all … gives an agent NOTHING to recover from"), so the     #
# pins are updated to the new text WITH the identifier they name. The two         #
# builders below keep the expected strings in one place — a wording change still  #
# has to be a deliberate edit here (the pin's whole point).                       #
# --------------------------------------------------------------------------- #

def _quote_not_found_detail(quote):
    """The narrative "no block matched this quote" detail (resolve._resolve_narrative)."""
    return (
        f"no block's own text contains the anchor quote {quote!r} — the quote is "
        f"matched verbatim (substring) against each block's OWN text, never its "
        # LD-455 amended the REMEDY only; the diagnosis above it is byte-unchanged. The
        # struck sentence ("re-read the document and copy the quote verbatim") named the
        # action the consumer had just taken, measured failing 5/5 in dogfood round 4.
        f"children's; {NOT_FOUND_REMEDY}"
    )


def _span_absent_detail(span, block_id, quote):
    """The sub-span "that span is not in this block" detail (resolve._resolve_subspan)."""
    return (
        f"the span {span!r} does not occur in the text runs of block {block_id} "
        f"(resolved from quote {quote!r}) — a sub-span edit's span must be verbatim "
        f"text of that block"
    )


def _roundtrip(entry: PlanEntry) -> None:
    """A PlanEntry survives to_dict → from_dict byte-identically (the wire contract)."""
    assert PlanEntry.from_dict(entry.to_dict()) == entry
    # and to_json parses back to the same structure
    assert json.loads(json.dumps(entry.to_dict())) == entry.to_dict()


# =========================================================================== #
# NARRATIVE EDIT — quote anchor → whole-paragraph replace (op="edit", tagless)  #
# =========================================================================== #

def test_narrative_edit_resolve_preview_serialize():
    tree = _page(_para("p1", "hello world"))
    req = _req("hello world", "REPLACED")

    result = resolve(req, tree)
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "p1"
    assert result.cell is None and result.insertion is None

    entry = dry_run([req], tree).entries[0]
    assert (entry.op, entry.outcome) == ("edit", "resolved")
    assert (entry.block_id, entry.before, entry.after) == ("p1", "hello world", "REPLACED")
    assert entry.cell is None

    # tagless edit serialization — NO "op" key (W1/W2 byte-compatible form)
    assert entry.to_dict() == {
        "outcome": "resolved",
        "anchor": req.anchor.to_dict(),
        "replacement": "REPLACED",
        "block_id": "p1",
        "before": "hello world",
        "after": "REPLACED",
    }
    _roundtrip(entry)


def test_narrative_edit_refused_serialize():
    tree = _page(_para("p1", "hello world"))
    req = _req("nothing matches this", "REPLACED")

    result = resolve(req, tree)
    assert result == Refusal.not_found(detail=_quote_not_found_detail("nothing matches this"))

    entry = dry_run([req], tree).entries[0]
    assert (entry.op, entry.outcome) == ("edit", "refused")
    assert entry.refusal == result
    assert entry.to_dict() == {
        "outcome": "refused",
        "anchor": req.anchor.to_dict(),
        "replacement": "REPLACED",
        "refusal": {
            "reason": "not-found",
            "detail": _quote_not_found_detail("nothing matches this"),
        },
    }
    _roundtrip(entry)


def test_narrative_edit_apply_issues_a_patch():
    tree = _page(_para("p1", "hello world"))
    plan = dry_run([_req("hello world", "REPLACED")], tree)
    opener = StubOpener([_block_payload("p1", [_run("hello world")]), _patch_ok()])

    log = apply(plan, _client(opener), "docX")

    assert _methods(opener) == ["GET", "PATCH"]           # read live block, then patch it
    patch = _by_method(opener, "PATCH")[0]
    assert "/blocks/p1" in patch["url"]
    assert log.entries[0].outcome == "applied"
    assert (log.entries[0].before, log.entries[0].after) == ("hello world", "REPLACED")


# =========================================================================== #
# TABLE-CELL EDIT — TableLocator anchor → cell patch (op="edit" + cell context) #
# =========================================================================== #

def _metric_table():
    return _page(_table(
        "t1",
        [[("h0", "Metric"), ("h1", "Q3")], [("r0", "On-time delivery"), ("r1", "97.2%")]],
    ))


def test_table_cell_edit_resolve_preview_serialize():
    tree = _metric_table()
    req = _treq("On-time delivery", column_header="Q3", replacement="NEW")

    result = resolve(req, tree)
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "r1"                        # the target cell
    assert result.cell == ResolvedCell(
        row=1, column=1, row_key="On-time delivery", column_label="Q3",
        target_text_block_id="r1__t", key_text_block_id="r0__t",
    )

    entry = dry_run([req], tree).entries[0]
    assert (entry.op, entry.outcome) == ("edit", "resolved")
    assert (entry.block_id, entry.before, entry.after) == ("r1", "97.2%", "NEW")
    assert entry.cell == result.cell

    # a resolved TABLE edit is a tagless "edit" carrying the cell context sub-dict
    assert entry.to_dict() == {
        "outcome": "resolved",
        "anchor": req.anchor.to_dict(),
        "replacement": "NEW",
        "block_id": "r1",
        "before": "97.2%",
        "after": "NEW",
        "cell": {
            "row": 1, "column": 1, "row_key": "On-time delivery", "column_label": "Q3",
            "target_text_block_id": "r1__t", "key_text_block_id": "r0__t",
        },
    }
    _roundtrip(entry)


def test_table_cell_edit_apply_double_revalidates_then_patches_inner_block():
    tree = _metric_table()
    plan = dry_run([_treq("On-time delivery", column_header="Q3", replacement="NEW")], tree)
    opener = StubOpener([
        _block_payload("r0__t", [_run("On-time delivery")]),   # (1) key cell re-read
        _block_payload("r1__t", [_run("97.2%")]),              # (2) target cell re-read
        _patch_ok(),                                           # (3) patch inner block
    ])

    log = apply(plan, _client(opener), "docX")

    assert _methods(opener) == ["GET", "GET", "PATCH"]         # DOUBLE re-validation, then patch
    patch = _by_method(opener, "PATCH")[0]
    assert "/blocks/r1__t" in patch["url"]                     # writes the INNER text block
    assert log.entries[0].outcome == "applied"
    assert log.entries[0].block_id == "r1"                     # apply-log carries the CELL id


# =========================================================================== #
# INSERT — reference anchor + position → create children (op="insert")          #
# =========================================================================== #

def test_insert_resolve_preview_serialize():
    tree = _page(_para("p1", "first line"), _para("p2", "second line"))
    req = _insert("first line", InsertPosition.AFTER, ["brand new paragraph"])

    result = resolve(req, tree)
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "p1"
    assert result.insertion == ResolvedInsertion(position="after", parent_block_id="root", index=1)

    entry = dry_run([req], tree).entries[0]
    assert (entry.op, entry.outcome) == ("insert", "resolved")
    assert entry.position == "after"
    assert [p.text for p in entry.content] == ["brand new paragraph"]

    assert entry.to_dict() == {
        "outcome": "resolved",
        "anchor": req.reference.to_dict(),
        "op": "insert",
        "position": "after",
        "content": [{"text": "brand new paragraph"}],
        "block_id": "p1",
        "insertion_point": {"position": "after", "parent_block_id": "root", "index": 1},
    }
    _roundtrip(entry)


def test_insert_refused_serialize():
    tree = _page(_para("p1", "first line"))
    req = _insert("no such reference", InsertPosition.AFTER, ["x"])

    result = resolve(req, tree)
    assert result == Refusal.not_found(detail=_quote_not_found_detail("no such reference"))

    entry = dry_run([req], tree).entries[0]
    assert (entry.op, entry.outcome) == ("insert", "refused")
    assert entry.to_dict() == {
        "outcome": "refused",
        "anchor": req.reference.to_dict(),
        "op": "insert",
        "position": "after",
        "content": [{"text": "x"}],
        "refusal": {
            "reason": "not-found",
            "detail": _quote_not_found_detail("no such reference"),
        },
    }
    _roundtrip(entry)


def test_insert_apply_posts_children():
    tree = _page(_para("p1", "first line"), _para("p2", "second line"))
    plan = dry_run([_insert("first line", InsertPosition.AFTER, ["brand new paragraph"])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("first line")], parent_id="root"),   # reference re-validation
        _parent_payload("root", ["p1", "p2"]),          # LIVE parent → the index (LD-453)
        _create_ok(["newX"]),
    ])

    log = apply(plan, _client(opener), "docX")

    # read the reference, read its LIVE parent for the index, then create.
    assert _methods(opener) == ["GET", "GET", "POST"]
    post = _by_method(opener, "POST")[0]
    assert "/blocks/root/children" in post["url"]
    assert post["body"]["index"] == 1
    assert log.entries[0].outcome == "inserted"
    assert list(log.entries[0].created_block_ids) == ["newX"]


# =========================================================================== #
# DELETE — target anchor → batch delete (op="delete", destructive-safe)         #
# =========================================================================== #

def test_delete_resolve_preview_serialize():
    tree = _page(_para("p1", "to remove"))
    req = _delete("to remove")

    result = resolve(req, tree)
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "p1"
    assert result.cell is None and result.insertion is None

    entry = dry_run([req], tree).entries[0]
    assert (entry.op, entry.outcome) == ("delete", "resolved")
    assert (entry.block_id, entry.before) == ("p1", "to remove")

    assert entry.to_dict() == {
        "outcome": "resolved",
        "anchor": req.target.to_dict(),
        "op": "delete",
        "block_id": "p1",
        "before": "to remove",
    }
    _roundtrip(entry)


def test_delete_refused_serialize():
    tree = _page(_para("p1", "to remove"))
    req = _delete("no such target")

    entry = dry_run([req], tree).entries[0]
    assert (entry.op, entry.outcome) == ("delete", "refused")
    assert entry.to_dict() == {
        "outcome": "refused",
        "anchor": req.target.to_dict(),
        "op": "delete",
        "refusal": {
            "reason": "not-found",
            "detail": _quote_not_found_detail("no such target"),
        },
    }
    _roundtrip(entry)


def test_delete_apply_captures_payload_then_batch_deletes():
    tree = _page(_para("p1", "to remove"))
    plan = dry_run([_delete("to remove")], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("to remove")], parent_id="root"),   # target re-read (+ capture)
        _parent_payload("root", ["p1"]),                               # live parent for the range
        _delete_ok(),
    ])

    log = apply(plan, _client(opener), "docX")

    assert _methods(opener) == ["GET", "GET", "DELETE"]                 # read target, read parent, delete
    deleted = _by_method(opener, "DELETE")[0]
    assert "/blocks/root/children/batch_delete" in deleted["url"]
    assert log.entries[0].outcome == "deleted"
    assert log.entries[0].block_id == "p1"
    # destructive-safe: the removed payload was captured
    assert log.entries[0].removed_payload["block_id"] == "p1"


# =========================================================================== #
# SUB-SPAN — block anchor + span → surgical span patch (op="subspan")           #
# =========================================================================== #

def test_subspan_resolve_preview_serialize():
    tree = _page(_para("p1", "the quick brown fox"))
    req = _subspan("the quick brown fox", "quick", "slow")

    result = resolve(req, tree)
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "p1"

    entry = dry_run([req], tree).entries[0]
    assert (entry.op, entry.outcome) == ("subspan", "resolved")
    # on a resolved sub-span: before == span, after == replacement
    assert (entry.span, entry.before, entry.after) == ("quick", "quick", "slow")

    assert entry.to_dict() == {
        "outcome": "resolved",
        "anchor": req.anchor.to_dict(),
        "op": "subspan",
        "span": "quick",
        "replacement": "slow",
        "block_id": "p1",
        "before": "quick",
        "after": "slow",
    }
    _roundtrip(entry)


def test_subspan_refused_serialize():
    tree = _page(_para("p1", "the quick brown fox"))
    # span absent from the block → not-found refusal
    req = _subspan("the quick brown fox", "zebra", "slow")

    result = resolve(req, tree)
    assert result == Refusal.not_found(
        detail=_span_absent_detail("zebra", "p1", "the quick brown fox")
    )

    entry = dry_run([req], tree).entries[0]
    assert (entry.op, entry.outcome) == ("subspan", "refused")
    assert entry.to_dict() == {
        "outcome": "refused",
        "anchor": req.anchor.to_dict(),
        "op": "subspan",
        "span": "zebra",
        "replacement": "slow",
        "refusal": {
            "reason": "not-found",
            "detail": _span_absent_detail("zebra", "p1", "the quick brown fox"),
        },
    }
    _roundtrip(entry)


def test_subspan_apply_issues_a_patch():
    tree = _page(_para("p1", "the quick brown fox"))
    plan = dry_run([_subspan("the quick brown fox", "quick", "slow")], tree)
    opener = StubOpener([_block_payload("p1", [_run("the quick brown fox")]), _patch_ok()])

    log = apply(plan, _client(opener), "docX")

    assert _methods(opener) == ["GET", "PATCH"]
    patch = _by_method(opener, "PATCH")[0]
    assert "/blocks/p1" in patch["url"]
    assert log.entries[0].outcome == "applied"
    assert (log.entries[0].before, log.entries[0].after) == ("quick", "slow")


# =========================================================================== #
# MIXED BATCH — one dry_run over all five ops in one plan: the strongest         #
# single pin that each request kind keeps its own dispatch arm (no cross-wire).  #
# =========================================================================== #

def test_mixed_batch_preserves_per_op_dispatch_and_order():
    tree = _page(
        _para("p1", "alpha line"),
        _para("p2", "beta line"),
        _table("t1", [[("h0", "Metric"), ("h1", "Q3")], [("r0", "uptime"), ("r1", "99.9%")]]),
    )
    requests = [
        _req("alpha line", "ALPHA"),                                    # narrative edit
        _treq("uptime", column_header="Q3", replacement="TABLE"),      # table-cell edit
        _insert("beta line", InsertPosition.BEFORE, ["inserted"]),     # insert
        _delete("beta line"),                                          # delete
        _subspan("alpha line", "alpha", "ALFA"),                       # sub-span
    ]

    plan = dry_run(requests, tree)
    ops = [e.op for e in plan.entries]
    assert ops == ["edit", "edit", "insert", "delete", "subspan"]      # 1:1, in order, per kind

    # the first "edit" is narrative (no cell); the second is a table cell (cell present)
    assert plan.entries[0].cell is None
    assert plan.entries[1].cell is not None and plan.entries[1].block_id == "r1"

    # whole-plan JSON round-trips losslessly (the wire contract for the batch)
    restored = [PlanEntry.from_dict(d) for d in plan.to_dict()["entries"]]
    assert restored == list(plan.entries)


def test_deserialize_unknown_op_fails_loud():
    """LD-099 semantic pin: an unknown ``op`` tag on a serialized entry RAISES on
    deserialize (the LD-097 registry lookup miss) rather than silently coercing to
    DELETE (the pre-LD-097 ``PlanEntry.from_dict`` ``else`` branch). The architect
    accepts fail-loud as the safer behavior — silent coerce-to-delete on a corrupt
    wire dict was the dangerous one. Pinned to the typed :class:`LarkDocIOError`
    family (Dev wrapped the lookup miss in ``LarkConfigError`` — see the handoff)."""
    good = dry_run([_delete("to remove")], _page(_para("p1", "to remove"))).entries[0].to_dict()
    assert good["op"] == "delete"                       # a valid tagged entry to corrupt
    corrupt = dict(good, op="frobnicate")               # an op tag no descriptor registers
    with pytest.raises(LarkDocIOError):
        PlanEntry.from_dict(corrupt)


def test_refusal_reason_enum_values_are_pinned():
    # A cross-wired refusal (e.g. a subspan routed through delete's serializer) would
    # surface as the wrong reason string; pin the vocabulary the wire format emits.
    assert RefusalReason.NOT_FOUND.value == "not-found"
    assert RefusalReason.AMBIGUOUS.value == "ambiguous-N-candidates"
    assert RefusalReason.SPAN_NOT_SPLITTABLE.value == "span-not-splittable"
    assert RefusalReason.CANNOT_HOLD_CHILDREN.value == "cannot-hold-children"
    assert RefusalReason.COLUMN_NOT_FOUND.value == "column-not-found"
