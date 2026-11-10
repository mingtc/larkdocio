"""LD-528 — the destructive-safe undo record carries the IMAGE it destroyed.

``_capture_removed_payload`` is the only record of something irreversible: it is written
from the live block read immediately before the delete, and once the delete lands there is
nothing left to read. Its own docstring calls it a *complete, lossless snapshot* and says
*an incomplete payload is a FAIL* — and for an image block it recorded
``{'block_id': …, 'block_type': 27, 'elements': [], 'style': None}``: the block that was
destroyed named, and nothing about what was in it.

**Why it was empty, and why that only mattered from LD-507 onwards.** The capture finds a
block's content **by shape** — the one value that is a dict carrying an ``elements`` list.
An image has no such value; its content is the ``image`` object. Before LD-507 the delete
of an image refused at resolve time, so the empty record was unreachable. LD-507 measured
Lark's own child-delete route against an image, narrowed the fence to admit it, and the
shipped guide now *recommends* that route — which made the empty record reachable on
precisely the type the library had just started recommending.

**The precedent is the fix's shape (LD-192).** A diagram carries no ``elements`` container
either, and its ``add_ons`` object is captured verbatim, the key absent for every other
type so existing records stay byte-unchanged. This file polices the same contract for the
``image`` object, and it polices the negative half just as hard: a text record and a
diagram record must be **unchanged**, with no spurious ``image`` key.

**What this record is NOT, and the tests say so on purpose.** It is a **reference** record.
The token names bytes that still exist — deleting the block deletes no media and no route
in Lark's open API purges drive media — so a consumer can name what was destroyed and fetch
it back with ``DocxMediaClient.download``. It is **not** an undo button: nothing in this
library re-binds a captured token to a new block (``put_image_in_document`` takes no
pre-made token), so re-authoring the picture is a fresh upload and a **new** permanent
token. No test here asserts a restore, and the shipped words must not promise one.

**Fixture provenance — measured, not invented (AC3).** The five-key image payload below is
quoted verbatim from LD-506's committed capture
``dev/ld506-in-cell-image/captures/002-in-cell-image-raw-payload.json``,
``blocks_flat_route[10]`` — which at the time of writing lives on the unlanded branch
of LD-506, NOT on this one. The delete
itself is LD-507's capture ``tests/captures/ld507-image-block-delete/captures/001-image-block-delete.json``
(on this branch), which names the same block id and the same media token but does not
record the block's five-key payload — the payload citation belongs to LD-506's capture and
is written that way here deliberately. **Zero live calls, zero disposables, zero media
tokens** were spent by this file or by the change it guards.
"""
import json

import pytest

import harness
from larkdocio.model import ImageNode
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.write import AnchorById, DeleteRequest, apply, dry_run
from larkdocio.write.apply import _capture_removed_payload

from write_harness import LiveTreeOpener, _client, _page, _para

#: THE MEASURED PAYLOAD — verbatim from LD-506's capture 002 (see the module docstring for
#: the path and the branch it lives on). Five keys, not four: ``scale`` is real.
MEASURED_IMAGE = {"align": 2, "height": 1, "scale": 1,
                  "token": "Examplec11ec9e2c11b40f4193c", "width": 1}

#: HYPOTHETICAL, NOT CAPTURED — no live payload measured here has ever carried these keys.
#: It exists for exactly one purpose: to prove the capture takes the object **whole** rather
#: than enumerating the five keys it happens to know, so a key a future payload carries
#: survives too. It must never be read as a claim about what Lark returns.
HYPOTHETICAL_IMAGE = dict(MEASURED_IMAGE, caption="Q3 revenue", some_future_key={"a": 1})

_DIAGRAM_ADD_ONS = {
    "component_id": "",
    "component_type_id": "blk_example00000000000000001",  # synthetic, not Mermaid's id
    "record": json.dumps({"data": "flowchart TD\n  A --> B", "theme": "default"}),
}


def _blocks(image=MEASURED_IMAGE):
    return [
        {"block_id": "page", "block_type": 1, "parent_id": "",
         "children": ["p1", "img27", "b40"],
         "page": {"elements": [{"text_run": {"content": "Doc Title"}}]}},
        {"block_id": "p1", "block_type": 2, "parent_id": "page", "children": [],
         "text": {"elements": [{"text_run": {"content": "Anchor paragraph."}}]}},
        {"block_id": "img27", "block_type": 27, "parent_id": "page", "children": [],
         "image": dict(image)},
        {"block_id": "b40", "block_type": 40, "parent_id": "page", "children": [],
         "add_ons": dict(_DIAGRAM_ADD_ONS)},
    ]


def _tree():
    return Parser(new_config()).parse_docx_tree(
        "page", harness.build_blocks(_blocks()))


class _Client:
    """The narrowest write double a delete needs: a real tree a delete really removes from,
    so ``apply``'s own re-read → capture → delete sequence runs unmodified."""

    def __init__(self, blocks):
        self.blocks = {b["block_id"]: dict(b) for b in blocks}
        self.revision = 1

    def get_block(self, document_id, block_id):
        return dict(self.blocks[block_id])

    def read_document_revision(self, document_id):
        return self.revision

    def batch_delete(self, document_id, block_id, start_index, end_index):
        self.revision += 1
        parent = self.blocks[block_id]
        kids = list(parent.get("children") or ())
        for gone in kids[start_index:end_index]:
            self.blocks.pop(gone, None)
        parent["children"] = kids[:start_index] + kids[end_index:]
        return {}


def _delete(block_id, live_image=MEASURED_IMAGE):
    """Drive a full delete through the PUBLIC surface and hand back the apply-log record.

    ``live_image`` is what the **client** answers for the image block — deliberately a
    separate knob from the offline tree, because the record is written from the live read
    and the live read may carry keys the offline model has no field for.
    """
    client = _Client(_blocks(live_image))
    plan = dry_run([DeleteRequest(target=AnchorById(block_id=block_id))], _tree())
    assert not plan.refusals, [r.refusal.detail for r in plan.refusals]
    log = apply(plan, client, "page")
    assert block_id not in client.blocks, "the delete did not actually remove the block"
    return log.entries[0]


# =========================================================================== #
# 1. THE DEFECT ITSELF — the record carries the image, through the public log  #
# =========================================================================== #

def test_an_image_delete_RECORDS_THE_IMAGE_it_destroyed():
    """The one assertion the empty record could not satisfy. Watch this redden by deleting
    the ``image`` arm of ``_capture_removed_payload``: the record collapses to
    ``{'block_id': 'img27', 'block_type': 27, 'elements': [], 'style': None}`` — the file
    token, the only handle on bytes that outlive the block, gone with it."""
    removed = _delete("img27").removed_payload

    assert removed["block_type"] == 27, removed
    assert "image" in removed, (
        f"the removed-payload lost the picture — the record names a block that no longer "
        f"exists and nothing about what was in it: {removed}")
    assert removed["image"]["token"] == MEASURED_IMAGE["token"], removed


def test_the_recorded_image_is_VERBATIM_AND_WHOLE_not_re_keyed():
    """``==`` against the measured object, not a key-by-key rebuild: the capture must take
    the object as read. A capture that enumerated ``align``/``height``/``scale``/``token``/
    ``width`` would pass the token assertion above and still silently drop the sixth key a
    future payload carries — which is why the hypothetical shape is exercised too. The
    hypothetical is fed through the **live read**, not the offline tree: that is where a
    surprise key would actually arrive, and the pinned SDK's ``Block`` model cannot even
    hold one."""
    assert _delete("img27").removed_payload["image"] == MEASURED_IMAGE

    surprising = _delete("img27", live_image=HYPOTHETICAL_IMAGE).removed_payload["image"]
    assert surprising == HYPOTHETICAL_IMAGE, (
        f"a key the capture did not know about was dropped: {surprising}")


def test_the_image_record_survives_the_JSON_round_trip_a_consumer_will_log_it_through():
    """The apply log's own serialization — the shape a consumer's undo trail is written in.
    An unserializable record is a record nobody has."""
    entry = _delete("img27")
    round_tripped = json.loads(json.dumps(entry.to_dict()))["removed_payload"]
    assert round_tripped["image"] == MEASURED_IMAGE, round_tripped


def test_the_image_record_is_reachable_through_the_apply_log_not_only_the_helper():
    """Belt and braces on the surface: the helper and the public log agree, so the guard
    above is policing what a consumer actually reads."""
    block = next(b for b in _blocks() if b["block_id"] == "img27")
    assert _capture_removed_payload(block, "img27")["image"] == MEASURED_IMAGE


def test_the_double_that_LD507_ships_ALSO_answers_the_real_image_shape():
    """The other apply-level path — LD-507's ``LiveTreeOpener``, driven through the real
    ``WriteClient`` and its transport rather than a hand-rolled double. Its type-27 arm
    already answered the five measured keys before this fix; only the record was empty."""
    opener = LiveTreeOpener(
        children={"root": ["p1", "img", "p2"]},
        texts={"p1": "Alpha body paragraph.", "p2": "Beta body paragraph."},
        block_types={"img": 27},
    )
    tree = _page(_para("p1", "Alpha body paragraph."),
                 ImageNode(block_id="img", token="tok"),
                 _para("p2", "Beta body paragraph."))
    plan = dry_run([DeleteRequest(target=AnchorById(block_id="img"))], tree)
    log = apply(plan, _client(opener), "doc528")

    removed = log.entries[0].removed_payload
    assert set(removed["image"]) == {"align", "height", "scale", "token", "width"}, removed
    assert removed["image"]["token"] == "tok-img", removed


# =========================================================================== #
# 2. THE NEGATIVE HALF — every other record is BYTE-UNCHANGED (the LD-192 law) #
# =========================================================================== #

def test_the_removed_payload_for_a_TEXT_block_gains_NO_image_key():
    removed = _delete("p1").removed_payload
    assert removed == {
        "block_id": "p1",
        "block_type": 2,
        "elements": [{"text_run": {"content": "Anchor paragraph."}}],
        "style": None,
    }, removed


def test_the_removed_payload_for_a_DIAGRAM_block_is_unchanged_and_gains_NO_image_key():
    """LD-192's record must survive LD-528 untouched — same four base keys, ``add_ons``
    still verbatim, no ``image``."""
    removed = _delete("b40").removed_payload
    assert removed == {
        "block_id": "b40",
        "block_type": 40,
        "elements": [],
        "style": None,
        "add_ons": _DIAGRAM_ADD_ONS,
    }, removed


@pytest.mark.parametrize("block_id", ["p1", "b40"])
def test_no_record_of_a_non_image_block_carries_an_image_key(block_id):
    """The additive property stated directly: the key is **absent**, not empty, for every
    block type that is not an image — so a consumer's stored records do not change shape."""
    assert "image" not in _delete(block_id).removed_payload


def test_the_capture_adds_a_key_ONLY_when_the_live_block_carries_the_object():
    """The guard against a capture that helpfully invents ``image: None``. Read over the
    helper directly, across every block shape the delete path can hand it."""
    for block in _blocks():
        captured = _capture_removed_payload(block, block["block_id"])
        assert ("image" in captured) == ("image" in block), (block["block_id"], captured)
        assert ("add_ons" in captured) == ("add_ons" in block), (block["block_id"], captured)


# =========================================================================== #
# 3. THE RIDER (AC4) — resolve.py's "no by-id op can reach this" is FALSE now   #
# =========================================================================== #

def test_a_by_id_image_delete_really_DOES_reach_the_empty_live_basis():
    """The behavioural half of the transformed clause. ``_live_basis_plain_text`` returns
    ``""`` for an image — the preserved reason (an image carries no live text-run text) —
    and since LD-507 a by-id **delete** reaches it with one. That empty basis is not a dead
    corner: it is the mechanism that makes the delete's compare-and-swap (``'' == ''``)
    trivially hold, which is why the id route works at all."""
    from larkdocio.write.resolve import _live_basis_plain_text

    assert _live_basis_plain_text(ImageNode(block_id="img27", token="t",
                                            caption="Q3 revenue")) == ""
    # …and the whole route runs on that basis, end to end, without a stale-anchor refusal.
    entry = _delete("img27")
    assert entry.outcome == "deleted", entry.to_dict()


def test_the_live_basis_docstring_no_longer_claims_the_arm_is_UNREACHABLE():
    """The supersession, policed at the site: the reason survives, the false conclusion does
    not, and the issue that overtook it is named. Deleting the sentence instead of
    transforming it is what gets a settled argument re-litigated (CLAUDE.md § Supersession)."""
    from larkdocio.write.resolve import _live_basis_plain_text

    doc = " ".join(_live_basis_plain_text.__doc__.split())

    # NOT DELETED: the false clause is still on the page, verbatim — and it appears ONLY as
    # a quotation that the very next words declare false and attribute to LD-507. Assert the
    # whole shape in one go: a bare re-statement no longer matches.
    assert 'so no by-id op can reach this function with one"* — is **FALSE since LD-507**' in doc, doc
    # NOT STANDING: the sentence as it originally read (the clause closing the bullet) is gone.
    assert "write-hostile, so no by-id op can reach this function with one)." not in doc, doc
    # THE REASON, PRESERVED — these node kinds carry no live text-run text.
    assert "absent from the live element basis" in doc, doc
    assert "that reason stands unchanged" in doc, doc
    # THE IFRAME HALF, NOT WIDENED — unmeasured, not refuted.
    assert "iframe" in doc and "UNMEASURED, NOT REFUTED" in doc, doc


# =========================================================================== #
# 4. THE SHIPPED WORDS (AC5) — true, and not one word more                     #
# =========================================================================== #

def test_the_guide_no_longer_describes_the_record_as_elements_plus_style():
    from larkdocio import guide

    text = guide(full=True)
    assert "full payload (elements + style)" not in text, (
        "the guide still describes the record by the two keys that are empty for an image")


def test_the_guide_states_the_honest_recovery_path_and_promises_NO_re_bind():
    """The over-claim this issue exists to avoid. The guide may say the token still names
    bytes and that ``download`` gets them; it may **not** say larkdocio restores the block."""
    from larkdocio import guide

    text = guide(full=True)
    window = text[text.index("`removed_payload` is the undo you will not get any other way"):][:2600]
    assert "download" in window, window
    assert "new" in window and "token" in window, window
    assert "re-bind" in window or "rebind" in window, window
    for over_claim in ("restores the block", "restore the block", "restore the image",
                       "put the image back", "undo the delete"):
        assert over_claim not in text.lower(), over_claim


def test_no_library_route_re_binds_a_captured_token_which_is_why_the_words_are_weak():
    """The fact the wording rests on, pinned rather than remembered: the authoring route
    takes no pre-made token, so a captured one cannot be handed back to it."""
    import inspect

    from larkdocio.write.media import put_image_in_document

    params = set(inspect.signature(put_image_in_document).parameters)
    assert "token" not in params and "file_token" not in params, sorted(params)
    assert "block_id" not in params, sorted(params)
