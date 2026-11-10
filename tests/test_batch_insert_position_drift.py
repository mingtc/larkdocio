"""LD-453 — a same-parent multi-insert BATCH lands each insert beside its own reference.

The measured defect (dogfood round 4, triage `dev/dogfood4-triage/dogfood4-drift-repro.md`,
live capture `captures/batch-insert-drift.json`): two or more
:class:`~larkdocio.write.model.InsertRequest`\\ s in **one** batch resolving to the **same
parent** landed at **stale ordinals** — each successive insert one position early per
earlier-applied same-parent insert at a lower index. `plan.refusals` was empty, every apply-log
entry said ``inserted`` with real created ids, and only a full read-back showed the document was
wrong.

Why this file is CONFORMANCE-tier (`process/doctrine/conformance-tier.md` § A.4): every case
below asks *"did the block land where the caller asked — beside its own reference?"*, which is
The block create/delete spec § F1 § S2/S3's promise to a consumer. An implementation rewritten from the corpus that
fails any of these has the **product** wrong, not merely different — the choice of *how* the
engine derives the live index (the shipped answer: read it off the live parent, mirroring
`_apply_delete`) is deliberately never asserted here.

All four cases run against :class:`~write_harness.LiveTreeOpener`, a double whose tree actually
**mutates** under the batch's own writes — the property the pre-LD-453 doubles lacked, which is
why the defect was invisible offline.
"""
import pytest

from larkdocio.write.apply import apply
from larkdocio.write.model import (
    AnchorById,
    DeleteRequest,
    InsertPosition,
    InsertRequest,
    NewParagraph,
)
from larkdocio.write.preview import dry_run

from write_harness import LiveTreeOpener, _client, _heading, _page, _para

pytestmark = pytest.mark.conformance


# --------------------------------------------------------------------------- #
# The measured repro's own shape: 6 flat children of the page root, three body   #
# paragraphs anchored by id (the capture's `repro` block, quoted).               #
# --------------------------------------------------------------------------- #

SEED = [
    ("s1", "Section One"),
    ("a1", "Alpha body paragraph."),
    ("s2", "Section Two"),
    ("b1", "Beta body paragraph."),
    ("s3", "Section Three"),
    ("g1", "Gamma body paragraph."),
]

MARKERS = {
    "a1": "MARKER-1 belongs after Alpha.",
    "b1": "MARKER-2 belongs after Beta.",
    "g1": "MARKER-3 belongs after Gamma.",
}


def _seed_tree():
    return _page(*[_para(bid, text) for bid, text in SEED])


def _seed_opener(**kwargs):
    return LiveTreeOpener(
        children={"root": [bid for bid, _ in SEED]},
        texts=dict(SEED),
        **kwargs,
    )


def _insert_by_id(block_id, text, position=InsertPosition.AFTER):
    return InsertRequest(
        reference=AnchorById(block_id=block_id),
        position=position,
        content=(NewParagraph(text),),
    )


# --------------------------------------------------------------------------- #
# AC2.1 — the measured repro: each insert lands after ITS OWN anchor             #
# --------------------------------------------------------------------------- #

def test_three_same_parent_after_inserts_in_one_batch_each_land_after_their_own_anchor():
    """The capture's `repro` block. Pre-fix this produced

        Section One / Alpha / MARKER-1 / Section Two / MARKER-2 / Beta / MARKER-3 /
        Section Three / Gamma

    — MARKER-2 one early, MARKER-3 two early (into the wrong section).
    """
    requests = [_insert_by_id(bid, text) for bid, text in MARKERS.items()]
    plan = dry_run(requests, _seed_tree())
    assert plan.refusals == ()

    opener = _seed_opener()
    log = apply(plan, _client(opener), "doc453")

    assert [entry.outcome for entry in log.entries] == ["inserted"] * 3
    assert opener.order() == [
        "Section One",
        "Alpha body paragraph.",
        "MARKER-1 belongs after Alpha.",
        "Section Two",
        "Beta body paragraph.",
        "MARKER-2 belongs after Beta.",
        "Section Three",
        "Gamma body paragraph.",
        "MARKER-3 belongs after Gamma.",
    ]


def test_same_parent_after_inserts_land_correctly_whatever_order_they_are_submitted_in():
    """Descending submission order was the undocumented workaround; it must stay correct,
    and ascending order must now agree with it — the result may not depend on batch order."""
    for order in (["a1", "b1", "g1"], ["g1", "b1", "a1"], ["b1", "g1", "a1"]):
        plan = dry_run([_insert_by_id(bid, MARKERS[bid]) for bid in order], _seed_tree())
        opener = _seed_opener()
        apply(plan, _client(opener), "doc453")
        assert opener.order() == [
            "Section One", "Alpha body paragraph.", "MARKER-1 belongs after Alpha.",
            "Section Two", "Beta body paragraph.", "MARKER-2 belongs after Beta.",
            "Section Three", "Gamma body paragraph.", "MARKER-3 belongs after Gamma.",
        ], f"submission order {order} changed the document"


# --------------------------------------------------------------------------- #
# AC2.2 — APPEND_INTO preserves authored order (the triage's first corollary)    #
# --------------------------------------------------------------------------- #

def test_two_append_into_inserts_into_one_parent_preserve_authored_order():
    """`resolve.py` freezes ``index=_child_count(node)`` at plan time, so pre-fix both
    entries targeted the same index and the SECOND landed before the first."""
    tree = _page(_heading("h1", "Section One", children=[_para("c1", "existing child")]))
    plan = dry_run(
        [
            _insert_by_id("h1", "appended first", InsertPosition.APPEND_INTO),
            _insert_by_id("h1", "appended second", InsertPosition.APPEND_INTO),
        ],
        tree,
    )
    assert plan.refusals == ()

    opener = LiveTreeOpener(
        children={"root": ["h1"], "h1": ["c1"]},
        texts={"h1": "Section One", "c1": "existing child"},
        block_types={"h1": 3},
    )
    apply(plan, _client(opener), "doc453")

    assert opener.order("h1") == ["existing child", "appended first", "appended second"]


# --------------------------------------------------------------------------- #
# AC2.3 — a delete earlier in the batch shifts a later same-parent insert        #
# --------------------------------------------------------------------------- #

def test_delete_then_insert_in_the_same_parent_puts_the_insert_where_the_plan_showed_it():
    """Delete already resolves its index off the LIVE parent, so it removes a child the
    later insert's frozen ordinal still counted — pre-fix the insert landed one late."""
    plan = dry_run(
        [
            DeleteRequest(target=AnchorById(block_id="s1")),
            _insert_by_id("b1", "MARKER-2 belongs after Beta."),
        ],
        _seed_tree(),
    )
    assert plan.refusals == ()

    opener = _seed_opener()
    apply(plan, _client(opener), "doc453")

    assert opener.order() == [
        "Alpha body paragraph.",
        "Section Two",
        "Beta body paragraph.",
        "MARKER-2 belongs after Beta.",
        "Section Three",
        "Gamma body paragraph.",
    ]


# --------------------------------------------------------------------------- #
# AC2.4 — the CONTROL: one insert per batch is untouched by the fix              #
# AC2.5 (optional) — different parents never interfere                           #
# --------------------------------------------------------------------------- #

def test_one_insert_per_batch_control_is_unmoved_by_the_fix():
    """The capture's `control` block: the identical three inserts, one per batch with a
    fresh read between, were always correct and must stay so, position for position."""
    opener = _seed_opener()
    for bid, text in MARKERS.items():
        tree = _page(*[
            _para(child, opener.texts[child]) for child in opener.children["root"]
        ])
        plan = dry_run([_insert_by_id(bid, text)], tree)
        apply(plan, _client(opener), "doc453")

    assert opener.order() == [
        "Section One", "Alpha body paragraph.", "MARKER-1 belongs after Alpha.",
        "Section Two", "Beta body paragraph.", "MARKER-2 belongs after Beta.",
        "Section Three", "Gamma body paragraph.", "MARKER-3 belongs after Gamma.",
    ]


def test_inserts_into_different_parents_do_not_interfere():
    """The index is per-parent: a batch spanning two parents drifts within neither."""
    tree = _page(
        _heading("h1", "First", children=[_para("c1", "one"), _para("c2", "two")]),
        _heading("h2", "Second", children=[_para("d1", "three")]),
    )
    plan = dry_run(
        [
            _insert_by_id("c1", "after one"),
            _insert_by_id("d1", "after three"),
            _insert_by_id("c2", "after two"),
        ],
        tree,
    )
    opener = LiveTreeOpener(
        children={"root": ["h1", "h2"], "h1": ["c1", "c2"], "h2": ["d1"]},
        texts={"h1": "First", "h2": "Second", "c1": "one", "c2": "two", "d1": "three"},
        block_types={"h1": 3, "h2": 3},
    )
    apply(plan, _client(opener), "doc453")

    assert opener.order("h1") == ["one", "after one", "two", "after two"]
    assert opener.order("h2") == ["three", "after three"]


# --------------------------------------------------------------------------- #
# AC4 — the plan preview is TRUE: what the plan described is what the document    #
# holds afterwards. Pinned as a property over the plan itself, not as a side      #
# effect of the four cases above.                                                #
# --------------------------------------------------------------------------- #

def test_every_resolved_insert_lands_where_its_plan_entry_said_relative_to_its_reference():
    """The plan's commitment is **positional relative to the reference block** — ``position``
    + the reference ``block_id`` — and this property reads that commitment straight off the
    plan and checks the post-apply tree against it, entry by entry.

    ``insertion_point.index`` is deliberately NOT asserted to be the final ordinal: it is the
    plan-time ordinal of the pre-batch snapshot, and for a multi-entry batch it cannot be both
    that and the landing position (making it so would require sequential re-planning, which
    LD-453 § Out of scope rejects). It is documented as advisory on
    :class:`~larkdocio.write.resolve.ResolvedInsertion`; the guarantee lives here.
    """
    requests = [_insert_by_id(bid, text) for bid, text in MARKERS.items()]
    plan = dry_run(requests, _seed_tree())
    opener = _seed_opener()
    log = apply(plan, _client(opener), "doc453")

    inserts = [entry for entry in plan.entries if entry.op == "insert"]
    for entry, applied in zip(inserts, log.entries):
        created = applied.created_block_ids[0]
        parent = entry.insertion_point.parent_block_id
        assert entry.position == "after"
        assert opener.index_of(created, parent) == opener.index_of(entry.block_id, parent) + 1


def test_append_into_lands_inside_the_parent_the_plan_named():
    tree = _page(_heading("h1", "Section One", children=[_para("c1", "existing child")]))
    plan = dry_run(
        [_insert_by_id("h1", "appended", InsertPosition.APPEND_INTO)], tree
    )
    opener = LiveTreeOpener(
        children={"root": ["h1"], "h1": ["c1"]},
        texts={"h1": "Section One", "c1": "existing child"},
        block_types={"h1": 3},
    )
    log = apply(plan, _client(opener), "doc453")

    entry = plan.entries[0]
    assert entry.insertion_point.parent_block_id == "h1"
    assert opener.children["h1"][-1] == log.entries[0].created_block_ids[0]
