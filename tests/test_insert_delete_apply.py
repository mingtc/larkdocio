"""Offline unit tests for the insert/delete apply engine (LD-076).

W3-S3 executes **insert** and **delete** plans through the **existing plan-gated
pipeline** — no new endpoints, lifting W0's raw ``create_children`` / ``batch_delete``
into the plan-gated, re-validated, apply-logged path (spike Test 3 create-children,
Test 8 batch_delete):

* a resolved **insert** creates the text-bearing paragraph(s) via
  :meth:`WriteClient.create_children` at the **index computed from the resolved
  reference** (before/after/append-into — carried on the
  :class:`~larkdocio.write.resolve.ResolvedInsertion` the S2 resolver attached), and its
  apply-log entry records the created block id(s);
* a resolved **delete** removes the target via :meth:`WriteClient.batch_delete` (the
  contiguous child range covering the target, located from the LIVE parent's child
  order). Because deletion is **destructive**, the engine captures the target block's
  **full payload** (elements + per-run style + block-level style) **before** deleting and
  records it in the delete's apply-log entry, so a consumer can reconstruct what was
  removed — an incomplete payload is a FAIL (the block create/delete spec § Decision (c) / AC4).

Both **re-validate against the live block right before writing** (the reference/target
must still match its anchor → else ``stale-anchor`` skip, no write), are **throttled**
through W0's transport, and produce one apply-log entry per processed edit. All offline
(a fake clock + a stub opener, no network); the full insert/delete WRITE round-trip is
S5 (LD-078).
"""
import json

from log_reading_apply import reading_the_log
from larkdocio.write.apply import apply
apply = reading_the_log(apply)
from larkdocio.write.model import ApplyLog, InsertPosition, RefusalReason
from larkdocio.write.preview import dry_run

# Shared fake-transport doubles + node/request builders (LD-088). ``_req`` is the
# shared edit-request builder (this file's former ``_edit``).
from write_harness import (
    FakeClock,
    StubOpener,
    _block_payload,
    _by_method,
    _client,
    _delete,
    _heading,
    _insert,
    _methods,
    _page,
    _para,
    _parent_payload,
    _patch_ok,
    _req,
    _run,
)


# --------------------------------------------------------------------------- #
# file-local payloads (insert/delete-specific). The node/request builders        #
# (_para / _heading / _page / _insert / _delete / _req) and the fake transport   #
# (_run / _block_payload / _patch_ok / _client / _methods / _by_method) live in   #
# write_harness.                                                                  #
# --------------------------------------------------------------------------- #

def _create_ok(created_ids):
    """A ``create_children`` response: ``data.children`` carries the new block id(s)."""
    return {"code": 0, "data": {
        "children": [{"block_id": bid} for bid in created_ids],
        "document_revision_id": 200,
    }}


def _delete_ok():
    return {"code": 0, "data": {"document_revision_id": 201}}


# --------------------------------------------------------------------------- #
# AC1 — insert apply at the computed index (create_children, parent + index)     #
# --------------------------------------------------------------------------- #

def test_insert_after_creates_children_at_the_computed_parent_and_index():
    tree = _page(_para("p1", "first line"), _para("p2", "second line"))
    plan = dry_run([_insert("first line", InsertPosition.AFTER, ["a brand new paragraph"])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("first line")], parent_id="root"),  # reference re-validation
        _parent_payload("root", ["p1", "p2"]),        # LIVE parent → the index (LD-453)
        _create_ok(["newX"]),
    ])
    log = apply(plan, _client(opener), "doc123")

    post = _by_method(opener, "POST")[0]
    assert "/documents/doc123/blocks/root/children" in post["url"]     # parent = root
    assert post["body"] == {
        "index": 1,                                                     # AFTER p1 (index 0) → 1
        "children": [
            {"block_type": 2, "text": {"elements": [{"text_run": {"content": "a brand new paragraph"}}]}}
        ],
    }
    assert log.entries[0].outcome == "inserted"


def test_insert_before_targets_the_reference_own_index():
    tree = _page(_para("p1", "first line"), _para("p2", "second line"))
    plan = dry_run([_insert("second line", InsertPosition.BEFORE, ["inserted before second"])], tree)
    opener = StubOpener([
        _block_payload("p2", [_run("second line")], parent_id="root"),
        _parent_payload("root", ["p1", "p2"]),        # LIVE parent → the index (LD-453)
        _create_ok(["newY"]),
    ])
    apply(plan, _client(opener), "doc123")

    post = _by_method(opener, "POST")[0]
    assert "/blocks/root/children" in post["url"]
    assert post["body"]["index"] == 1                                   # BEFORE p2 (index 1) → 1


def test_insert_append_into_targets_the_reference_as_parent_appended_last():
    # append-into a heading → the parent of create_children is the REFERENCE itself (the
    # heading), not its parent, and the write goes at the API's own append index, -1.
    # LD-453: `append-into` means LAST, so the engine no longer sends the plan-time child
    # count — that ordinal decays the moment another entry in the same batch appends
    # first, which used to reverse two same-parent append-into entries.
    tree = _page(_heading("h1", "Section One", children=[_para("c1", "existing child")]))
    plan = dry_run([_insert("Section One", InsertPosition.APPEND_INTO, ["appended child"])], tree)
    opener = StubOpener([
        _block_payload("h1", [_run("Section One")], block_type=3, key="heading1", parent_id="root"),
        _create_ok(["newZ"]),
    ])
    apply(plan, _client(opener), "doc123")

    post = _by_method(opener, "POST")[0]
    assert "/blocks/h1/children" in post["url"]                         # parent = the heading itself
    assert post["body"]["index"] == -1                                  # appended last, live


# --------------------------------------------------------------------------- #
# AC2 — delete apply (batch_delete over the target's contiguous child range)     #
# --------------------------------------------------------------------------- #

def test_delete_removes_the_target_via_batch_delete_at_its_live_parent_range():
    tree = _page(_para("a", "keep A"), _para("d1", "delete me"), _para("b", "keep B"))
    plan = dry_run([_delete("delete me")], tree)
    opener = StubOpener([
        _block_payload("d1", [_run("delete me")], parent_id="root"),   # target read (stale-check + capture)
        _parent_payload("root", ["a", "d1", "b"]),                     # parent read (locate index)
        _delete_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")

    delete = _by_method(opener, "DELETE")[0]
    assert "/documents/doc123/blocks/root/children/batch_delete" in delete["url"]  # parent = root
    assert delete["body"] == {"start_index": 1, "end_index": 2}         # d1 sits at index 1
    assert log.entries[0].outcome == "deleted"
    assert log.entries[0].block_id == "d1"


# --------------------------------------------------------------------------- #
# AC3 — live re-validation before each write (drift → stale-anchor skip)          #
# --------------------------------------------------------------------------- #

def test_insert_stale_when_reference_drifts_skips_the_write():
    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert("anchor line", InsertPosition.AFTER, ["never created"])], tree)
    # the live reference DRIFTED — the anchor quote is no longer a substring.
    opener = StubOpener([
        _block_payload("p1", [_run("totally different now")], parent_id="root"),
        # deliberately NO create payload queued — a POST here would be a bug.
    ])
    log = apply(plan, _client(opener), "doc123")

    assert _methods(opener) == ["GET"]                                  # read the reference, never created
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR


def test_delete_stale_when_target_drifts_skips_the_write():
    tree = _page(_para("d1", "remove this line"))
    plan = dry_run([_delete("remove this line")], tree)
    # the live target DRIFTED — quote gone → refuse, and NEVER read the parent / delete.
    opener = StubOpener([
        _block_payload("d1", [_run("this text changed entirely")], parent_id="root"),
        # NO parent GET, NO delete queued — any further call is a bug.
    ])
    log = apply(plan, _client(opener), "doc123")

    assert _methods(opener) == ["GET"]                                  # read only the target, never deleted
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.STALE_ANCHOR


# --------------------------------------------------------------------------- #
# AC4 — delete apply-log carries the FULL removed payload (DESTRUCTIVE-SAFE)      #
# --------------------------------------------------------------------------- #

def test_delete_log_entry_carries_the_full_removed_block_payload():
    tree = _page(_para("d1", "critical data"))
    plan = dry_run([_delete("critical data")], tree)
    # the live target carries per-run style (bold) AND block-level style (alignment).
    live_elements = [_run("critical ", bold=True), _run("data", text_color=5)]
    opener = StubOpener([
        _block_payload("d1", live_elements, block_type=2, parent_id="root", style={"align": 2, "folded": False}),
        _parent_payload("root", ["d1"]),
        _delete_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")

    (entry,) = log.entries
    assert entry.outcome == "deleted"
    payload = entry.removed_payload
    # the FULL payload: id + type + elements (with per-run style) + block-level style.
    assert payload["block_id"] == "d1"
    assert payload["block_type"] == 2
    assert payload["elements"] == live_elements          # per-run bold + text_color preserved
    assert payload["style"] == {"align": 2, "folded": False}
    # the destructive record round-trips through JSON losslessly (nothing lost).
    assert ApplyLog.from_dict(json.loads(log.to_json())).entries == log.entries
    restored = ApplyLog.from_json(log.to_json()).entries[0]
    assert restored.removed_payload["elements"][0]["text_run"]["text_element_style"] == {"bold": True}


# --------------------------------------------------------------------------- #
# AC5 — insert apply-log records the created id(s)                               #
# --------------------------------------------------------------------------- #

def test_insert_log_entry_records_the_created_block_ids():
    tree = _page(_para("p1", "the anchor"))
    plan = dry_run([_insert("the anchor", InsertPosition.AFTER, ["para one", "para two"])], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("the anchor")], parent_id="root"),
        _parent_payload("root", ["p1"]),                                # LIVE parent (LD-453)
        _create_ok(["created-1", "created-2"]),                         # two new ids from the API
    ])
    log = apply(plan, _client(opener), "doc123")

    (entry,) = log.entries
    assert entry.outcome == "inserted"
    assert entry.created_block_ids == ("created-1", "created-2")
    # the inserted entry round-trips through JSON losslessly.
    assert ApplyLog.from_dict(json.loads(log.to_json())).entries == log.entries


# --------------------------------------------------------------------------- #
# AC6 — throttled + refusals never write                                        #
# --------------------------------------------------------------------------- #

def test_insert_delete_writes_route_through_the_shared_throttle_not_a_raw_socket():
    tree = _page(_para("p1", "alpha unique"), _para("p2", "beta unique"))
    plan = dry_run([
        _insert("alpha unique", InsertPosition.AFTER, ["ins A"]),
        _insert("beta unique", InsertPosition.AFTER, ["ins B"]),
    ], tree)
    clock = FakeClock()
    opener = StubOpener([
        _block_payload("p1", [_run("alpha unique")], parent_id="root"),
        _parent_payload("root", ["p1", "p2"]), _create_ok(["a"]),
        _block_payload("p2", [_run("beta unique")], parent_id="root"),
        _parent_payload("root", ["p1", "ins A", "p2"]), _create_ok(["b"]),
    ])
    apply(plan, _client(opener, clock=clock), "doc123")

    # every call (4 GET + 2 POST) went through the injected opener — not a raw socket.
    # Each insert now reads its LIVE parent for the index too (LD-453), so the GETs come
    # in pairs: reference re-validation, then the parent whose child order decides WHERE.
    assert _methods(opener) == ["GET", "GET", "POST", "GET", "GET", "POST"]
    # calls past the 3rd in the same second were PACED by the ≤3/sec limiter — proof the
    # engine did not bypass common/transport.py.
    assert clock.sleeps == [1.0]


def test_only_resolved_and_fresh_insert_delete_edits_write():
    tree = _page(
        _para("p1", "anchor one"),
        _para("dupA", "twin"), _para("dupB", "twin"),       # ambiguous insert reference
        _para("del1", "remove one"),                        # resolves, but live drifts → stale
        _para("del2", "remove two"),                        # resolves fresh → deletes
    )
    plan = dry_run([
        _insert("anchor one", InsertPosition.AFTER, ["inserted"]),   # resolved → creates
        _insert("twin", InsertPosition.AFTER, ["nope"]),             # ambiguous ref → refused @plan
        _delete("remove one"),                                       # resolves, drifts live → stale
        _delete("remove two"),                                       # resolved fresh → deletes
    ], tree)
    opener = StubOpener([
        _block_payload("p1", [_run("anchor one")], parent_id="root"),                       # insert:
        _parent_payload("root", ["p1", "dupA", "dupB", "del1", "del2"]), _create_ok(["i1"]),
        _block_payload("del1", [_run("changed entirely")], parent_id="root"),               # stale delete → no write
        _block_payload("del2", [_run("remove two")], parent_id="root"),                     # fresh delete:
        _parent_payload("root", ["p1", "dupA", "dupB", "del1", "del2"]), _delete_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")

    # exactly TWO writes — one create (insert) + one batch_delete (fresh delete).
    assert len(_by_method(opener, "POST")) == 1
    assert len(_by_method(opener, "DELETE")) == 1
    outcomes = [e.outcome for e in log.entries]
    assert outcomes == ["inserted", "refused", "refused", "deleted"]
    reasons = [e.refusal.reason for e in log.entries[1:3]]
    assert reasons == [RefusalReason.AMBIGUOUS, RefusalReason.STALE_ANCHOR]
    # the ambiguous refusal still carries its candidate ids (from the plan).
    assert set(log.entries[1].refusal.candidate_ids) == {"dupA", "dupB"}


# --------------------------------------------------------------------------- #
# AC7 — insert + delete + edit coexist in one plan-gated batch (dispatch intact) #
# --------------------------------------------------------------------------- #

def test_edit_insert_delete_apply_in_one_batch():
    tree = _page(
        _para("p", "edit this paragraph"),
        _para("ref", "insert after me"),
        _para("gone", "delete this paragraph"),
    )
    plan = dry_run([
        _req("edit this paragraph", replacement="edited paragraph"),   # edit: 1 GET + PATCH
        _insert("insert after me", InsertPosition.AFTER, ["new sibling"]),  # insert: 1 GET + POST
        _delete("delete this paragraph"),                               # delete: 2 GET + DELETE
    ], tree)
    opener = StubOpener([
        _block_payload("p", [_run("edit this paragraph")], parent_id="root"), _patch_ok(),
        _block_payload("ref", [_run("insert after me")], parent_id="root"),
        _parent_payload("root", ["p", "ref", "gone"]), _create_ok(["ins"]),
        _block_payload("gone", [_run("delete this paragraph")], parent_id="root"),
        _parent_payload("root", ["p", "ref", "gone"]), _delete_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")

    assert [e.outcome for e in log.entries] == ["applied", "inserted", "deleted"]
    assert _methods(opener) == ["GET", "PATCH", "GET", "GET", "POST", "GET", "GET", "DELETE"]
