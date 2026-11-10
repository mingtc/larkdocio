"""LD-482 — a table that fits the measured envelope is authored in ONE atomic call.

The shipped route builds a table in three movements: create a ≤9-per-axis seed grid, append
a row per call until it is the authored height, then fill the cells. Each movement is its own
throttled write, so a failure partway through leaves **a real, wrong table in a real
document** — half-grown, or grown and half-filled. Lark's ``descendant`` endpoint takes the
whole subtree, cells and text, in **one** call: the consumer's own 216-cell grid measured
**1 call / 0.82 s** there against **463 calls / 158.41 s** through the pre-LD-481 fill, and
every over-envelope refusal the spike provoked read back as **nothing created**
(``dev/spikes/2026-08-14-table-cell-creation-cap.md`` §§ 3a/3b/3c, in the dev repo).

What this file pins, all offline:

* **the route-selection rule** — exactly one table, inside ``2 × cells + 1 ≤ 1000``. Anything
  else (a table sharing its entry with another block, a table over the envelope, a nested
  tree) keeps the shipped route, whole. The rule is *tested*, not merely stated;
* **positioning** — the binding gate. The table lands at the requested index among its
  siblings, alone and in a **mixed batch**, against the double whose tree actually mutates
  under the batch's own writes (:class:`~write_harness.LiveTreeOpener`). LD-453's own
  conformance suite is untouched and still green;
* **atomicity** — the one call is the only call, and what happens to the REST of a mixed batch
  when Lark refuses the subtree is asserted, not discovered;
* **block-id reporting** — one created id, the table's, resolved by NAME out of
  ``block_id_relations``, still usable as an ``AnchorById``;
* **reader equivalence** — the same content authored both ways renders **byte-identical**
  through larkdocio's own reader.

The live arm — the same table authored on the wire, counted, read back and torn down — is
``tests/test_live_write_one_call_table_gate.py`` (``pytest -m live_write``).
"""
import json

import pytest

from larkdocio.errors import LarkAPIError, LarkApplyRefusedError
from larkdocio.write import (
    MAX_TABLE_CELLS,
    AnchorById,
    InsertPosition,
    InsertRequest,
    NewBlock,
    NewParagraph,
    apply,
    compose,
    dry_run,
)
from larkdocio.write.client import MAX_DESCENDANTS_PER_CALL
from larkdocio.write.encode import (
    MAX_ONE_CALL_TABLE_CELLS,
    encode_content,
    fits_one_call,
    table_descendants,
    table_subtree,
)

from compose_roundtrip import doc_double
from harness import render
from write_harness import LiveTreeOpener, _client, _heading, _page, _para

# The one-call envelope is MEASURED EXTERNAL TRUTH and the positional contract is the promise
# a consumer holds. An implementation regenerated from this corpus that fails either has the
# product wrong, not merely different. process/doctrine/conformance-tier.md § A.4.
pytestmark = pytest.mark.conformance


SEED = [("s1", "Section One"), ("a1", "Alpha body paragraph."),
        ("s2", "Section Two"), ("b1", "Beta body paragraph.")]


def _seed_tree():
    return _page(*[_para(bid, text) for bid, text in SEED])


def _seed_opener(**kwargs):
    return LiveTreeOpener(children={"root": [bid for bid, _ in SEED]},
                          texts=dict(SEED), **kwargs)


def _grid(rows, columns, *, prefix="r"):
    return [[f"{prefix}{r}c{c}" for c in range(columns)] for r in range(rows)]


def _table(rows, columns, **kwargs):
    return NewBlock.table(_grid(rows, columns), **kwargs)


def _insert(block_id, content, position=InsertPosition.AFTER):
    return InsertRequest(reference=AnchorById(block_id=block_id), position=position,
                         content=tuple(content))


def _descendant_calls(opener):
    return [c for c in opener.calls
            if c["method"] == "POST" and "/descendant" in c["path"]]


def _children_calls(opener):
    return [c for c in opener.calls
            if c["method"] == "POST" and c["path"].split("?")[0].endswith("/children")]


# --------------------------------------------------------------------------- #
# AC1 — the ROUTE-SELECTION RULE, stated and tested                             #
# --------------------------------------------------------------------------- #

def test_the_envelope_is_derived_from_the_measured_ceiling_and_not_re_measured():
    assert MAX_DESCENDANTS_PER_CALL == 1000
    assert MAX_ONE_CALL_TABLE_CELLS == 499 == (MAX_DESCENDANTS_PER_CALL - 1) // 2
    # the spike's own two bisection points, reproduced by the arithmetic
    assert table_descendants(499) == 999 <= MAX_DESCENDANTS_PER_CALL
    assert table_descendants(500) == 1001 > MAX_DESCENDANTS_PER_CALL
    # and its 36×6 body, which answered code 0 with 433 descendants
    assert table_descendants(36 * 6) == 433


def test_the_route_is_taken_for_a_lone_table_inside_the_envelope():
    encoded = encode_content((_table(6, 4),))
    assert len(encoded) == 1 and fits_one_call(encoded[0])


def test_the_route_is_NOT_taken_for_a_table_over_the_envelope():
    """500 cells is inside larkdocio's authoring cap and outside Lark's one-call envelope —
    the one shape that proves the two numbers are different things."""
    over = _table(5, 100)                       # 500 cells: ≤ cap, > envelope
    assert 5 * 100 == MAX_TABLE_CELLS > MAX_ONE_CALL_TABLE_CELLS
    assert not fits_one_call(encode_content((over,))[0])


def test_the_route_is_NOT_taken_when_the_table_shares_its_entry_with_another_block():
    """Mixed content would need a SEQUENCE of calls at arithmetically-advanced indexes —
    new positional logic in the insert path, which LD-482 names as its split condition. The
    rule keeps mixed content on the shipped route instead."""
    opener = _seed_opener()
    plan = dry_run([_insert("a1", (NewParagraph("intro"), _table(3, 3)))], _seed_tree())
    apply(plan, _client(opener), "doc482")

    assert _descendant_calls(opener) == []
    assert _children_calls(opener), "mixed content must still go through create_children"


def test_a_non_table_insert_is_untouched_by_the_route():
    opener = _seed_opener()
    plan = dry_run([_insert("a1", (NewParagraph("just a paragraph"),))], _seed_tree())
    apply(plan, _client(opener), "doc482")

    assert _descendant_calls(opener) == []
    assert len(_children_calls(opener)) == 1


# --------------------------------------------------------------------------- #
# AC1 — what goes on the wire: ONE call, the AUTHORED grid, 2×cells+1 blocks     #
# --------------------------------------------------------------------------- #

def test_a_lone_table_is_authored_in_exactly_one_write_call():
    opener = _seed_opener()
    plan = dry_run([_insert("a1", (_table(12, 6),))], _seed_tree())
    apply(plan, _client(opener), "doc482")

    assert len(_descendant_calls(opener)) == 1
    assert _children_calls(opener) == [], "no create_children — the subtree IS the call"
    assert [c for c in opener.calls if c["method"] == "PATCH"] == [], (
        "no grow and no fill: a PATCH here means the three-movement route came back")


def test_the_one_call_body_declares_the_AUTHORED_grid_not_the_nine_per_axis_seed():
    """The 9-per-axis ceiling is the *create* endpoint's property-form validation. This route
    does not go through it — the spike created a 36-row table in one call."""
    opener = _seed_opener()
    plan = dry_run([_insert("a1", (_table(36, 6),))], _seed_tree())
    apply(plan, _client(opener), "doc482")

    body = _descendant_calls(opener)[0]["body"]
    table = body["descendants"][0]
    assert table["table"]["property"]["row_size"] == 36
    assert table["table"]["property"]["column_size"] == 6
    assert len(body["descendants"]) == table_descendants(216) == 433
    assert body["children_id"] == [table["block_id"]]
    assert len(table["children"]) == 216


def test_every_cell_carries_an_inner_text_block_because_a_childless_cell_is_REFUSED():
    """``1770041 open schema mismatch`` — measured. An empty authored cell is not a cheaper
    spelling; it gets the same empty run an authored empty paragraph does."""
    root, descendants = table_subtree(
        encode_content((NewBlock.table([["a", ""], ["", "d"]]),))[0]
    )
    cells = [d for d in descendants if d["block_type"] == 32]
    texts = [d for d in descendants if d["block_type"] == 2]
    assert len(cells) == 4 and len(texts) == 4
    assert all(len(cell["children"]) == 1 for cell in cells)
    assert [t["text"]["elements"][0]["text_run"]["content"] for t in texts] == [
        "a", "", "", "d"]
    assert descendants[0]["block_id"] == root


def test_the_body_is_json_serialisable_and_carries_no_real_block_ids():
    _, descendants = table_subtree(encode_content((_table(3, 3),))[0])
    json.dumps(descendants)                    # it has to survive the wire
    assert all(d["block_id"].startswith("larkdocio_") for d in descendants)


# --------------------------------------------------------------------------- #
# AC2 — POSITIONING. The binding gate: alone AND in a mixed batch.               #
# --------------------------------------------------------------------------- #

def test_the_table_lands_at_the_requested_index_among_its_siblings():
    opener = _seed_opener()
    plan = dry_run([_insert("a1", (_table(3, 3),))], _seed_tree())
    log = apply(plan, _client(opener), "doc482")

    table_id = log.entries[0].created_block_ids[0]
    assert opener.children["root"] == ["s1", "a1", table_id, "s2", "b1"]
    assert opener.index_of(table_id) == opener.index_of("a1") + 1


def test_the_table_lands_BEFORE_its_reference_when_that_is_what_was_asked():
    opener = _seed_opener()
    plan = dry_run([_insert("b1", (_table(2, 2),), InsertPosition.BEFORE)], _seed_tree())
    log = apply(plan, _client(opener), "doc482")

    table_id = log.entries[0].created_block_ids[0]
    assert opener.children["root"] == ["s1", "a1", "s2", table_id, "b1"]


def test_append_into_puts_the_table_last_inside_the_parent_the_plan_named():
    tree = _page(_heading("h1", "Section One", children=[_para("c1", "existing child")]))
    opener = LiveTreeOpener(children={"root": ["h1"], "h1": ["c1"]},
                            texts={"h1": "Section One", "c1": "existing child"},
                            block_types={"h1": 3})
    plan = dry_run([_insert("h1", (_table(2, 2),), InsertPosition.APPEND_INTO)], tree)
    log = apply(plan, _client(opener), "doc482")

    assert _descendant_calls(opener)[0]["body"]["index"] == -1
    assert opener.children["h1"] == ["c1", log.entries[0].created_block_ids[0]]


def test_a_MIXED_BATCH_of_paragraph_and_table_inserts_each_land_beside_their_own_anchor():
    """The LD-453 defect shape, with a table in it: two same-parent inserts in ONE batch, the
    second of which takes the lifted-out route. Each must land beside its own reference — a
    drift here is exactly the bug class LD-453 repaired."""
    opener = _seed_opener()
    plan = dry_run(
        [
            _insert("a1", (NewParagraph("MARKER after Alpha."),)),
            _insert("b1", (_table(3, 4),)),
        ],
        _seed_tree(),
    )
    log = apply(plan, _client(opener), "doc482")

    marker_id = log.entries[0].created_block_ids[0]
    table_id = log.entries[1].created_block_ids[0]
    assert opener.children["root"] == ["s1", "a1", marker_id, "s2", "b1", table_id]


def test_a_MIXED_BATCH_whose_TABLE_lands_FIRST_still_places_the_later_insert_correctly():
    """The direction that used to break: an earlier same-parent insert grew the parent under
    the later entry's plan-time ordinal. The table entry is an insert like any other here, so
    the live-index derivation must still hold with it in the batch."""
    opener = _seed_opener()
    plan = dry_run(
        [
            _insert("a1", (_table(2, 3),)),
            _insert("b1", (NewParagraph("MARKER after Beta."),)),
        ],
        _seed_tree(),
    )
    log = apply(plan, _client(opener), "doc482")

    table_id = log.entries[0].created_block_ids[0]
    marker_id = log.entries[1].created_block_ids[0]
    assert opener.children["root"] == ["s1", "a1", table_id, "s2", "b1", marker_id]


def test_two_tables_into_the_same_parent_in_one_batch_keep_their_own_positions():
    opener = _seed_opener()
    plan = dry_run([_insert("a1", (_table(2, 2),)), _insert("b1", (_table(2, 2),))],
                   _seed_tree())
    log = apply(plan, _client(opener), "doc482")

    first, second = (e.created_block_ids[0] for e in log.entries)
    assert opener.children["root"] == ["s1", "a1", first, "s2", "b1", second]


def test_the_route_reads_its_index_off_the_LIVE_tree_exactly_as_create_children_does():
    """Not an assertion about the endpoint: an assertion that nothing about *deriving* the
    position moved. The index on the wire is the live child index of the reference + 1."""
    opener = _seed_opener()
    plan = dry_run([_insert("s2", (_table(2, 2),))], _seed_tree())
    apply(plan, _client(opener), "doc482")

    assert _descendant_calls(opener)[0]["body"]["index"] == 3   # after "s2", live
    assert _descendant_calls(opener)[0]["path"].split("/blocks/")[1].startswith("root")


# --------------------------------------------------------------------------- #
# AC3 — ATOMICITY, and the specified fate of the rest of a mixed batch          #
# --------------------------------------------------------------------------- #

class _RefusingOpener(LiveTreeOpener):
    """Answers the ``descendant`` call with Lark's own over-envelope refusal, and applies
    nothing to the tree — the spike's measured outcome ("nothing created")."""

    def __call__(self, req, timeout=30):
        if req.get_method() == "POST" and "/descendant" in req.full_url:
            self.calls.append({"method": "POST", "path": req.full_url.split(".com", 1)[-1],
                               "body": json.loads(req.data.decode())})
            from write_harness import _FakeHTTPResponse
            return _FakeHTTPResponse({"code": 99992402, "msg": "field validation failed"})
        return super().__call__(req, timeout=timeout)


def test_a_refused_subtree_leaves_NOTHING_and_names_the_block_it_was_writing():
    opener = _RefusingOpener(children={"root": [bid for bid, _ in SEED]}, texts=dict(SEED))
    plan = dry_run([_insert("a1", (_table(3, 3),))], _seed_tree())

    # TRANSFORMED, NOT STRUCK (LD-643): every assertion is the one this test always made —
    # Lark's code, the named block, the document byte-unchanged, one attempt and no retry.
    # What moved is the CARRIER: the apply-time disposition boundary types the named refusal
    # into the log rather than letting it escape, so the atomicity claim below is now made
    # against a record the caller actually keeps.
    log = apply(plan, _client(opener), "doc482", allow_partial=True)
    detail = log.entries[0].refusal.detail

    assert "99992402" in detail
    assert "block index 0 (kind: table)" in detail
    assert opener.children["root"] == [bid for bid, _ in SEED], (
        "the document must be exactly as it was — the whole point of the atomic route")
    assert len(_descendant_calls(opener)) == 1, "one attempt, no retry, no partial follow-up"


def test_what_happens_to_the_REST_of_a_mixed_batch_is_SPECIFIED():
    """Stated so a caller can plan around it, and unchanged from any other API refusal
    mid-batch: entries BEFORE the table stay applied, the table lands nothing, entries AFTER
    it are never attempted.

    **TRANSFORMED, NOT STRUCK (LD-643).** All three of those terms are unchanged and all three
    are still asserted below, against the same live-tree double — which is what makes this the
    test that proves the boundary added a RECORD and not a write. The fourth term, *"and the
    error propagates out of apply()"*, is the one LD-643 supersedes: propagating is exactly
    what left the caller with no account of the entry that had already applied. It now becomes
    a complete log — one entry per plan entry, the table's classified, the entry after it
    ``not-attempted`` — carried on ``LarkApplyRefusedError.log``.
    """
    opener = _RefusingOpener(children={"root": [bid for bid, _ in SEED]}, texts=dict(SEED))
    plan = dry_run(
        [
            _insert("a1", (NewParagraph("BEFORE the table."),)),
            _insert("b1", (_table(3, 3),)),
            _insert("s2", (NewParagraph("AFTER the table."),)),
        ],
        _seed_tree(),
    )
    with pytest.raises(LarkApplyRefusedError) as excinfo:
        apply(plan, _client(opener), "doc482")

    order = opener.order()
    assert "BEFORE the table." in order, "an entry that already applied stays applied"
    assert "AFTER the table." not in order, "entries after the refusal are never attempted"
    assert len(opener.children["root"]) == len(SEED) + 1, "the table itself landed nothing"

    # …and the account of all three now reaches the caller, which is what LD-643 bought.
    log = excinfo.value.log
    assert [e.outcome for e in log.entries] == ["inserted", "refused", "not-attempted"]
    assert log.halt["index"] == 1


# --------------------------------------------------------------------------- #
# AC4 — BLOCK-ID REPORTING is unchanged for the caller                          #
# --------------------------------------------------------------------------- #

def test_the_apply_log_reports_exactly_one_created_id_the_TABLES():
    opener = _seed_opener(created=["cell-noise", "TABLE-ID"])
    plan = dry_run([_insert("a1", (_table(2, 2),))], _seed_tree())
    log = apply(plan, _client(opener), "doc482")

    entry = log.entries[0]
    assert entry.outcome == "inserted"
    assert len(entry.created_block_ids) == 1, (
        "a table insert has always reported ONE created id; the cells were never reported "
        "by the other route either")
    assert entry.created_block_ids[0] in opener.children["root"]


def test_the_created_id_is_resolved_by_NAME_out_of_the_relation_map_not_by_position():
    """``block_id_relations`` comes back in no particular order — the spike's captures
    interleave them — so positional indexing into it would be a coin flip."""
    from larkdocio.write.apply import _minted_id

    data = {"block_id_relations": [
        {"block_id": "real-x0", "temporary_block_id": "larkdocio_x0"},
        {"block_id": "real-c0", "temporary_block_id": "larkdocio_c0"},
        {"block_id": "real-t", "temporary_block_id": "larkdocio_t"},
    ]}
    assert _minted_id(data, "larkdocio_t") == "real-t"
    # the fallback, for a response that carries the created roots but no relation row
    assert _minted_id({"children": [{"block_id": "root-id"}]}, "larkdocio_t") == "root-id"
    assert _minted_id({}, "larkdocio_t") is None


def test_the_created_id_is_a_usable_ANCHOR_BY_ID_for_a_following_edit():
    opener = _seed_opener()
    plan = dry_run([_insert("a1", (_table(2, 2),))], _seed_tree())
    log = apply(plan, _client(opener), "doc482")
    table_id = log.entries[0].created_block_ids[0]

    assert AnchorById(block_id=table_id).block_id == table_id
    assert opener.children[table_id], "the created id addresses the real table subtree"


# --------------------------------------------------------------------------- #
# AC5 — READER EQUIVALENCE, re-verified rather than inherited                   #
# --------------------------------------------------------------------------- #

def _descendant_doc(content, *, doc_id="root"):
    """The block dicts a document holds after ``content`` was authored through the ONE-CALL
    route — built from :func:`table_subtree`'s real body, so this is the shipped payload and
    not a second description of it."""
    child = encode_content(tuple(content))[0]
    root_temp, descendants = table_subtree(child)
    by_temp = {d["block_id"]: d for d in descendants}
    parent_of = {kid: d["block_id"]
                 for d in descendants for kid in (d.get("children") or ())}
    page = {"block_id": doc_id, "parent_id": "doc", "block_type": 1,
            "page": {"elements": []}, "children": [root_temp]}
    blocks = [page]
    for temp, payload in by_temp.items():
        blocks.append({**payload, "parent_id": parent_of.get(temp, doc_id),
                       "children": list(payload.get("children") or ())})
    return blocks


def test_the_same_table_authored_both_ways_reads_back_BYTE_IDENTICAL():
    """The spike's § 3e finding, re-verified offline against larkdocio's own reader: *"two
    pipe-table runs found, 13 lines each, identical == True"*. A grid at or under the
    9-per-axis create ceiling is used deliberately — that is the shape where the shipped
    route's seeded property and the authored one coincide, so the comparison is about the
    two constructions and not about the seed."""
    content = tuple(compose("| h0 | h1 | h2 |\n|---|---|---|\n| a | b | c |\n| d | e | f |"))
    assert [c.kind.value for c in content] == ["table"]

    shipped = render(doc_double(content), doc_id="root")
    one_call = render(_descendant_doc(content), doc_id="root")
    assert one_call == shipped
    assert "| h0 | h1 | h2 |" in one_call
