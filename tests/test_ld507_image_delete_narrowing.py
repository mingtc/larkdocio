"""LD-507 — an authored image CAN be deleted, and the fence narrows for DELETE only.

**THE SUPERSESSION THIS FILE POLICES, in one paragraph.** ``WRITE_HOSTILE_NODE_TYPES``
(``larkdocio/write/resolve.py``) was cut from the write spike's finding that image /
board / embed / synced content **is not text-patchable**. That reason is TRUE and is
**preserved**: such a block carries no text of its own, so it can be neither edited nor
used as an insertion reference. It simply was never a statement about **DELETE**, which
patches no text — it removes a child range. LD-507 asked Lark's own route the question
once, honestly, and took the verdict from a **read-back** rather than the call's own
``code: 0``:

* ``POST …/documents/{doc}/blocks/{parent}/children/batch_delete`` against an **image
  block (27)** authored by ``put_image_in_document`` → accepted, and **gone**: the parent
  no longer lists it AND a direct ``get_block`` answers ``1770002 not found``;
* the **control** — the same route, the same parent table cell, the same run, against a
  **text block (2)** → also gone. So the answer belongs to the block type, not the harness.

Capture: ``tests/captures/ld507-image-block-delete/captures/001-image-block-delete.json`` (in the dev
repo), ``_outcome: ROUTE_DELETES_IMAGE_BLOCK``, 2026-08-19.

**So this file has three jobs, and the second is the one that matters most.**

1. **The narrowing is real** — a ``DeleteRequest`` anchored **by id** at an image resolves.
2. **THE PRESERVED HALF STILL HAS TEETH** — an image as an **edit target**, a **sub-span
   target** or an **insertion reference** still refuses ``write-hostile-target``, on both
   anchor kinds. These are the assertions to watch redden if anyone ever "simplifies" the
   narrowing into a blanket unfencing.
3. **THE SCOPE IS EXACTLY THE EVIDENCE (D-59)** — board (43), iframe (26), Base embed (18),
   Sheet embed (30), Base named-view (53) and both synced types (49/50) are **unmeasured,
   not refuted**, so their delete still refuses and the refusal SAYS "unmeasured".
"""
import json
import pathlib

import pytest

from larkdocio.model import (
    BitableNode,
    BoardNode,
    IframeNode,
    ImageNode,
    ReferenceBaseNode,
    ReferenceSyncedNode,
    SheetNode,
    SourceSyncedNode,
    Text,
    TextNode,
)
from larkdocio.write.apply import apply
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
)
from larkdocio.write.preview import dry_run
from larkdocio.write.resolve import (
    DELETE_MEASURED_NODE_TYPES,
    WRITE_HOSTILE_NODE_TYPES,
    ResolvedTarget,
    resolve,
)

from write_harness import LiveTreeOpener, _client, _page, _para

CAPTURE = (pathlib.Path(__file__).resolve().parent.parent
           / "tests" / "captures" / "ld507-image-block-delete" / "captures"
           / "001-image-block-delete.json")

#: The seven types the probe did NOT measure. They keep refusing every op, delete included.
UNMEASURED_HOSTILE_NODES = (
    BoardNode(block_id="brd", token="brd-tok"),
    IframeNode(url="https://embed.example/x", block_id="frame"),
    BitableNode(block_id="base", token="base-tok"),
    SheetNode(block_id="sheet", token="sheet-tok"),
    ReferenceBaseNode(block_id="refbase", token="rb-tok", view_id="v1"),
    SourceSyncedNode(content=[Text("synced origin")], block_id="syncsrc"),
    ReferenceSyncedNode(block_id="syncref", source_doc="d", source_block="b"),
)


def _tree(*extra):
    return _page(_para("p1", "Alpha body paragraph."), *extra)


def _image_tree(caption="revenue chart"):
    return _tree(ImageNode(block_id="img", token="tok", caption=caption))


# =========================================================================== #
# 1. THE NARROWING — the measured shape, by id, resolves                       #
# =========================================================================== #

def test_delete_of_an_image_by_id_resolves_because_the_route_was_measured():
    result = resolve(DeleteRequest(target=AnchorById(block_id="img")), _image_tree())
    assert isinstance(result, ResolvedTarget), getattr(result, "detail", result)
    assert result.block_id == "img"


def test_the_plan_previews_an_image_delete_rather_than_refusing_it():
    plan = dry_run([DeleteRequest(target=AnchorById(block_id="img"))], _image_tree())
    assert plan.refusals == ()
    assert [entry.block_id for entry in plan.entries] == ["img"]


def test_apply_really_issues_the_child_range_delete_for_an_image():
    """End to end against the live-document double: the plan applies, the image leaves the
    parent's ordered child list, and nothing else moves. The double answers the REAL image
    payload (no text container at all), so this is not proved against a fiction."""
    opener = LiveTreeOpener(
        children={"root": ["p1", "img", "p2"]},
        texts={"p1": "Alpha body paragraph.", "p2": "Beta body paragraph."},
        block_types={"img": 27},
    )
    tree = _page(_para("p1", "Alpha body paragraph."),
                 ImageNode(block_id="img", token="tok"),
                 _para("p2", "Beta body paragraph."))
    plan = dry_run([DeleteRequest(target=AnchorById(block_id="img"))], tree)
    assert plan.refusals == ()

    log = apply(plan, _client(opener), "doc507")

    assert opener.children["root"] == ["p1", "p2"]
    assert opener.of("DELETE", "children/batch_delete"), "no batch_delete was issued"
    assert [entry.block_id for entry in log.entries] == ["img"]
    assert log.refusals == ()
    # LD-528: and the entry this delete leaves behind is the ONLY record of what was
    # destroyed, so it has to carry the picture — this file's own delete was one assertion
    # away from showing it empty. The full contract lives in
    # tests/test_ld528_image_delete_undo_record.py.
    assert log.entries[0].removed_payload["image"]["token"] == "tok-img", (
        log.entries[0].removed_payload)


def test_an_uncaptioned_image_deletes_too_because_the_precondition_is_the_empty_string():
    """The shape ``put_image_in_document`` actually creates carries no caption at all. Its
    by-id compare-and-swap is ``'' == ''`` — which is why the id route works end to end and
    the quote route could never have."""
    opener = LiveTreeOpener(children={"root": ["img"]}, texts={},
                            block_types={"img": 27})
    plan = dry_run([DeleteRequest(target=AnchorById(block_id="img"))],
                   _page(ImageNode(block_id="img", token="tok")))
    assert plan.refusals == ()
    log = apply(plan, _client(opener), "doc507")
    assert opener.children["root"] == []
    assert log.refusals == ()


# =========================================================================== #
# 2. THE PRESERVED HALF — un-patchable and un-anchorable, STILL ENFORCED       #
#    (these are the teeth; watch them redden before believing them)            #
# =========================================================================== #

@pytest.mark.parametrize("anchor", [
    pytest.param(AnchorById(block_id="img"), id="by-id"),
    pytest.param(Anchor(quote="revenue chart"), id="by-quote"),
])
def test_an_image_is_still_refused_as_an_EDIT_target(anchor):
    result = resolve(EditRequest(anchor=anchor, replacement="X"), _image_tree())
    assert result.reason is RefusalReason.WRITE_HOSTILE
    assert "img" in result.detail


@pytest.mark.parametrize("anchor", [
    pytest.param(AnchorById(block_id="img"), id="by-id"),
    pytest.param(Anchor(quote="revenue chart"), id="by-quote"),
])
def test_an_image_is_still_refused_as_an_INSERTION_REFERENCE(anchor):
    result = resolve(
        InsertRequest(reference=anchor, position=InsertPosition.AFTER,
                      content=(NewParagraph("x"),)),
        _image_tree())
    assert result.reason is RefusalReason.WRITE_HOSTILE


def test_an_image_is_still_refused_as_a_SUB_SPAN_target():
    result = resolve(
        SubSpanEditRequest(anchor=AnchorById(block_id="img"),
                           span="revenue", replacement="X"),
        _image_tree())
    assert result.reason is RefusalReason.WRITE_HOSTILE


def test_a_quote_anchored_image_DELETE_still_refuses_and_names_the_route_that_works():
    """Not an oversight — the *un-anchorable* half doing its job. An image's only quotable
    text is its caption, which lives nowhere in the live block's ``text_run`` elements, so
    the delete path's apply-time precondition (*the quote must still be a substring of the
    live text*) can never hold. Planning it would ship a plan that always refuses
    ``stale-anchor`` at write time, so the refusal happens early and names ``AnchorById``."""
    result = resolve(DeleteRequest(target=Anchor(quote="revenue chart")), _image_tree())
    assert result.reason is RefusalReason.WRITE_HOSTILE
    assert "AnchorById" in result.detail
    assert "img" in result.detail


# =========================================================================== #
# 3. THE SCOPE IS THE EVIDENCE (D-59) — seven types unmeasured, not refuted    #
# =========================================================================== #

@pytest.mark.parametrize("node", UNMEASURED_HOSTILE_NODES,
                         ids=lambda n: type(n).__name__)
def test_every_unmeasured_hostile_type_still_refuses_DELETE(node):
    result = resolve(DeleteRequest(target=AnchorById(block_id=node.block_id)),
                     _tree(node))
    assert result.reason is RefusalReason.WRITE_HOSTILE
    assert node.block_id in result.detail


@pytest.mark.parametrize("node", UNMEASURED_HOSTILE_NODES,
                         ids=lambda n: type(n).__name__)
def test_the_unmeasured_refusal_says_UNMEASURED_rather_than_claiming_it_cannot(node):
    """A negative claim may not exceed its evidence: nothing here says their delete FAILS,
    only that nobody asked."""
    detail = resolve(DeleteRequest(target=AnchorById(block_id=node.block_id)),
                     _tree(node)).detail
    assert "UNMEASURED, NOT REFUTED" in detail


def test_the_measured_set_is_exactly_one_type_and_is_a_subset_of_the_fence():
    """The narrowing is exactly as wide as its evidence. Widening this tuple needs its own
    measurement, not an analogy — and this assertion is what makes that a deliberate act."""
    assert DELETE_MEASURED_NODE_TYPES == (ImageNode,)
    assert set(DELETE_MEASURED_NODE_TYPES) < set(WRITE_HOSTILE_NODE_TYPES)


def test_the_fence_itself_is_unchanged_all_eight_types_still_listed():
    """The conclusion narrowed for ONE op; the list did not lose a member."""
    assert len(WRITE_HOSTILE_NODE_TYPES) == 8
    assert ImageNode in WRITE_HOSTILE_NODE_TYPES


# =========================================================================== #
# 4. THE MEASUREMENT ITSELF IS PINNED — so a re-measure that disagrees is loud #
# =========================================================================== #

def test_the_committed_capture_still_carries_the_measurement_this_narrowing_rests_on():
    """If a future run of the probe answers differently, or the capture is edited, the
    narrowing loses its ground — and this reddens rather than passing silently."""
    capture = json.loads(CAPTURE.read_text(encoding="utf-8"))
    assert capture["_outcome"] == "ROUTE_DELETES_IMAGE_BLOCK"
    assert capture["_verdict_image_27"] == "gone"
    assert capture["_verdict_control_text_2"] == "gone", (
        "the control is what makes the answer attributable to the block type")
    assert capture["_scope"]["sends_that_are_the_question"] == 1


def test_the_capture_takes_its_verdict_from_a_READ_BACK_and_not_from_code_zero():
    """R12: the delete answered ``code: 0`` — which is exactly why the capture has to prove
    it looked again. Both read-back questions must be recorded, and both must say gone."""
    capture = json.loads(CAPTURE.read_text(encoding="utf-8"))
    question = capture["question_image_27"]
    assert question["code"] == 0 and question["accepted"] is True
    read_back = question["read_back"]
    assert read_back["parent_still_lists_it"] is False
    assert read_back["direct_read_resolves"] is False
    assert read_back["direct_read_error"]["code"] == 1770002


def test_the_capture_scopes_its_claim_and_names_what_it_did_not_measure():
    """D-59: the claim may not exceed its evidence, and the seven unmeasured types must be
    named in the capture itself rather than only in prose."""
    scope = json.loads(CAPTURE.read_text(encoding="utf-8"))["_scope"]
    assert scope["block_type_measured"].startswith("image (docx block type 27)")
    unmeasured = " ".join(scope["unmeasured_not_refuted"])
    for word in ("board (43)", "iframe (26)", "Base embed (18)", "Sheet embed (30)",
                 "Base named-view (53)", "synced origin (49)", "synced reference (50)"):
        assert word in unmeasured
