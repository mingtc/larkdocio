"""larkdocio.write.ops — the ONE op-descriptor registry the write chains dispatch from
(LD-097).

**The problem this seam solves.** The writer grew **four parallel per-op dispatch
chains**, each an ``isinstance`` / ``op``-string ladder that had to be extended in lockstep
whenever a write op was added (the W2 table + W3 insert/delete/sub-span tranches each did
this):

* :func:`~larkdocio.write.resolve.resolve` — request kind → resolver;
* :func:`~larkdocio.write.preview.dry_run` — request kind → previewer;
* :meth:`~larkdocio.write.preview.PlanEntry.to_dict` / ``from_dict`` — op string →
  serialize / deserialize fields;
* :func:`~larkdocio.write.apply.apply` — plan entry → write path.

Five ops × four chains was the classic *divergent-change / shotgun-surgery* seam this module
closed at LD-097 — pre-registry history, deliberately **not** a count of what the registry
serves today (that arity is derived, never re-typed: see :mod:`larkdocio.write.apply`'s
declared basis, and — in the source repository rather than in the wheel —
``tests/test_write_registration_seam.py`` registers this sentence as
history so nobody "corrects" a true past-tense claim into a false present-tense one): adding an
op meant ~8 coordinated edits across four functions that could silently drift out of
agreement (a plan built by one chain but mis-served by another corrupts a document).

**The fix (this module).** One :class:`OpDescriptor` per op, gathered in the single ordered
:data:`OPS` table — *the* registration seam. Each of the four chains is now a thin generic
loop that reads its behaviour off the descriptor:

* :func:`classify` maps a request to its op kind (the ONE ordered ``isinstance`` ladder,
  shared by resolve + dry_run so the two can never disagree on kind);
* :func:`resolve_dispatch` / :func:`preview_dispatch` / :func:`apply_dispatch` /
  :func:`serialize_entry` / :func:`deserialize_entry` each look the descriptor up and call
  its bound function.

**Adding a new op is ONE registration point** — append one :class:`OpDescriptor` to
:data:`OPS` (with its ``resolve`` / ``preview`` / ``apply`` / ``serialize`` / ``deserialize``
callables, which you must author regardless). **No edit to** ``resolve()`` / ``dry_run()`` /
``PlanEntry`` serialization / ``apply()`` **dispatch is required** — they iterate the
registry. This is deliberately a *registry*, **not** a big-bang visitor rewrite: every leaf
behaviour function stays exactly where and what it was; only the dispatch is centralized.

**Import layering.** ``dry_run`` structurally calls ``resolve`` (preview sits above resolve),
and ``apply`` sits above preview — so a single table naming all three layers' functions sits
*above* all of them. The four public entry points therefore reach this registry via a
**lazy** ``from larkdocio.write import ops`` inside their bodies (module cached after the
first call), which keeps this module free to import their leaf functions at load without a
circular import. Nothing here opens a socket or changes any leaf behaviour.
"""
from dataclasses import dataclass, replace
from typing import Callable, Dict, Tuple

from larkdocio.errors import LarkConfigError
from larkdocio.write.model import (
    CreateCommentRequest,
    DeleteRequest,
    EditRequest,
    GrowTableRequest,
    InsertRequest,
    Refusal,
    RemoveCommentRequest,
    SubSpanEditRequest,
    TableLocator,
    _anchor_from_dict,
    _content_from_dict,
)
from larkdocio.write.resolve import (
    ResolvedCell,
    ResolvedInsertion,
    _resolve_delete,
    _resolve_grow_table,
    _resolve_insert,
    _resolve_subspan,
    _resolve_whole_block_edit,
    _resolve_whole_cell_edit,
)
from larkdocio.write.preview import (
    PlanEntry,
    _preview_delete,
    _preview_edit,
    _preview_grow_table,
    _preview_insert,
    _preview_subspan,
)
from larkdocio.write.apply import (
    _apply_delete,
    _apply_grow_table,
    _apply_insert,
    _apply_narrative,
    _apply_subspan,
    _apply_table_cell,
)
from larkdocio.write.comments import (
    _apply_comment_create,
    _apply_comment_remove,
    _deserialize_comment_create,
    _deserialize_comment_remove,
    _preview_comment_create,
    _preview_comment_remove,
    _resolve_comment_create,
    _resolve_comment_remove,
    _serialize_comment_create,
    _serialize_comment_remove,
)


# --------------------------------------------------------------------------- #
# The two "edit" sub-dispatch wrappers — an EditRequest splits table vs narrative #
# by ANCHOR type at resolve, and by CELL presence at apply. Both were inline       #
# branches in resolve()/apply(); lifted here verbatim so the registry entry for     #
# "edit" is a single callable like every other op (behaviour byte-identical).       #
# --------------------------------------------------------------------------- #

def _resolve_edit(request, root):
    """Resolve an :class:`~larkdocio.write.model.EditRequest`: a
    :class:`~larkdocio.write.model.TableLocator` anchor → the W2 table-cell resolver,
    otherwise the shared narrative-or-by-id text-target path (the former inline tail of
    ``resolve()``; LD-137 routed its non-table arm through the one anchor seam so a quote and
    an id reach the identical downstream semantics).

    **Both** arms are the *whole-rewrite* resolvers — the locating logic plus that path's own
    plan-time precondition, inline review anchors: the table arm is
    :func:`~larkdocio.write.resolve._resolve_whole_cell_edit` (the cell's locator plus the
    check on the inner block the patch rewrites) and the non-table arm is
    :func:`~larkdocio.write.resolve._resolve_whole_block_edit`. Both are deliberately narrower
    than the bare locating layers they wrap, and the sub-span op resolves through the shared
    seam *without* the precondition, because splitting runs is exactly what lets it honor the
    anchors. The two whole-rewrite arms refuse with the **same** reason and different
    ``detail`` recoveries — a cell cannot be sub-span-edited through its locator, only through
    its inner block's id."""
    anchor = request.anchor
    if isinstance(anchor, TableLocator):
        return _resolve_whole_cell_edit(anchor, root)
    return _resolve_whole_block_edit(anchor, root)


def _apply_edit(entry, client, document_id):
    """Apply a resolved **edit** entry: a table cell (``entry.cell`` present) → the
    DOUBLE-re-validation table path, otherwise the single-re-validation narrative path
    (the former inline ``elif entry.cell is not None`` / ``else`` branches of ``apply()``)."""
    if entry.cell is not None:
        return _apply_table_cell(entry, client, document_id)
    return _apply_narrative(entry, client, document_id)


# --------------------------------------------------------------------------- #
# Per-op serialize / deserialize — the op-specific fields of PlanEntry.to_dict /  #
# from_dict, one function per op (the former per-op branches of those methods).    #
# Each serialize() returns ONLY the op's own fields, in the SAME order the former  #
# to_dict emitted them; serialize_entry() prepends the shared {outcome, anchor}    #
# (+ the "op" tag for every op except the tagless "edit") — so the wire format is  #
# byte-identical (B2).                                                             #
#                                                                                  #
# LD-137 adds ONE optional trailing field, `precondition_text`, emitted only for a  #
# resolved BY-ID entry (an id anchor has no quote to re-validate, so the plan        #
# carries the block's captured live-basis text instead). A quote-anchored entry      #
# carries None and the key is omitted, so every shipped wire form stays              #
# byte-identical.                                                                    #
# --------------------------------------------------------------------------- #

def _serialize_precondition(entry, d: dict) -> None:
    """Append ``precondition_text`` to ``d`` when the entry carries one (LD-137).

    Trailing + conditional so a quote-anchored entry's JSON is byte-unchanged. One helper,
    used by every op that captures a precondition, so the key can never be spelled or
    positioned differently per op.
    """
    if entry.precondition_text is not None:
        d["precondition_text"] = entry.precondition_text


def _serialize_edit(entry) -> dict:
    d: dict = {"replacement": entry.replacement}
    if entry.is_resolved:
        d["block_id"] = entry.block_id
        d["before"] = entry.before
        d["after"] = entry.after
        if entry.cell is not None:
            d["cell"] = entry.cell.to_dict()
        _serialize_precondition(entry, d)
    else:
        d["refusal"] = entry.refusal.to_dict() if entry.refusal else None
    # LD-574's checkbox state — trailing + conditional, on BOTH outcomes, so an edit that
    # does not move the bit serializes byte-identically to every plan written before it and
    # a refused one still shows the approver what was asked for.
    if entry.todo_done is not None:
        d["todo_done"] = entry.todo_done
    return d


def _deserialize_edit(anchor, d, resolved) -> PlanEntry:
    replacement = d["replacement"]
    if resolved:
        cell = ResolvedCell.from_dict(d["cell"]) if d.get("cell") is not None else None
        return PlanEntry.resolved(
            anchor=anchor,
            replacement=replacement,
            block_id=d["block_id"],
            before=d["before"],
            after=d["after"],
            cell=cell,
            precondition_text=d.get("precondition_text"),
            todo_done=d.get("todo_done"),
        )
    return PlanEntry.refused(anchor=anchor, replacement=replacement,
                             refusal=Refusal.from_dict(d["refusal"]),
                             todo_done=d.get("todo_done"))


def _serialize_insert(entry) -> dict:
    d: dict = {"position": entry.position, "content": [p.to_dict() for p in entry.content]}
    if entry.is_resolved:
        d["block_id"] = entry.block_id
        d["insertion_point"] = entry.insertion_point.to_dict() if entry.insertion_point else None
        _serialize_precondition(entry, d)
    else:
        d["refusal"] = entry.refusal.to_dict() if entry.refusal else None
    return d


def _deserialize_insert(anchor, d, resolved) -> PlanEntry:
    # ONE content registration point (LD-134): `_content_from_dict` tells the kind-tagged
    # NewBlock from the tagless NewParagraph, so a new creatable kind never touches this
    # op descriptor — the same discipline the op registry itself enforces for ops.
    content = tuple(_content_from_dict(p) for p in d.get("content", []))
    position = d.get("position")
    if resolved:
        ip = (
            ResolvedInsertion.from_dict(d["insertion_point"])
            if d.get("insertion_point") is not None
            else None
        )
        return PlanEntry.insert_resolved(
            reference=anchor, content=content, position=position, block_id=d["block_id"],
            insertion_point=ip, precondition_text=d.get("precondition_text"),
        )
    return PlanEntry.insert_refused(
        reference=anchor, content=content, position=position, refusal=Refusal.from_dict(d["refusal"])
    )


def _serialize_subspan(entry) -> dict:
    d: dict = {"span": entry.span, "replacement": entry.replacement}
    if entry.is_resolved:
        d["block_id"] = entry.block_id
        d["before"] = entry.before   # == span
        d["after"] = entry.after     # == replacement
        # LD-150 / dogfood F16: the sub-span family joins the other three in disclosing its
        # by-id compare-and-swap basis. Trailing + conditional, so a quote-anchored sub-span's
        # shipped JSON is byte-unchanged.
        _serialize_precondition(entry, d)
    else:
        d["refusal"] = entry.refusal.to_dict() if entry.refusal else None
    return d


def _deserialize_subspan(anchor, d, resolved) -> PlanEntry:
    span = d["span"]
    replacement = d["replacement"]
    if resolved:
        return PlanEntry.subspan_resolved(
            anchor=anchor, span=span, replacement=replacement, block_id=d["block_id"],
            precondition_text=d.get("precondition_text"),
        )
    return PlanEntry.subspan_refused(
        anchor=anchor, span=span, replacement=replacement, refusal=Refusal.from_dict(d["refusal"])
    )


def _serialize_grow_table(entry) -> dict:
    """The table-grow op's own wire fields (LD-575).

    ``grow`` carries the request (so a refused entry still shows which index was asked for);
    a resolved entry adds the resolved table's ``block_id`` and the grid in ``before`` /
    ``after``. No ``precondition_text``: a grow rewrites no text, so there is nothing for a
    per-entry compare-and-swap to hold.
    """
    d: dict = {"grow": entry.grow.to_dict() if entry.grow else None}
    if entry.is_resolved:
        d["block_id"] = entry.block_id
        d["before"] = entry.before
        d["after"] = entry.after
    else:
        d["refusal"] = entry.refusal.to_dict() if entry.refusal else None
    return d


def _deserialize_grow_table(anchor, d, resolved) -> PlanEntry:
    request = GrowTableRequest.from_dict(d["grow"])
    if resolved:
        return PlanEntry.grow_table_resolved(
            anchor=anchor, request=request, block_id=d["block_id"],
            before=d["before"], after=d["after"],
        )
    return PlanEntry.grow_table_refused(
        anchor=anchor, request=request, refusal=Refusal.from_dict(d["refusal"]))


def _serialize_delete(entry) -> dict:
    d: dict = {}
    if entry.is_resolved:
        d["block_id"] = entry.block_id
        d["before"] = entry.before
        _serialize_precondition(entry, d)
    else:
        d["refusal"] = entry.refusal.to_dict() if entry.refusal else None
    return d


def _deserialize_delete(anchor, d, resolved) -> PlanEntry:
    if resolved:
        return PlanEntry.delete_resolved(
            target=anchor, block_id=d["block_id"], before=d["before"],
            precondition_text=d.get("precondition_text"),
        )
    return PlanEntry.delete_refused(target=anchor, refusal=Refusal.from_dict(d["refusal"]))


# --------------------------------------------------------------------------- #
# The op-descriptor registry — THE single registration seam                       #
# --------------------------------------------------------------------------- #

#: **What a docx write op writes** — the criterion that separates the document BODY from the
#: review conversation laid over it, carried on the registry rather than re-typed wherever the
#: question is asked (LD-586). It is the same distinction
#: :attr:`larkdocio.write.preview.PlanEntry.is_comment` asks per plan entry, hoisted to the
#: registration seam so it can be asked of a *family* — which is what
#: :func:`larkdocio.write.absences._docx_body_request_families` needs to answer
#: "which families write the body?" **by reading the registry** instead of hand-listing them.
DOCUMENT_BODY = "document-body"
REVIEW_CONVERSATION = "review-conversation"

#: **THE** enumeration of write targets. A descriptor whose ``writes`` is not one of these is
#: refused at construction, so a new op cannot join the registry without answering the
#: question — the failure mode LD-586 fixed was an op joining and the answer not moving.
WRITE_TARGETS: Tuple[str, ...] = (DOCUMENT_BODY, REVIEW_CONVERSATION)


@dataclass(frozen=True)
class OpDescriptor:
    """One write op's complete dispatch record — everything the four chains need.

    * ``kind`` — the op-string discriminator carried on :class:`~larkdocio.write.preview.PlanEntry`
      (``"edit"`` / ``"insert"`` / ``"delete"`` / ``"subspan"``);
    * ``request_type`` — the concrete request class :func:`classify` matches (``isinstance``);
    * ``anchor_field`` — the **name of the request field that carries the anchor**
      (``"reference"`` for insert, ``"target"`` for delete, ``"anchor"`` for edit /
      sub-span). Added by LD-137 so the *anchor kinds* a family accepts can be **projected**
      off that field's own annotation (see
      :func:`larkdocio.capabilities.capabilities`) instead of hand-listed in the discovery
      layer — widen a family's anchor union and the registry follows automatically;
    * ``writes`` — **what this op writes**, one of :data:`WRITE_TARGETS`
      (:data:`DOCUMENT_BODY` or :data:`REVIEW_CONVERSATION`). Added by LD-586 for the same
      reason ``anchor_field`` was: so "which request families write the document body?" is
      **derived from this registry** rather than hand-listed somewhere else and left behind
      when a family joins. Register an op and its family joins that answer by existing.
    * ``resolve`` — ``(request, root) -> ResolvedTarget | Refusal``;
    * ``preview`` — ``(request, result) -> PlanEntry``;
    * ``apply`` — ``(entry, client, document_id) -> ApplyLogEntry`` (a resolved entry only —
      the op-agnostic *refused* case is handled once in ``apply()``);
    * ``serialize`` — ``(entry) -> dict`` of the op's own wire fields, in emission order;
    * ``deserialize`` — ``(anchor, d, resolved) -> PlanEntry`` rebuilding the entry from JSON.

    To add an op: author its five callables and append **one** ``OpDescriptor`` to
    :data:`OPS`. The chains pick it up with no dispatch edits.
    """

    kind: str
    request_type: type
    anchor_field: str
    writes: str
    resolve: Callable
    preview: Callable
    apply: Callable
    serialize: Callable
    deserialize: Callable

    def __post_init__(self):
        """A write target outside :data:`WRITE_TARGETS` is refused here rather than silently
        dropping the op out of every derivation that reads the field."""
        if self.writes not in WRITE_TARGETS:
            raise LarkConfigError(
                "Op %r declares writes=%r, which is not one of %s. Every op says whether it "
                "writes the document body or the review conversation laid over it; the "
                "answer is read off this registry."
                % (self.kind, self.writes, ", ".join(repr(t) for t in WRITE_TARGETS))
            )


#: The ordered registry. ``classify`` scans it top-to-bottom by ``isinstance``; ``edit``
#: (:class:`~larkdocio.write.model.EditRequest`) is last and also the fallback kind, matching
#: the former ``resolve()`` / ``dry_run()`` ``else``-is-edit behaviour exactly.
OPS: Tuple[OpDescriptor, ...] = (
    OpDescriptor(
        kind="insert", request_type=InsertRequest, anchor_field="reference",
        writes=DOCUMENT_BODY,
        resolve=_resolve_insert, preview=_preview_insert, apply=_apply_insert,
        serialize=_serialize_insert, deserialize=_deserialize_insert,
    ),
    OpDescriptor(
        kind="delete", request_type=DeleteRequest, anchor_field="target",
        writes=DOCUMENT_BODY,
        resolve=_resolve_delete, preview=_preview_delete, apply=_apply_delete,
        serialize=_serialize_delete, deserialize=_deserialize_delete,
    ),
    OpDescriptor(
        kind="subspan", request_type=SubSpanEditRequest, anchor_field="anchor",
        writes=DOCUMENT_BODY,
        resolve=_resolve_subspan, preview=_preview_subspan, apply=_apply_subspan,
        serialize=_serialize_subspan, deserialize=_deserialize_subspan,
    ),
    # LD-202 — the two comment ops. They sit BEFORE ``edit`` for the same reason insert /
    # delete / subspan do: ``edit`` is also the ``else`` fallback, so anything after it is
    # unreachable. Their anchor fields differ from each other (a create points at the whole
    # document, a removal at one thread), which is exactly what the ``anchor_field``
    # projection exists to carry.
    OpDescriptor(
        kind="comment-create", request_type=CreateCommentRequest, anchor_field="anchor",
        writes=REVIEW_CONVERSATION,
        resolve=_resolve_comment_create, preview=_preview_comment_create,
        apply=_apply_comment_create,
        serialize=_serialize_comment_create, deserialize=_deserialize_comment_create,
    ),
    OpDescriptor(
        kind="comment-remove", request_type=RemoveCommentRequest, anchor_field="target",
        writes=REVIEW_CONVERSATION,
        resolve=_resolve_comment_remove, preview=_preview_comment_remove,
        apply=_apply_comment_remove,
        serialize=_serialize_comment_remove, deserialize=_deserialize_comment_remove,
    ),
    # LD-575 — the table-grow op. BEFORE ``edit`` for the same reason every op above is:
    # ``edit`` is also the ``else`` fallback, so a descriptor after it is unreachable and no
    # happy-path test would ever notice. Its anchor field accepts a DIFFERENT union from every
    # other family's (the table's own id, or a table locator — never a quote, since a table
    # carries no text of its own), which is exactly what the ``anchor_field`` projection
    # exists to carry.
    OpDescriptor(
        kind="grow-table", request_type=GrowTableRequest, anchor_field="anchor",
        writes=DOCUMENT_BODY,
        resolve=_resolve_grow_table, preview=_preview_grow_table, apply=_apply_grow_table,
        serialize=_serialize_grow_table, deserialize=_deserialize_grow_table,
    ),
    OpDescriptor(
        kind="edit", request_type=EditRequest, anchor_field="anchor",
        writes=DOCUMENT_BODY,
        resolve=_resolve_edit, preview=_preview_edit, apply=_apply_edit,
        serialize=_serialize_edit, deserialize=_deserialize_edit,
    ),
)

BY_KIND: Dict[str, OpDescriptor] = {d.kind: d for d in OPS}

#: The fallback kind for an unrecognized request type — preserves the former
#: ``else``-branch-is-edit semantics of ``resolve()`` / ``dry_run()``.
_DEFAULT_KIND = "edit"


# --------------------------------------------------------------------------- #
# The generic dispatchers the four public chains delegate to                      #
# --------------------------------------------------------------------------- #

def classify(request) -> str:
    """The op kind for ``request`` — the ONE ordered ``isinstance`` ladder resolve and
    dry_run share (they can no longer disagree). Falls back to ``"edit"`` for any request
    type not otherwise matched, exactly as both former chains' ``else`` branch did."""
    for desc in OPS:
        if isinstance(request, desc.request_type):
            return desc.kind
    return _DEFAULT_KIND


def descriptor_for(request) -> OpDescriptor:
    """The :class:`OpDescriptor` for ``request`` (via :func:`classify`)."""
    return BY_KIND[classify(request)]


def resolve_dispatch(request, root):
    """Resolve ``request`` through its op's resolver (the body of ``resolve()``)."""
    return descriptor_for(request).resolve(request, root)


def preview_dispatch(request, result) -> PlanEntry:
    """Build the plan entry for ``request`` + its resolved ``result`` (the per-request body
    of ``dry_run()``)."""
    return descriptor_for(request).preview(request, result)


def apply_dispatch(entry, client, document_id):
    """Apply one **resolved** plan ``entry`` through its op's write path (the resolved arm
    of ``apply()``; the refused arm is op-agnostic and stays in ``apply()``)."""
    return BY_KIND[entry.op].apply(entry, client, document_id)


def serialize_entry(entry) -> dict:
    """Serialize a :class:`~larkdocio.write.preview.PlanEntry` to its wire dict.

    The shared ``{outcome, anchor}`` head, then the ``"op"`` tag for every op **except**
    the tagless ``"edit"`` (whose W1/W2 form carries no tag — byte-compatibility), then the
    op's own fields from its ``serialize`` callable. Field order matches the former
    per-op ``PlanEntry.to_dict`` exactly (B2)."""
    desc = BY_KIND[entry.op]
    d: dict = {"outcome": entry.outcome, "anchor": entry.anchor.to_dict()}
    if entry.op != _DEFAULT_KIND:
        d["op"] = entry.op
    d.update(desc.serialize(entry))
    # LD-172 — `preview_note` is emitted HERE rather than in a per-op serializer, because it is
    # op-agnostic by nature: any op may earn a non-refusing disclosure, and a field wired into
    # one op's serializer would silently not round-trip for the next. Trailing + conditional, so
    # an entry that earns no note serializes byte-identically to every shipped plan.
    if entry.preview_note is not None:
        d["preview_note"] = entry.preview_note
    return d


def deserialize_entry(d: dict) -> PlanEntry:
    """Rebuild a :class:`~larkdocio.write.preview.PlanEntry` from its wire dict — the op is
    read from the ``"op"`` tag (absent ⇒ the tagless ``"edit"``), then its ``deserialize``
    callable reconstructs the entry (the body of ``PlanEntry.from_dict``).

    An **unrecognized** ``"op"`` tag fails loud — a :class:`~larkdocio.errors.LarkConfigError`
    on the registry lookup miss — which is a deliberate, accepted change from the pre-LD-097
    ``PlanEntry.from_dict``, whose ``else`` branch silently coerced any unknown op to DELETE
    (the dangerous behavior: a corrupt wire dict would have been applied as a deletion)."""
    anchor = _anchor_from_dict(d["anchor"])
    op = d.get("op", _DEFAULT_KIND)
    resolved = d["outcome"] == "resolved"
    try:
        desc = BY_KIND[op]
    except KeyError:
        raise LarkConfigError(f"unknown write op {op!r} in serialized plan entry") from None
    entry = desc.deserialize(anchor, d, resolved)
    # The mirror of `serialize_entry`'s op-agnostic tail (LD-172): restored once, here, so no
    # per-op deserializer has to know about a disclosure that belongs to none of them.
    note = d.get("preview_note")
    if note is not None:
        entry = replace(entry, preview_note=note)
    return entry
