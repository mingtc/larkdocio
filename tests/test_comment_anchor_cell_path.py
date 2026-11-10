"""The THIRD edit path and inline review anchors — a whole-CELL (table) edit.

The gap this file closes
------------------------
Two docx edit paths were made honest about a reviewer's **inline** comment anchors: the
**sub-span** path re-emits each rebuilt run's anchors, and the **whole-block** path
**refuses** (``comment-anchors-present``) rather than collapse them away. A **table-cell**
edit is a third path with the same shape and, until now, neither half:

* it patches the target cell's **inner text block** with the **same** collapsing builder
  (:func:`~larkdocio.write.apply.build_whole_paragraph_update`), so an anchor inside that
  cell left the emitted body;
* its anchor is a :class:`~larkdocio.write.model.TableLocator`, resolved by
  ``_resolve_table``, which carried **no** plan-time inline-anchor precondition — the
  whole-block precondition sits on the narrative/by-id arm only.

So the loss was **silent** on this path: no refusal, no note, nothing in the plan or the
apply-log.

What was NOT wrong, and why it matters here
-------------------------------------------
The collapsing builder **strips** ``comment_ids`` from its collapsed run, so this path's
emitted body was byte-identical to what shipped — a **drop**, never a *relocation* of the
leading run's anchor onto the whole rewritten cell. That variant was rejected on the record
(a comment that moves to different text misreports what a reviewer objected to), so the gap
was a **missing refusal** and never a corruption. The builder is therefore left exactly as
it is and the refusal goes **upstream** of it, at plan time
(:func:`~larkdocio.write.resolve._resolve_whole_cell_edit`).

The shape of the fix
--------------------
* **Refuse, not carry** — a whole-cell edit is *by definition* a collapse, so there is
  nowhere honest to put a per-passage anchor. Same answer as the whole-block path.
* **The existing reason, reused** — ``comment-anchors-present``: the same failure in kind
  deserves one vocabulary, and a caller already switching on it needs no new branch.
* **A cell-shaped ``detail``** — it names the **row and column** (a cell is not addressed by
  a block id), the **inner text block** the patch would have rewritten, and the recovery a
  ``TableLocator`` cannot express: a **sub-span** edit anchored **by that inner block's id**.
* **The narrowest possible subject** — only the anchors on the block the patch actually
  rewrites may refuse. Anchors on the row's key cell (read for row identity, never
  patched), on a sibling paragraph deeper in the same cell, on another cell, or at
  **block** level are all untouched by the rebuild, so refusing on them would be a false
  refusal on a shipped path.

What the server does with what we send (the evidence the refusal rests on,
``dev/comments-probe-round2-2026-07-29.md`` § Q6): a patch that omits the ids leaves the
anchor **orphaned**, and no later call can re-attach it. Preservation has to happen in the
patch that does the edit or not at all — which is why a path that structurally cannot carry
the ids must refuse rather than proceed-and-apologize.
"""
import json
import pathlib

import pytest

from log_reading_apply import reading_the_log
from larkdocio.model import StyledText, Text, TableCellNode, TextNode
from larkdocio.write.apply import apply, build_whole_paragraph_update
apply = reading_the_log(apply)
from larkdocio.write.model import (
    AnchorById,
    RefusalReason,
    SubSpanEditRequest,
)
from larkdocio.write.preview import dry_run
from larkdocio.write.resolve import _first_text_block, resolve

from write_harness import (
    StubOpener,
    _block_payload,
    _cell,
    _client,
    _page,
    _para,
    _patch_ok,
    _req,
    _run,
    _treq,
)

ID_A = "7667754726531878624"
ID_B = "7667754726531878625"


# --------------------------------------------------------------------------- #
# Builders — a cell whose INNER text block carries WORD-level anchors            #
# (the shared `_cell` builds the plain shape; these are its anchored variants)   #
# --------------------------------------------------------------------------- #

def _anchored_cell(bid, *runs, inner_block_ids=None, cell_block_ids=None, extra=()):
    """A :class:`TableCellNode` whose inner text block's runs carry word-level anchors.

    ``runs`` are ``(text, comment_ids)`` pairs — ``None`` builds a plain :class:`Text` (a run
    with no ``text_element_style`` at all), anything else a :class:`StyledText` carrying that
    list verbatim. ``inner_block_ids`` / ``cell_block_ids`` are the **block**-level lists on
    the inner text block and on the cell itself — a different granularity and a different
    question. ``extra`` are further ``(block_id, text, comment_ids)`` paragraphs appended
    **after** the patched one inside the same cell.
    """
    inlines = [Text(t) if ids is None else StyledText(t, comment_ids=ids) for (t, ids) in runs]
    children = [TextNode(content=inlines, block_id=f"{bid}__t", comment_ids=inner_block_ids)]
    for (eid, text, ids) in extra:
        children.append(TextNode(
            content=[Text(text) if ids is None else StyledText(text, comment_ids=ids)],
            block_id=eid,
        ))
    return TableCellNode(children=children, block_id=bid, comment_ids=cell_block_ids)


def _table_of(*cells, col_size=3, header_row=True, merges=None, bid="t5"):
    from larkdocio.model import TableNode
    return TableNode(cells=list(cells), col_size=col_size, header_row=header_row,
                     merges=list(merges or []), block_id=bid)


#: The shipped-shape table: a header row plus one data row whose Q3 cell is the target.
def _tree(target_cell, *, key_cell=None, q2_cell=None):
    return _page(_table_of(
        _cell("h0", "Metric"), _cell("h1", "Q2"), _cell("h2", "Q3"),
        key_cell or _cell("r1k", "On-time delivery"),
        q2_cell or _cell("r1a", "95.0%"),
        target_cell,
    ))


def _anchored_tree(*runs, **kwargs):
    return _tree(_anchored_cell("r1b", *runs, **kwargs))


def _plan(tree, replacement="99.9%"):
    return dry_run([_treq("On-time delivery", column_index=2, replacement=replacement)], tree)


def _entry(tree, replacement="99.9%"):
    (entry,) = _plan(tree, replacement).entries
    return entry


# --------------------------------------------------------------------------- #
# 1. THE REFUSAL — the third path stops being silent                            #
# --------------------------------------------------------------------------- #

def test_a_whole_CELL_edit_on_an_inline_anchored_cell_REFUSES():
    """The bug, inverted: the entry used to resolve and drop the anchor on apply."""
    entry = _entry(_anchored_tree(("97.2%", [ID_A])))
    assert not entry.is_resolved, entry.to_dict()
    assert entry.refusal.reason is RefusalReason.COMMENT_ANCHORS_PRESENT


def test_the_cell_refusal_REUSES_the_existing_reason_and_mints_no_new_member():
    """One vocabulary for one failure in kind: a caller already branching on
    ``comment-anchors-present`` needs no new branch, and no existing reason's meaning moved."""
    assert {r.name: r.value for r in RefusalReason} == {
        "AMBIGUOUS": "ambiguous-N-candidates",
        "NOT_FOUND": "not-found",
        "WRITE_HOSTILE": "write-hostile-target",
        "STALE_ANCHOR": "stale-anchor",
        "COLUMN_NOT_FOUND": "column-not-found",
        "CANNOT_HOLD_CHILDREN": "cannot-hold-children",
        "CANNOT_HOLD_SIBLINGS": "cannot-hold-siblings",
        "SPAN_NOT_SPLITTABLE": "span-not-splittable",
        "MERGE_NOT_EXPRESSIBLE": "merge-not-expressible",
        # LD-574 — the compiled-no-op refusal. Added, never renamed: every
        # existing member above keeps its own wire value byte for byte.
        "CHANGE_NOT_EXPRESSIBLE": "change-not-expressible",
        # LD-575 — the table-grow boundary. Added, never renamed: every existing member above
        # and below keeps its own wire value byte for byte.
        "TABLE_GROW_UNSUPPORTED": "table-grow-unsupported",
        "NOT_IN_DIALECT": "not-in-dialect",
        "STALE_DOCUMENT": "stale-document",
        "COMMENT_ANCHORS_PRESENT": "comment-anchors-present",
        # The comment WRITE ops' three (LD-202). Listed rather than tolerated, so this stays
        # a closed set: a new member costs a deliberate edit here, which is the whole point.
        # Note what they are NOT — none of them re-uses or re-points a value above.
        "COMMENT_ANCHOR_NOT_CREATABLE": "comment-anchor-not-creatable",
        "COMMENT_SURFACE_UNSUPPORTED": "comment-surface-unsupported",
        "COMMENT_THREAD_NOT_SOLELY_AUTHORED": "comment-thread-not-solely-authored",
        # The reconciler's eight (LD-233) — likewise listed by hand. Each is a fact about
        # an EDITED PROJECTION coming back in, not about an anchor resolving in a
        # document, and none of them re-uses or re-points a value above.
        "MARKER_INVENTED": "marker-invented",
        "MARKER_DUPLICATED": "marker-duplicated",
        "MARKER_ABSENT": "marker-absent",
        # The four that complete the loss taxonomy (LD-235) — added deliberately, same
        # note: no reason above changed its name or its value, and `marker-absent` still
        # means exactly what it meant (marker AND content both gone). `marker-dropped` is
        # the strictly narrower case it could not previously tell apart.
        "MARKER_DROPPED": "marker-dropped",
        "MARKER_RELOCATED": "marker-relocated",
        "MARKER_MANGLED": "marker-mangled",
        "MARKER_ORPHANED": "marker-orphaned",
        "MARKER_ORDER_CHANGED": "marker-order-changed",
        "BLOCK_TYPE_MUTATION": "block-type-mutation",
        "SEGMENT_AMBIGUOUS": "segment-ambiguous",
        "UNMARKED_CONTENT_CHANGED": "unmarked-content-changed",
        "UNDECODABLE_TEXT": "undecodable-text",
        # The twelfth taxonomy row, ruled in later (LD-235, fixing LD-238): a plan that
        # conserves a block must never ALSO plan that block's own content as new. Same
        # note again — no reason above changed its name or its value.
        "CONSERVED_BLOCK_RE_CREATED": "conserved-block-re-created",
        # LD-643 — the APPLY-TIME disposition family. Added at the tail, never renamed: every
        # existing member above keeps its own wire value byte for byte, and none of these
        # re-uses or re-points one. Seven of the eight are deliberately the SAME wire values
        # the sheets and Base engines publish, so one condition does not get two names across
        # two engines; `pagination-unterminated` is this surface's own.
        "API_ERROR": "api-error",
        "PERMISSION_DENIED": "permission-denied",
        "RATE_LIMITED": "rate-limited",
        "TRANSPORT_FAILURE": "transport-failure",
        "PAGINATION_UNTERMINATED": "pagination-unterminated",
        "UNEXPECTED_ERROR": "unexpected-error",
        "UNVERIFIED_WRITE": "unverified-write",
        "NOT_ATTEMPTED": "not-attempted",
    }


def test_the_cell_refusal_detail_names_the_ROW_and_the_COLUMN_not_just_a_block_id():
    """A cell is not addressed by a block id, so a detail that names only one is unusable:
    the consumer wrote a row key and a column, and that is what they must read back."""
    detail = _entry(_anchored_tree(("97.2%", [ID_A]))).refusal.detail
    assert "On-time delivery" in detail, detail        # the row, as the consumer named it
    assert "Q3" in detail, detail                      # the column's header label
    assert "row 1" in detail and "column 2" in detail, detail
    assert "t5" in detail, detail                      # the table
    assert "r1b__t" in detail, detail                  # the inner block the patch rewrites
    assert ID_A in detail, detail                      # the anchor in the way


def test_the_cell_refusal_detail_names_WHY_and_THE_RECOVERY_THAT_WORKS():
    """The house standard — a paragraph a consumer could paste to another user: what is in the
    way, why this path cannot honor it, and the path that can. The recovery is **not** the
    same sentence the whole-block refusal prints: a ``TableLocator`` cannot express a span, so
    the sub-span edit has to be anchored by the inner block's **id**."""
    detail = _entry(_anchored_tree(("97.2%", [ID_A]))).refusal.detail
    lowered = detail.lower()
    assert "comment" in lowered, detail                                  # WHAT
    assert "one run" in lowered or "single run" in lowered, detail        # WHY
    assert "sub-span" in lowered, detail                                 # the RECOVERY
    assert "anchorbyid" in lowered, detail                               # ...how to aim it
    assert len(detail.split()) >= 40, f"too terse for the house standard: {detail}"


def test_the_cell_refusal_names_the_recovery_the_engine_ACTUALLY_HAS():
    """The recovery a detail names must work. The identical cell, sub-span-edited by the inner
    block's id, resolves — so the paragraph is not sending a consumer somewhere that also
    refuses."""
    tree = _anchored_tree(("Q3 came in at ", None), ("97.2%", [ID_A]))
    plan = dry_run(
        [SubSpanEditRequest(anchor=AnchorById(block_id="r1b__t"), span="97.2%",
                            replacement="99.9%")],
        tree,
    )
    assert plan.entries[0].is_resolved, plan.entries[0].to_dict()


def test_the_cell_refusal_detail_carries_NO_internal_dialect():
    """It is a shipped consumer-facing string."""
    import consumer_text
    detail = _entry(_anchored_tree(("97.2%", [ID_A]))).refusal.detail
    assert not consumer_text.dialect_hits(detail), detail


def test_the_cell_refusal_survives_the_plan_wire_format():
    entry = _entry(_anchored_tree(("97.2%", [ID_A])))
    wire = json.loads(json.dumps(entry.to_dict()))
    assert wire["refusal"]["reason"] == "comment-anchors-present"
    assert wire["refusal"]["detail"] == entry.refusal.detail
    assert wire.get("cell") is None and wire.get("block_id") is None


def test_the_refused_cell_entry_carries_no_cell_context_like_every_other_refusal():
    entry = _entry(_anchored_tree(("97.2%", [ID_A])))
    assert entry.cell is None and entry.block_id is None and entry.before is None


def test_SEVERAL_ids_and_SEVERAL_anchored_runs_are_all_named_verbatim():
    """The ids are the document's data, not ours to normalize: the detail names them in the
    API's own run order, with **no sort and no de-duplication** — the same rule the model
    keeps. One reviewer anchored across two runs really does appear twice, and saying "2" when
    the document says three anchor entries would be a quieter kind of lie."""
    detail = _entry(_anchored_tree(
        ("97.2", [ID_B, ID_A]), ("%", [ID_A]))).refusal.detail
    assert "3 inline comment anchors" in detail, detail
    assert f"({ID_B}, {ID_A}, {ID_A})" in detail, detail


def test_a_SINGLE_anchor_is_counted_in_the_SINGULAR():
    detail = _entry(_anchored_tree(("97.2%", [ID_A]))).refusal.detail
    assert "1 inline comment anchor (" in detail, detail


# --------------------------------------------------------------------------- #
# 2. PRE-I/O — the refusal is a PLAN fact, and it costs no write                 #
# --------------------------------------------------------------------------- #

def test_the_cell_refusal_is_decided_at_PLAN_time_before_any_client_exists():
    """``dry_run`` takes no client and opens no socket — the anchors are already on the tree
    the consumer read, so this cannot be a write-time discovery."""
    assert not _entry(_anchored_tree(("97.2%", [ID_A]))).is_resolved


def test_a_batch_holding_only_an_anchored_CELL_edit_issues_ZERO_writes():
    """A call-count spy that would raise on contact: the double re-validation this path
    normally performs never happens either, so not even a GET leaks."""
    plan = _plan(_anchored_tree(("97.2%", [ID_A])))
    opener = StubOpener([])                     # any request at all would IndexError
    log = apply(plan, _client(opener), "doc123")
    assert opener.requests == []
    assert log.entries[0].refusal.reason is RefusalReason.COMMENT_ANCHORS_PRESENT


def test_a_MIXED_batch_writes_nothing_for_the_refused_CELL_entry():
    """The refused entry contributes zero writes and its neighbours still apply — the
    per-entry semantics every docx reason except the document-wide compare-and-swap has."""
    tree = _page(
        _table_of(
            _cell("h0", "Metric"), _cell("h1", "Q2"), _cell("h2", "Q3"),
            _cell("r1k", "On-time delivery"), _cell("r1a", "95.0%"),
            _anchored_cell("r1b", ("97.2%", [ID_A])),
        ),
        _para("p2", "plain text here"),
    )
    plan = dry_run(
        [_treq("On-time delivery", column_index=2, replacement="99.9%"),
         _req("plain text", replacement="NEW B")],
        tree,
    )
    opener = StubOpener([_block_payload("p2", [_run("plain text here")]), _patch_ok()])
    log = apply(plan, _client(opener), "doc123")

    assert log.entries[0].refusal.reason is RefusalReason.COMMENT_ANCHORS_PRESENT
    assert log.entries[1].outcome == "applied"
    assert [r["method"] for r in opener.requests] == ["GET", "PATCH"]
    assert "blocks/p2" in opener.requests[0]["url"]


# --------------------------------------------------------------------------- #
# 3. NO FALSE REFUSALS — the common path is byte-identical to what shipped       #
# --------------------------------------------------------------------------- #

def test_an_UNANCHORED_cell_edit_plans_exactly_as_it_always_did():
    entry = _entry(_tree(_cell("r1b", "97.2%")))
    assert entry.is_resolved, entry.to_dict()
    assert entry.block_id == "r1b"
    assert entry.before == "97.2%" and entry.after == "99.9%"
    assert (entry.cell.row, entry.cell.column) == (1, 2)
    assert entry.cell.target_text_block_id == "r1b__t"
    assert entry.cell.key_text_block_id == "r1k__t"


def test_an_UNANCHORED_cell_edit_emits_a_BYTE_IDENTICAL_patch_body():
    """The golden-style pin on the common path: the body, the URL and the request sequence
    are what the cell path has always emitted."""
    plan = _plan(_tree(_cell("r1b", "97.2%")))
    opener = StubOpener([
        _block_payload("r1k__t", [_run("On-time delivery")]),
        _block_payload("r1b__t", [_run("97.2%", bold=True)]),
        _patch_ok(),
    ])
    log = apply(plan, _client(opener), "doc123")
    assert [r["method"] for r in opener.requests] == ["GET", "GET", "PATCH"]
    patch = opener.requests[2]
    assert "/blocks/r1b__t" in patch["url"]
    assert patch["body"] == {"update_text_elements": {"elements": [
        {"text_run": {"content": "99.9%", "text_element_style": {"bold": True}}}
    ]}}
    assert log.entries[0].outcome == "applied"


@pytest.mark.parametrize("ids,refuses", [
    (None, False),   # the field is ABSENT on the run — nothing is anchored
    ([], False),     # PRESENT BUT EMPTY — the API said nothing is anchored here
    ([ID_A], True),  # populated — a reviewer really is anchored inside this cell
])
def test_absent_and_empty_both_mean_PROCEED_on_the_cell_path_too(ids, refuses):
    entry = _entry(_anchored_tree(("97.2%", ids)))
    assert (not entry.is_resolved) is refuses, entry.to_dict()
    if not refuses:
        assert entry.block_id == "r1b"


def test_a_BLOCK_LEVEL_anchor_on_the_cells_INNER_BLOCK_proceeds():
    """The rebuild replaces the block's *elements*; the block's own comment list is not part
    of the patch body, so refusing on it would be a false refusal."""
    entry = _entry(_anchored_tree(("97.2%", None), inner_block_ids=[ID_A]))
    assert entry.is_resolved, entry.to_dict()


def test_a_BLOCK_LEVEL_anchor_on_the_CELL_ITSELF_proceeds():
    entry = _entry(_anchored_tree(("97.2%", None), cell_block_ids=[ID_A]))
    assert entry.is_resolved, entry.to_dict()


def test_BOTH_granularities_together_still_refuse_and_name_the_WORD_level_ids():
    entry = _entry(_anchored_tree(
        ("97.2%", [ID_A]), inner_block_ids=[ID_B], cell_block_ids=[ID_B]))
    assert not entry.is_resolved
    assert ID_A in entry.refusal.detail and ID_B not in entry.refusal.detail


def test_an_anchor_on_the_rows_KEY_cell_proceeds():
    """The key cell is **read** for row identity and never patched, so its anchors are not in
    danger from this edit."""
    entry = _entry(_tree(
        _cell("r1b", "97.2%"),
        key_cell=_anchored_cell("r1k", ("On-time delivery", [ID_A])),
    ))
    assert entry.is_resolved, entry.to_dict()


def test_an_anchor_in_a_DIFFERENT_cell_of_the_same_row_proceeds():
    entry = _entry(_tree(
        _cell("r1b", "97.2%"),
        q2_cell=_anchored_cell("r1a", ("95.0%", [ID_A])),
    ))
    assert entry.is_resolved, entry.to_dict()


def test_an_anchor_on_a_SIBLING_paragraph_the_patch_never_touches_proceeds():
    """A multi-paragraph cell: the whole-cell patch rewrites the **first** text-bearing block
    only, so an anchor on a later paragraph in the same cell survives the edit untouched.
    Refusing on it would block an edit that loses nothing."""
    entry = _entry(_anchored_tree(
        ("97.2%", None), extra=[("r1b__t2", "footnote text", [ID_A])]))
    assert entry.is_resolved, entry.to_dict()
    assert entry.cell.target_text_block_id == "r1b__t"


# --------------------------------------------------------------------------- #
# 4. ORDERING — the new precondition shadows no pre-existing refusal            #
# --------------------------------------------------------------------------- #

def test_a_MERGED_anchored_cell_still_refuses_WRITE_HOSTILE():
    """The structural refusals are decided first: a merged target is refused for being
    merged, which is the answer the consumer has always had for it."""
    tree = _page(_table_of(
        _cell("h0", "Metric"), _cell("h1", "Q2"), _cell("h2", "Q3"),
        _cell("r1k", "On-time delivery"),
        _anchored_cell("r1a", ("10ms", [ID_A])),
        _cell("r1b", "10ms"),
        merges=[(1, 1), (1, 1), (1, 1), (1, 1), (1, 2), (1, 1)],
    ))
    (entry,) = dry_run(
        [_treq("On-time delivery", column_index=1, replacement="9ms")], tree).entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.WRITE_HOSTILE


def test_an_AMBIGUOUS_row_still_refuses_AMBIGUOUS_even_when_anchored():
    tree = _page(_table_of(
        _cell("h0", "Metric"), _cell("h1", "Val"),
        _cell("k1", "Churn"), _anchored_cell("v1", ("5%", [ID_A])),
        _cell("k2", "Churn"), _anchored_cell("v2", ("6%", [ID_B])),
        col_size=2,
    ))
    (entry,) = dry_run([_treq("Churn", column_index=1)], tree).entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.AMBIGUOUS
    assert "matched 2 rows" in entry.refusal.detail, entry.refusal.detail


def test_a_COLUMN_NOT_FOUND_still_wins_over_the_anchor_check():
    (entry,) = dry_run(
        [_treq("On-time delivery", column_index=9)],
        _anchored_tree(("97.2%", [ID_A])),
    ).entries
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.COLUMN_NOT_FOUND


def test_the_table_id_the_detail_names_is_found_by_IDENTITY_not_by_EQUALITY():
    """Two cells holding the same text and no ids compare **equal**, so an equality search
    would happily name the first table it found. The detail must name the table the target is
    actually in, or it sends a consumer to the wrong place."""
    from larkdocio.write.resolve import _enclosing_table_id
    decoy = _table_of(
        _cell("d0", "Metric"), _cell("d1", "Q2"), _cell("d2", "Q3"),
        _cell("dk", "On-time delivery"), _cell("da", "95.0%"), _cell("db", "97.2%"),
        bid="decoy",
    )
    target = _anchored_cell("r1b", ("97.2%", [ID_A]))
    real = _table_of(
        _cell("h0", "Metric"), _cell("h1", "Q2"), _cell("h2", "Q3"),
        _cell("r1k", "On-time delivery"), _cell("r1a", "95.0%"), target,
        bid="real",
    )
    root = _page(decoy, real)
    # the decoy's plain 97.2% cell compares EQUAL to nothing here only because the target is
    # anchored — so pin the identity rule on a decoy cell that IS equal to a plain one instead
    assert _enclosing_table_id(root, real.cells[4]) == "real", "identity, not equality"
    assert _enclosing_table_id(root, decoy.cells[4]) == "decoy"
    assert _enclosing_table_id(root, target) == "real"
    # and a cell that is in no table at all yields None rather than raising
    assert _enclosing_table_id(root, _cell("orphan", "x")) is None


def test_the_resolver_ENTRY_POINT_carries_the_precondition_not_just_the_previewer():
    """``resolve`` is public surface of its own; the precondition must live on the path both
    it and ``dry_run`` share, not be bolted onto the preview layer."""
    from larkdocio.write.model import Refusal
    result = resolve(
        _treq("On-time delivery", column_index=2), _anchored_tree(("97.2%", [ID_A])))
    assert isinstance(result, Refusal)
    assert result.reason is RefusalReason.COMMENT_ANCHORS_PRESENT


# --------------------------------------------------------------------------- #
# 5. THE COLLAPSING BUILDER IS UNTOUCHED — a drop, never a relocation           #
# --------------------------------------------------------------------------- #

def test_the_collapsing_builder_STILL_never_carries_an_anchor_onto_the_collapsed_run():
    """Supersedes the characterization this path used to be pinned by. The builder is shared
    with the whole-block path and must stay a **drop**: carrying the leading run's anchor onto
    the rewritten cell would move a reviewer's comment onto text they never commented on,
    which is the variant that was rejected. The refusal above is what makes the drop
    unreachable through a plan, and this is what makes it harmless if it ever is reached."""
    live = [_run("97.2%", bold=True, comment_ids=[ID_A]), _run(" (est.)", comment_ids=[ID_B])]
    body = build_whole_paragraph_update(live, "REWRITTEN CELL")
    assert body == {"update_text_elements": {"elements": [
        {"text_run": {"content": "REWRITTEN CELL", "text_element_style": {"bold": True}}}
    ]}}
    assert "comment_ids" not in json.dumps(body)


# --------------------------------------------------------------------------- #
# 6. REAL PAYLOADS — the whole chain, off the harvest's own captured bytes       #
#                                                                              #
# No document in this repository has an anchored comment inside a table cell:    #
# every one of the harvest's seven anchored blocks is a top-level list item, and #
# no API call can create an anchored comment, so one cannot be provisioned.      #
# What CAN be real is the run shape — and it is the shape that matters, because  #
# Lark returns every style flag explicitly `false` beside the anchor, so the     #
# run's cleaned *style* is empty and the emitted style object is the anchor      #
# alone. These legs put a harvested block's VERBATIM elements in the cell        #
# position and drive real payload -> real SDK Block -> real parser -> real model  #
# -> real plan, rather than trusting a hand-authored inline.                     #
# --------------------------------------------------------------------------- #

_HARVEST = (pathlib.Path(__file__).resolve().parent.parent / "tests" / "captures"
            / "comments-probe-round2-captures" / "10-harvest-docx.json")


def _harvested_word_anchored() -> dict:
    blocks = {
        bid: rec
        for bid, rec in json.loads(_HARVEST.read_text(encoding="utf-8"))
        ["anchored_blocks"].items()
        if rec.get("word_level_anchors")
    }
    assert blocks, "the harvest carries no word-level anchored block — the capture moved"
    return blocks


_HARVESTED_IDS = sorted(_harvested_word_anchored())


def _real_elements(record) -> list:
    return record["block_verbatim"][record["comment_id_view"]["container_key"]]["elements"]


def _real_cell_payload(record) -> list:
    """A real 2x2 table payload whose target cell's inner text block holds ``record``'s own
    captured elements — the anchored run exactly as Lark returned it."""
    def cell(cid, inner_id, elements):
        return [
            {"block_id": cid, "parent_id": "tbl", "block_type": 32, "table_cell": {},
             "children": [inner_id]},
            {"block_id": inner_id, "parent_id": cid, "block_type": 2,
             "text": {"elements": elements}},
        ]

    def plain(text):
        return [{"text_run": {"content": text}}]

    return [
        {"block_id": "root", "parent_id": "doc", "block_type": 1,
         "page": {"elements": plain("Doc")}, "children": ["tbl"]},
        {"block_id": "tbl", "parent_id": "root", "block_type": 31,
         "table": {"property": {"row_size": 2, "column_size": 2}},
         "children": ["c00", "c01", "c10", "c11"]},
        *cell("c00", "c00t", plain("Metric")),
        *cell("c01", "c01t", plain("Q3")),
        *cell("c10", "c10t", plain("On-time delivery")),
        *cell("c11", "c11t", json.loads(json.dumps(_real_elements(record)))),
    ]


def _real_tree(record):
    from harness import build_blocks
    from larkdocio.read.config import Config
    from larkdocio.read.parser import Parser
    return Parser(Config()).parse_docx_tree(
        "root", build_blocks(_real_cell_payload(record)))


@pytest.mark.parametrize("block_id", _HARVESTED_IDS)
def test_a_REAL_anchored_run_in_a_CELL_reaches_the_model_at_the_word_level(block_id):
    """Provenance, executable: the parser really does put the harvested run's anchors on the
    cell's inner block, so the refusal below is reading the document's own data."""
    record = _harvested_word_anchored()[block_id]
    inner = _first_text_block(_real_tree(record).children[0].cells[3])
    runs = [x for x in inner.content if isinstance(x, StyledText) and x.comment_ids]
    assert runs, inner.content
    assert [i for run in runs for i in run.comment_ids] == list(
        record["word_level_anchors"])


@pytest.mark.parametrize("block_id", _HARVESTED_IDS)
def test_a_whole_CELL_edit_of_a_REAL_anchored_cell_refuses_with_its_REAL_ids(block_id):
    record = _harvested_word_anchored()[block_id]
    (entry,) = dry_run(
        [_treq("On-time delivery", column_index=1, replacement="REWRITTEN CELL")],
        _real_tree(record),
    ).entries
    assert entry.refusal.reason is RefusalReason.COMMENT_ANCHORS_PRESENT, entry.to_dict()
    for comment_id in record["word_level_anchors"]:
        assert comment_id in entry.refusal.detail
    assert "c11t" in entry.refusal.detail and "On-time delivery" in entry.refusal.detail


@pytest.mark.parametrize("block_id", _HARVESTED_IDS)
def test_the_by_id_sub_span_recovery_RESOLVES_on_the_same_real_cell(block_id):
    """The recovery has to work on the very cell that refused, or the detail is a lie — and it
    is a *different* recovery from the whole-block path's, because a locator cannot name a
    span."""
    record = _harvested_word_anchored()[block_id]
    span = record["plain_text"].strip().split(" ")[0]
    (entry,) = dry_run(
        [SubSpanEditRequest(anchor=AnchorById(block_id="c11t"), span=span,
                            replacement="X")],
        _real_tree(record),
    ).entries
    assert entry.is_resolved, entry.to_dict()


def test_the_refusal_on_every_REAL_anchored_cell_issues_ZERO_api_calls():
    """Pre-I/O over the whole harvested set at once, with an opener that raises on contact."""
    opener = StubOpener([])
    for block_id, record in _harvested_word_anchored().items():
        plan = dry_run(
            [_treq("On-time delivery", column_index=1, replacement="REWRITTEN")],
            _real_tree(record),
        )
        log = apply(plan, _client(opener), "doc-never-touched")
        assert log.entries[0].refusal.reason is RefusalReason.COMMENT_ANCHORS_PRESENT
    assert opener.requests == []


# --------------------------------------------------------------------------- #
# 7. THE SHIPPED SURFACES SAY SO — the disclosures name the third path          #
#    (the omission was the whole reason the drop stayed invisible)              #
# --------------------------------------------------------------------------- #

def test_the_shipped_guide_names_the_CELL_refusal_and_its_BY_ID_recovery():
    """A consumer aiming a locator at a commented cell reads the guide, not the source. The
    two-path prose that shipped before would have told them the refusal is about a *block*."""
    from larkdocio import guide
    lowered = guide(full=True).lower()
    window = lowered.split("comment-anchors-present", 1)[1][:2500]
    assert "cell" in window, window[:500]
    assert "anchorbyid" in window, window[:500]


def test_the_capability_registry_states_the_CELL_path_policy():
    from larkdocio import capabilities
    rows = " ".join(
        capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]
        ["editable_not_creatable"]).lower()
    assert "whole-cell" in rows, rows
    assert "tablelocator" in rows, rows
    assert "inner text block" in rows, rows


def test_the_cell_disclosures_are_dialect_free():
    import consumer_text
    from larkdocio import capabilities, guide

    strings = [row for row in
               capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"][
                   "editable_not_creatable"] if "comment" in row.lower()]
    strings.extend(line for line in guide(full=True).split("\n")
                   if "whole-cell" in line.lower() or "whole table cell" in line.lower())
    strings.append(_entry(_anchored_tree(("97.2%", [ID_A]))).refusal.detail)
    assert len(strings) >= 3, strings
    for text in strings:
        assert not consumer_text.dialect_hits(text), text
