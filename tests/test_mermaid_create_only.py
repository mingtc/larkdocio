"""CREATE-ONLY: the mermaid NO-GO is pinned as a regression test, not left as a memory
(LD-192 / AC3).

The gate probe's second verdict was **UPDATE-IN-PLACE: NO-GO** — the docx block-patch surface
carries no ``add_ons`` updater (17 update descriptors, none of them ``add_ons``; three
plausible field spellings each refused ``1770001 invalid param`` live). So a diagram is
creatable but **not editable in place**, and editing one means **delete + re-create at the same
index**, at the cost of a **new ``block_id``**.

That has three consequences, and this file pins each so none can quietly drift:

1. **No update op ships, and none can be added by accident.** The absence is asserted against
   the pinned SDK's own descriptor set *and* against larkdocio's op registry — so an
   ``add_ons`` updater invented later reddens here rather than shipping.
2. **The refusal names the real route.** A consumer who reaches for a whole-block edit on a
   diagram gets told to delete + re-create, with the ``block_id`` cost stated — instead of the
   generic container message, which was written for a block whose text lives in its children
   and is simply not true of a diagram.
3. **The replace route is sound, including its recovery record.** The delete half's apply-log
   entry promises a *complete, lossless* snapshot of what was removed; for a diagram that has
   to include the diagram. Otherwise the route this library now recommends would be the one
   route whose undo record is empty.

The three refusal codes the probe measured are pinned in
``tests/test_mermaid_create_encode.py``; this file is about the *shape of the surface*.
"""
import json

import pytest

import harness
from larkdocio.blocks.diagram import MERMAID_COMPONENT_TYPE_ID
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    AnchorById,
    DeleteRequest,
    EditRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    SubSpanEditRequest,
    apply,
    dry_run,
)
from larkdocio.write.model import NewBlockKind, RefusalReason

_SOURCE = "flowchart TD\n    A[\"Draft\"] --> B[\"Shipped\"]"
_REVISED = "flowchart TD\n    A[\"Draft\"] --> B[\"Shipped\"] --> C[\"Archived\"]"


def _blocks(source=_SOURCE):
    return [
        {"block_id": "page", "block_type": 1, "parent_id": "",
         "children": ["h1"],
         "page": {"elements": [{"text_run": {"content": "Doc Title"}}]}},
        {"block_id": "h1", "block_type": 3, "parent_id": "page",
         "children": ["p1", "b40", "c19"],
         "heading1": {"elements": [{"text_run": {"content": "Overview"}}]}},
        # a genuine CONTAINER — a callout whose text really does live in a child block. It is
        # the control for the diagram rider: the generic message is TRUE here, so it must stay.
        {"block_id": "c19", "block_type": 19, "parent_id": "h1", "children": ["p2"],
         "callout": {}},
        {"block_id": "p2", "block_type": 2, "parent_id": "c19", "children": [],
         "text": {"elements": [{"text_run": {"content": "Inside the callout."}}]}},
        {"block_id": "p1", "block_type": 2, "parent_id": "h1", "children": [],
         "text": {"elements": [{"text_run": {"content": "Anchor paragraph."}}]}},
        {"block_id": "b40", "block_type": 40, "parent_id": "h1", "children": [],
         "add_ons": {
             "component_id": "",
             "component_type_id": MERMAID_COMPONENT_TYPE_ID,
             "record": json.dumps({"data": source, "theme": "default", "view": "codeChart"}),
         }},
    ]


def _tree(source=_SOURCE):
    return Parser(new_config()).parse_docx_tree("page", harness.build_blocks(_blocks(source)))


# =========================================================================== #
# 1. NO UPDATE PATH EXISTS — asserted against the SDK and against our registry  #
# =========================================================================== #

def test_the_pinned_SDK_carries_NO_add_ons_UPDATER():
    """The schema-level half of the verdict, re-derived from the pinned SDK rather than quoted.

    The asymmetry *is* the finding: ``Block`` carries ``add_ons`` (so it is expressible on a
    **create**) while ``UpdateBlockRequest`` has no updater for it (so it is not expressible on
    an **update**). If a future SDK adds one, this test reddens and the NO-GO is reopened
    deliberately — which is exactly the review this capability should get.
    """
    from lark_oapi.api.docx.v1 import UpdateBlockRequest
    from lark_oapi.api.docx.v1.model.block import Block

    descriptors = set(UpdateBlockRequest._types)
    assert "add_ons" in Block._types, "add_ons must still be expressible on a create"
    assert not any("add_ons" in name for name in descriptors), (
        f"the SDK grew an add_ons updater: {sorted(descriptors)}")
    assert len(descriptors) == 17, sorted(descriptors)


def test_the_add_ons_model_carries_exactly_the_three_fields_the_encoder_emits():
    """Nothing server-minted, nothing missing — the finding that made the create possible."""
    from lark_oapi.api.docx.v1.model.add_ons import AddOns

    assert set(AddOns._types) == {"component_id", "component_type_id", "record"}


def _add_ons_key_sites():
    """Every line in the shipped write package that builds an ``add_ons``-flavoured dict key.

    Read over the real source so a helper added anywhere in the package is covered, not just
    the paths this test happens to know about.
    """
    import pathlib

    import larkdocio.write

    root = pathlib.Path(larkdocio.write.__file__).parent
    sites = []
    for path in sorted(root.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            for spelling in ("add_ons", "update_add_ons", "replace_add_ons"):
                if f'"{spelling}":' in code or f"'{spelling}':" in code:
                    sites.append((path.name, lineno, spelling, line.strip()))
    return sites


@pytest.mark.parametrize("spelling", ["update_add_ons", "replace_add_ons"])
def test_the_two_UPDATE_flavoured_spellings_appear_NOWHERE(spelling):
    """Two of the three field spellings the probe tried live are update-only inventions — there
    is no legitimate reason for either to exist anywhere in the package, so their absence is
    absolute."""
    offenders = [s for s in _add_ons_key_sites() if s[2] == spelling]
    assert not offenders, (
        f"{spelling!r} appeared — the docx block-patch surface has no add_ons updater, so "
        f"building one can only ever refuse 1770001: {offenders}")


def test_the_ONLY_place_that_builds_an_add_ons_KEY_is_the_CREATE_encoder():
    """The bare ``add_ons`` spelling is legitimate in exactly one place — the **create**
    payload — and refuses ``1770001`` everywhere else, because no updater exists.

    So rather than banning the word, this pins the *census*: one site, in the encoder. A second
    site anywhere in the write package reddens here and has to justify itself, which is the
    check that actually protects the NO-GO (a ban would have to exempt the create path and
    would then be blind to a patch builder added beside it).
    """
    sites = [s for s in _add_ons_key_sites() if s[2] == "add_ons"]
    assert [(name, spelling) for name, _lineno, spelling, _line in sites] == [
        ("encode.py", "add_ons")], (
        f"exactly one add_ons key site is expected — the create encoder — got: {sites}")


def test_the_op_registry_has_no_diagram_UPDATE_op():
    """larkdocio's own op-descriptor registry is the discoverable list of what the engine can
    do. No diagram update belongs in it, and the create path deliberately needs no op of its
    own — a diagram is inserted by the ordinary insert op."""
    from larkdocio.write.ops import OPS

    names = [d.kind for d in OPS]
    assert not [n for n in names if "add_on" in n or "mermaid" in n or "diagram" in n], names


# =========================================================================== #
# 2. THE REFUSAL NAMES THE REAL ROUTE                                          #
# =========================================================================== #

def _refusals(requests, tree=None):
    plan = dry_run(requests, tree if tree is not None else _tree())
    return [e.refusal for e in plan.refusals]


def test_a_whole_block_edit_of_a_diagram_REFUSES():
    (refusal,) = _refusals([EditRequest(anchor=AnchorById(block_id="b40"),
                                       replacement="flowchart TD\n  X --> Y")])
    assert refusal.reason is RefusalReason.WRITE_HOSTILE
    assert "b40" in refusal.detail


def test_the_diagram_refusal_names_DELETE_PLUS_RECREATE_and_the_block_id_COST():
    """The rider this issue adds. The generic container message ("its text lives in its child
    blocks") is *false* for a diagram — a diagram has no children, its source lives in
    ``add_ons.record`` — and its advice ("target the text-bearing child block's id") cannot
    succeed. The refusal must instead name the route that works, and the cost it carries.
    """
    (refusal,) = _refusals([EditRequest(anchor=AnchorById(block_id="b40"),
                                       replacement="flowchart TD\n  X --> Y")])
    detail = refusal.detail
    low = detail.lower()
    assert "no in-place update" in low or "no add_ons updater" in low, detail
    assert "delete" in low and "re-create" in low, detail
    assert "same index" in low, detail
    assert "block_id" in detail, detail
    # …and it must NOT repeat the container claim, which is untrue here.
    assert "its text lives in its child blocks" not in low, detail
    assert "text-bearing child block" not in low, detail


def test_a_sub_span_edit_of_a_diagram_ALSO_refuses():
    """A diagram's source is not a run of styled text, so the sub-span path cannot touch it
    either. Asserted because "the whole-block path refuses" would be a hollow guarantee if the
    finer-grained one let a patch through."""
    (refusal,) = _refusals([SubSpanEditRequest(anchor=AnchorById(block_id="b40"),
                                              span="Draft", replacement="Sketch")])
    assert refusal.reason in (
        RefusalReason.WRITE_HOSTILE, RefusalReason.NOT_FOUND,
        RefusalReason.SPAN_NOT_SPLITTABLE), refusal.to_dict()
    assert "b40" in refusal.detail, refusal.detail


def test_the_ordinary_container_refusal_is_UNCHANGED_for_a_real_container():
    """The rider is additive, not a rewrite.

    The control is a **callout** (type 19): a real container, whose text really does live in a
    child block, so the generic message and its advice ("target the text-bearing child block's
    id") are both TRUE for it. That message must survive byte-for-byte — the diagram rider
    exists because the message is false for a *diagram*, not because it was ever wrong.
    """
    (refusal,) = _refusals([EditRequest(anchor=AnchorById(block_id="c19"),
                                        replacement="x")])
    detail = refusal.detail.lower()
    assert "container block that carries no text of its own" in detail, refusal.detail
    assert "re-create" not in detail, (
        "the diagram rider must not leak into the generic container refusal")


# =========================================================================== #
# 3. THE REPLACE ROUTE IS SOUND — including its recovery record                 #
# =========================================================================== #

class _Client:
    """The narrowest write double the replace route needs: a real document that a delete
    really removes from and a create really appends to, so ``apply``'s own logic runs."""

    def __init__(self, blocks):
        self.order = [b["block_id"] for b in blocks]
        self.blocks = {b["block_id"]: dict(b) for b in blocks}
        self.revision = 1
        self._minted = 0

    def get_block(self, document_id, block_id):
        return dict(self.blocks[block_id])

    def read_document_revision(self, document_id):
        return self.revision

    def create_children(self, document_id, block_id, children, index=None):
        self.revision += 1
        made = []
        for payload in children:
            self._minted += 1
            minted = f"minted{self._minted}"
            self.blocks[minted] = dict(payload, block_id=minted, parent_id=block_id,
                                       children=[])
            made.append(minted)
        parent = self.blocks[block_id]
        kids = list(parent.get("children") or ())
        at = len(kids) if index is None or index < 0 else index
        parent["children"] = kids[:at] + made + kids[at:]
        return {"children": [self.blocks[b] for b in made]}

    def batch_delete(self, document_id, block_id, start_index, end_index):
        self.revision += 1
        parent = self.blocks[block_id]
        kids = list(parent.get("children") or ())
        for block_id in kids[start_index:end_index]:
            self.blocks.pop(block_id, None)
        parent["children"] = kids[:start_index] + kids[end_index:]
        return {}


def test_THE_REPLACE_ROUTE_works_end_to_end_and_the_block_id_CHANGES():
    """The route the docs prescribe, run through the ordinary gate — insert the replacement at
    the old block's position, then delete the old block — with the cost **measured**: a new
    ``block_id``. This is the amplifier's "prove it, don't assert it" clause.
    """
    client = _Client(_blocks())
    plan = dry_run(
        [
            InsertRequest(reference=AnchorById(block_id="b40"),
                          position=InsertPosition.BEFORE,
                          content=(NewBlock.mermaid(_REVISED),)),
            DeleteRequest(target=AnchorById(block_id="b40")),
        ],
        _tree(),
    )
    assert not plan.refusals, [r.refusal.detail for r in plan.refusals]

    log = apply(plan, client, "page")
    assert [e.outcome for e in log.entries] == ["inserted", "deleted"], (
        [e.to_dict() for e in log.entries])

    (new_id,) = log.entries[0].created_block_ids
    assert new_id != "b40", "the replace route must yield a NEW block_id"
    assert "b40" not in client.blocks, "the old diagram must be gone"

    landed = client.blocks[new_id]
    assert landed["block_type"] == 40
    assert json.loads(landed["add_ons"]["record"])["data"] == _REVISED

    # the replacement really took the old one's POSITION, not merely "somewhere in the parent":
    # it sits at index 1, exactly where "b40" was, with its siblings undisturbed either side.
    assert client.blocks["h1"]["children"] == ["p1", new_id, "c19"], (
        client.blocks["h1"]["children"])


def test_the_DELETE_half_records_the_diagram_it_removed():
    """The apply-log's removed-payload promises a **complete, lossless** snapshot — enough to
    recreate the block. For a diagram that means the ``add_ons`` object: without it, the one
    route this library recommends for editing a diagram would be the one route whose undo
    record is empty, and a failed re-create would lose the source for good.

    A diagram carries no ``elements`` container at all, which is exactly why the shape-based
    capture missed it.
    """
    client = _Client(_blocks())
    plan = dry_run([DeleteRequest(target=AnchorById(block_id="b40"))], _tree())
    assert not plan.refusals, [r.refusal.detail for r in plan.refusals]
    log = apply(plan, client, "page")

    removed = log.entries[0].removed_payload
    assert removed["block_type"] == 40, removed
    assert "add_ons" in removed, (
        f"the removed-payload lost the diagram — it is not reconstructable: {removed}")
    assert removed["add_ons"]["component_type_id"] == MERMAID_COMPONENT_TYPE_ID
    assert json.loads(removed["add_ons"]["record"])["data"] == _SOURCE

    # …and it is JSON-serializable, like every other apply-log record.
    assert json.loads(json.dumps(log.entries[0].to_dict()))["removed_payload"]["add_ons"]


def test_the_removed_payload_for_a_TEXT_block_is_unchanged():
    """The capture fix is additive: a block with an ``elements`` container records exactly what
    it always did, and gains no spurious ``add_ons`` key."""
    client = _Client(_blocks())
    plan = dry_run([DeleteRequest(target=AnchorById(block_id="p1"))], _tree())
    log = apply(plan, client, "page")
    removed = log.entries[0].removed_payload
    assert removed["block_type"] == 2
    assert removed["elements"] == [{"text_run": {"content": "Anchor paragraph."}}]
    assert "add_ons" not in removed, removed


def test_the_recovered_payload_can_REBUILD_the_diagram_that_was_deleted():
    """The snapshot's whole purpose, exercised: take the removed payload and re-create the
    block from it. If this round-trips, the undo record really is sufficient."""
    client = _Client(_blocks())
    log = apply(dry_run([DeleteRequest(target=AnchorById(block_id="b40"))], _tree()),
                client, "page")
    removed = log.entries[0].removed_payload

    rebuilt = {"block_type": removed["block_type"], "add_ons": removed["add_ons"]}
    result = client.create_children("page", "h1", [rebuilt], index=1)
    (block,) = result["children"]
    assert block["block_type"] == 40
    assert json.loads(block["add_ons"]["record"])["data"] == _SOURCE


# =========================================================================== #
# 4. The consequence for anchoring, stated where a consumer will meet it        #
# =========================================================================== #

def test_the_capability_floor_and_the_writer_brief_both_warn_about_the_cached_id():
    """The verdict's own words: *a projection that caches a type-40 block id across an edit is
    unsound*. It constrains future id-anchored work, so it is said once, clearly, on the two
    surfaces a consumer plans against."""
    from larkdocio import capabilities, writer_brief

    floor = capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]
    joined = " ".join(floor["not_creatable"]).lower()
    assert "unsound" in joined, floor["not_creatable"]
    assert "block_id" in " ".join(floor["not_creatable"]), floor["not_creatable"]

    # Normalized before matching: the phrase spans a line wrap in the shipped Markdown, and a
    # flat substring grep walks straight past a wrapped claim (the lesson from the
    # comment-anchor reassurance guard).
    brief = " ".join(writer_brief().lower().split())
    assert "unsound" in brief
    assert "caching a type-40 block id across an edit is unsound" in brief


def test_a_diagram_is_creatable_AND_deletable_which_is_what_makes_the_route_possible():
    """The two halves the replace route needs, asserted together: a diagram can be brought
    into existence and it can be removed. It is only the *middle* — patching one — that does
    not exist."""
    plan = dry_run([DeleteRequest(target=AnchorById(block_id="b40"))], _tree())
    assert len(plan.resolved) == 1 and not plan.refusals

    insert = dry_run([InsertRequest(reference=AnchorById(block_id="p1"),
                                    position=InsertPosition.AFTER,
                                    content=(NewBlock.mermaid(_SOURCE),))], _tree())
    assert len(insert.resolved) == 1 and not insert.refusals
    assert insert.resolved[0].content[0].kind is NewBlockKind.MERMAID
