"""``compose()`` output flows through the SHIPPED gate — nothing new, nothing ungated
(LD-136/AC6, decision **D1/D6**).

The corpus property (``test_compose_roundtrip_corpus``) proves the compiler agrees with the
reader at the *encoder* seam. This file closes the other half: a composed fragment is
carried by the **existing** ``InsertRequest`` through the **existing**
``dry_run`` → :class:`Plan` → ``apply`` pipeline with an injected transport — so the
authoring surface adds **no ungated path**, and what lands is exactly what the encoder
emits (including the LD-135 table-cell fills through the shipped whole-cell patch).

All offline: a fake clock and a stub opener, no network.
"""
import pytest

from larkdocio.write import compose, compose_insert
from larkdocio.write.apply import apply
from larkdocio.write.model import Anchor, InsertPosition, RefusedError
from larkdocio.write.preview import Plan, dry_run

from write_harness import (
    StubOpener,
    _block_payload,
    _by_method,
    _client,
    _page,
    _para,
    _parent_payload,
    _patch_ok,
    _run,
)

_FRAGMENT = (
    "## Findings\n"
    "\n"
    "The engine can author a document now.\n"
    "\n"
    "- top item\n"
    "\t- nested item\n"
    "\n"
    "- [x] closed task\n"
    "\n"
    "```python\nprint('hi')\n```\n"
    "\n"
    "> a quoted line\n"
    "\n"
    "| Metric | Value |\n|---|---|\n| On-time | 97.2% |\n"
)


def _tree():
    return _page(_para("p1", "anchor line"))


def _create_ok(*records):
    """A ``create_children`` response; a ``(block_id, [child, ...])`` pair is the shape
    Lark returns for a table whose cells it auto-provisioned."""
    children = []
    for record in records:
        if isinstance(record, tuple):
            children.append({"block_id": record[0], "children": list(record[1])})
        else:
            children.append({"block_id": record})
    return {"code": 0, "data": {"children": children, "document_revision_id": 200}}


def _fill_responses(cell_ids, *, table_id="tbl"):
    """The batched fill's answers (LD-481): ONE document block list carrying every cell's
    inner text block, then the ``batch_update`` answers."""
    from test_table_creation import _fill_responses as _batched
    return _batched(cell_ids, table_id=table_id)


def test_a_composed_fragment_reaches_lark_only_through_a_dry_run_plan():
    """AC6 / D6: ``apply`` accepts only a ``Plan`` from ``dry_run`` — a hand-built request
    list cannot be applied, so composing gives a consumer no way around the gate."""
    request = compose_insert("# H\n", reference=Anchor(quote="anchor line"))
    with pytest.raises(TypeError):
        apply([request], _client(StubOpener([])), "doc123")


def test_a_dry_run_of_composed_content_issues_no_write():
    opener = StubOpener([])
    plan = dry_run(
        [compose_insert(_FRAGMENT, reference=Anchor(quote="anchor line"))], _tree(),
    )
    assert isinstance(plan, Plan)
    assert opener.requests == []
    assert plan.entries[0].refusal is None


def test_the_dry_run_preview_shows_every_composed_kind():
    """The mandatory dry-run previews the whole composed structure, so a consumer's
    approval UX shows what the Markdown became before a single write."""
    plan = dry_run(
        [compose_insert(_FRAGMENT, reference=Anchor(quote="anchor line"))], _tree(),
    )
    shown = plan.to_dict()["entries"][0]["content"]
    assert [c["kind"] for c in shown] == [
        "heading", "paragraph", "bullet", "todo", "code", "quote", "table",
    ]
    preview = repr(shown)
    for expected in ("Findings", "top item", "nested item", "closed task", "print('hi')",
                     "a quoted line", "On-time"):
        assert expected in preview


def test_composed_content_lands_through_the_shipped_apply_path():
    """The whole chain: compose → InsertRequest → dry_run → apply, with the real encoder
    payloads asserted at the transport and the table's authored cells filled through the
    SAME whole-cell patch body a ``TableLocator`` edit uses — batched (LD-481)."""
    plan = dry_run(
        [compose_insert(
            _FRAGMENT, reference=Anchor(quote="anchor line"),
            position=InsertPosition.AFTER,
        )], _tree(),
    )
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),         # its LIVE parent → the index (LD-453)
        # batch 1 — the seven top-level blocks (the table reports its provisioned cells)
        _create_ok("h2", "para", "b1", "todo1", "code1", "quote1",
                   ("tbl", ["c0", "c1", "c2", "c3"])),
        # batch 2 — the nested bullet, parented on the real id batch 1 returned
        _create_ok("b1child"),
        # the table's four authored cells: ONE block list, then ONE batched update
        *_fill_responses(["c0", "c1", "c2", "c3"]),
    ])
    log = apply(plan, _client(opener), "doc123")

    posts = _by_method(opener, "POST")
    assert len(posts) == 2
    assert "/blocks/root/children" in posts[0]["url"]
    assert posts[0]["body"]["children"] == [
        {"block_type": 4, "heading2": {
            "elements": [{"text_run": {"content": "Findings"}}]}},
        {"block_type": 2, "text": {
            "elements": [{"text_run": {
                "content": "The engine can author a document now."}}]}},
        {"block_type": 12, "bullet": {
            "elements": [{"text_run": {"content": "top item"}}]}},
        {"block_type": 17, "todo": {
            "elements": [{"text_run": {"content": "closed task"}}],
            "style": {"done": True}}},
        {"block_type": 14, "code": {
            "elements": [{"text_run": {"content": "print('hi')"}}],
            "style": {"language": 49}}},
        {"block_type": 15, "quote": {
            "elements": [{"text_run": {"content": "a quoted line"}}]}},
        {"block_type": 31, "table": {"property": {
            "row_size": 2, "column_size": 2, "header_row": True}}},
    ]
    # the nested item was created under the real id of its parent
    assert "/blocks/b1/children" in posts[1]["url"]
    assert posts[1]["body"]["children"] == [
        {"block_type": 12, "bullet": {
            "elements": [{"text_run": {"content": "nested item"}}]}},
    ]

    # the four authored cells were filled through the shipped whole-cell patch body,
    # carried in ONE batched call (LD-481) rather than one PATCH per cell
    patches = [r for r in opener.requests if r["method"] == "PATCH"]
    assert len(patches) == 1 and "batch_update" in patches[0]["url"]
    requests = patches[0]["body"]["requests"]
    assert [r["block_id"] for r in requests] == ["c0t", "c1t", "c2t", "c3t"]
    assert [
        r["update_text_elements"]["elements"][0]["text_run"]["content"]
        for r in requests
    ] == ["Metric", "Value", "On-time", "97.2%"]

    assert log.entries[0].outcome == "inserted"
    # pre-order: a nested child is logged right after the parent it was created under
    assert log.entries[0].created_block_ids == (
        "h2", "para", "b1", "b1child", "todo1", "code1", "quote1", "tbl",
    )


def test_an_authored_escape_lands_literal_in_the_payload():
    """The LD-130 interplay end to end: an escaped metachar composes to literal text and
    the encoder ships it **verbatim** (escaping is the reader's job on the way out)."""
    plan = dry_run(
        [compose_insert("\\# not a heading\n", reference=Anchor(quote="anchor line"))],
        _tree(),
    )
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),         # its LIVE parent → the index (LD-453)
        _create_ok("newP"),
    ])
    apply(plan, _client(opener), "doc123")
    body = _by_method(opener, "POST")[0]["body"]
    assert body["children"] == [
        {"block_type": 2, "text": {
            "elements": [{"text_run": {"content": "# not a heading"}}]}},
    ]


def test_a_refused_fragment_never_reaches_a_plan_at_all():
    """A refusal happens at COMPILE time, so an out-of-dialect fragment cannot even be
    packaged into a request — there is nothing to dry-run and nothing to apply."""
    opener = StubOpener([])
    with pytest.raises(RefusedError):
        compose_insert("![alt](tok)\n", reference=Anchor(quote="anchor line"))
    assert opener.requests == []


def test_a_composed_batch_may_mix_with_hand_built_requests():
    """Composing is additive: a composed insert sits in the same batch as any other
    request the engine already accepts."""
    from write_harness import _req

    plan = dry_run([
        _req("anchor line", replacement="rewritten"),
        compose_insert("- from markdown\n", reference=Anchor(quote="anchor line")),
    ], _tree())
    assert len(plan.entries) == 2
    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _patch_ok(),                             # the EDIT — no parent read
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),         # its LIVE parent → the index (LD-453)
        _create_ok("newB"),
    ])
    log = apply(plan, _client(opener), "doc123")
    assert [e.outcome for e in log.entries] == ["applied", "inserted"]


def test_ld142_compose_insert_declares_the_anchor_family_the_request_accepts():
    """LD-142 rider (QA's carried Minor from LD-137). ``compose_insert`` is *exactly*
    ``InsertRequest(reference=anchor, position=…, content=compose(md))`` — so its declared
    ``reference`` type must be the request's own
    :data:`~larkdocio.write.model.NarrativeAnchor` union. It said bare ``Anchor``, which read
    as "authoring is quote-anchored only" and would send a consumer looking for an
    ``AnchorById`` overload that already exists: the pairing has accepted an id anchor since
    LD-137, and the offline test below exercises it.
    """
    import typing

    from larkdocio.capabilities import _flatten_anchor_types
    from larkdocio.write.model import InsertRequest

    declared = {t.__name__ for t in _flatten_anchor_types(
        typing.get_type_hints(compose_insert)["reference"])}
    accepted = {t.__name__ for t in _flatten_anchor_types(
        typing.get_type_hints(InsertRequest)["reference"])}
    assert declared == accepted, (
        f"compose_insert declares reference: {sorted(declared)} but the InsertRequest it "
        f"builds accepts {sorted(accepted)}")


def test_ld142_compose_insert_really_accepts_an_id_anchor_through_the_gate():
    """The behavioral half of the rider: the widened annotation documents something that
    already works — a composed fragment anchored by ``block_id`` runs the whole
    ``dry_run`` → ``apply`` gate, id-anchored compare-and-swap included."""
    from larkdocio.write.model import AnchorById

    request = compose_insert("- from markdown\n", reference=AnchorById(block_id="p1"))
    plan = dry_run([request], _tree())
    (entry,) = plan.entries
    assert entry.is_resolved and entry.block_id == "p1"
    assert entry.precondition_text == "anchor line"   # the by-id CAS precondition (LD-137)

    opener = StubOpener([
        _block_payload("p1", [_run("anchor line")], parent_id="root"),
        _parent_payload("root", ["p1"]),         # its LIVE parent → the index (LD-453)
        _create_ok("newB"),
    ])
    log = apply(plan, _client(opener), "doc123")
    assert [e.outcome for e in log.entries] == ["inserted"]
