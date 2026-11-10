"""Turn a reconciliation plan into the write requests the SHIPPED engine already applies.

This is **a compiler, not an engine**. Everything it needs shipped long before the
reconciler did: :class:`~larkdocio.write.model.EditRequest` /
:class:`~larkdocio.write.model.InsertRequest` / :class:`~larkdocio.write.model.DeleteRequest`,
:class:`~larkdocio.write.model.AnchorById`'s exactly-one-or-refuse, the mandatory
:func:`~larkdocio.write.preview.dry_run` → :func:`~larkdocio.write.apply.apply` gate with
its non-forgeable plan and apply-log, :func:`~larkdocio.write.encode.encode_content` /
:func:`~larkdocio.write.encode.create_batches` and their
:data:`~larkdocio.write.model.MAX_CHILDREN_PER_CALL` limit, and the ``STALE_DOCUMENT``
whole-document compare-and-swap. So this module **adds none of it**: no new request type,
no new apply path, no second gate.

    >>> plan = reconcile(projection, edited_markdown)      # doctest: +SKIP
    >>> requests = compile_reconciliation(plan, projection)  # doctest: +SKIP
    >>> preview = dry_run(requests, root, document_revision_id=rev)  # doctest: +SKIP
    >>> log = apply(preview, client, document_id)          # doctest: +SKIP

Four properties are the whole contract, and each closes a way of getting this wrong.

**1. Identity, never geometry.** Every anchor is an
:class:`~larkdocio.write.model.AnchorById` naming a block the projection itself emitted.
A quote anchor would re-derive identity from text the reconciler already matched, and a
freshly created block's id is not knowable at compile time — so **no compiled request can
target content another request in the same batch creates.** That is the batch-blindness
the shipped engine documents in :mod:`larkdocio.write.intrabatch`, honored by
construction rather than asserted afterwards.

**2. The order the batch is emitted in is the engine's index semantics, not the plan's
reading order.** The engine computes an insertion **index** at plan time, off the
pre-batch tree, and applies it verbatim; a delete locates its target in the **live**
parent. So a batch is emitted as: every edit (id-anchored and index-free), then every
insert **bottom-up** — the latest document position first, so no insert can shift an
index a later insert in the same batch already had computed — then every delete, last,
because a delete shifts every index below it. Consecutive inserts that share an anchor
and a side are **one** request carrying several blocks, which is also the only shape in
which the engine's own batching has anything to split.

**3. Markers never reach Lark, and the two paths are guarded separately** because LD-197
proved the hazard is asymmetric. On the **insert** path
:func:`~larkdocio.write.compose.compose` already refuses marker-bearing Markdown outright
(raw HTML is in :data:`~larkdocio.write.compose.NOT_EXPRESSIBLE_CONSTRUCTS`). On the
**edit** path there is no such barrier: a replacement is a plain string nobody parses, and
Lark stores marker-shaped text **verbatim** — proven live. And *both* paths share one
remaining route in, because the projection **escapes** literal text: an escaped
marker-shaped string decodes back to a real marker on its way through the dialect. So every
compiled body — edit replacement, inserted block text, authored table cell — goes through
:func:`~larkdocio.model.projection.find_emitted_block_id_marker`, the **marker-set-aware**
question, asked in both domains and **at any position**: a marker for an identifier *this
projection emitted*, on a line of its own or in the middle of a sentence, **refuses** —
nothing is removed, because taking it out would silently rewrite prose nobody asked to
change. A marker-**shaped** string carrying anything else is the document's own writing and
survives exactly where it is. (Position-independence is LD-239: line-anchoring the question
let a marker ride a compiled body from mid-sentence. Reading an *edited projection* keeps
its line grammar — there a marker IS a line, and matching mid-sentence would delete a
consumer's prose.)

**4. Conservation is a hole in the batch, not a request — and a COUNTED change that would
compile to nothing REFUSES.** An unchanged block and a conserved opaque one compile to
**nothing at all** — not to a rewrite with the same value. A no-op reconciliation is
therefore an empty batch, and a reconciliation that edits one block of a hundred issues
exactly one request. The other half of that sentence is LD-574's: the reconciler counts a
change by comparing *decoded text*, which can differ where the writable content does not —
``- [ ] x`` versus ``- [x] x``, ``- a`` versus ``* a``, one code fence token versus another
— and such an entry used to compile to a request that rewrote the block with its own bytes
while the apply log said ``applied``. It now refuses, typed (``change-not-expressible``),
naming the property and the route that works. Two things make that safe rather than
trigger-happy: the ``done`` bit is **writable** as of the same change, so the case consumers
actually hit is a write and not a refusal; and the comparison is made by composing **both**
images through the dialect's own :func:`~larkdocio.write.compose.compose`, never by a second
pattern here, so a document nobody edited cannot be refused.

**The escaping policy — one policy, one inverse, applied by both directions** (LD-454). The
projection escapes literal text so a document's own marker-shaped prose cannot forge an
identity marker; every escape it writes has to be undone again on the way back, or a line
the caller never touched is written to Lark **in its escaped form, as authored intent**.
The inverse is mostly free: :func:`~larkdocio.write.compose.compose` parses the edited
Markdown with the dialect's own parser, and that parser resolves backslash escapes for a
paragraph, a list item, a quote, a heading and a table cell as part of reading them. It
does **not** in a **verbatim** context — inside a fenced code block a backslash is a
backslash, to markdown-it and to CommonMark itself — so this module applies
:func:`~larkdocio.model.renderer.unescape_literals` to exactly the composed kinds named in
:data:`VERBATIM_KINDS`, at the one seam where every compiled body passes
(:func:`_decoded_verbatim`), and nowhere else. Decoding the Markdown *before* composing it
would be the opposite error: escaped literal text would turn back into markup and author a
heading where the editor wrote about one.

Two modules export ``unescape_literals`` — :mod:`larkdocio.model.projection` and
:mod:`larkdocio.model.renderer` — and after this fix that is still correct, because it is
**one function**: the escaper lives in the renderer beside its inverse, and the projection
**re-exports** it (``model/projection.py``'s import list) so a reader of the projection API
does not have to know that. Two independently-written inverses is what would let the codec
drift apart half at a time, and that is what this rung must never grow; the identity is
pinned by a test (in the source repository) rather than left to habit.

The **whole-document staleness guard is inherited, not re-implemented**: pass the
``revision_id`` the projection was read at to :func:`~larkdocio.write.preview.dry_run` and
any drift under the plan refuses the whole batch with zero writes. This module deliberately
offers no second place to put it.
"""
from dataclasses import replace
from typing import List, Optional, Sequence, Tuple, Union

from larkdocio.model.projection import BlockIdProjection, find_emitted_block_id_marker
from larkdocio.model.renderer import unescape_literals
from larkdocio.errors import LarkEscapeError
from larkdocio.write.compose import compose
from larkdocio.write.intrabatch import COMMIT_THEN_ANCHOR_RULE
from larkdocio.write.model import (
    MAX_CHILDREN_PER_CALL,
    AnchorById,
    DeleteRequest,
    EditRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    NewBlockKind,
    NewParagraph,
    Refusal,
    RefusedError,
)
from larkdocio.write.reconcile import ReconciliationPlan, ReconciliationState

__all__ = [
    "COMPILED_REQUEST_FAMILIES",
    "EDIT_UNWRITABLE_BLOCK_FIELDS",
    "EDIT_WRITABLE_BLOCK_FIELDS",
    "RECONCILIATION_COMPILER_CONTRACT",
    "VERBATIM_KINDS",
    "compile_reconciliation",
]

#: What a whole-block edit can actually WRITE, named as the composed block's own field
#: names. ``text`` is :attr:`EditRequest.replacement`; ``done`` is the block ``PATCH``
#: endpoint's ``update_text_style`` oneof, shipped by LD-574 as
#: :attr:`EditRequest.todo_done`.
EDIT_WRITABLE_BLOCK_FIELDS = frozenset({"text", "done"})

#: **The residual, enumerated** (LD-574) — every other field a composed block can carry, so
#: "which changes can this operation not express?" is answered by a list rather than by a
#: feeling. A negative claim dies with its enumeration, and this one is held against
#: :class:`~larkdocio.write.model.NewBlock`'s own dataclass fields by a guard, so a tenth
#: authoring field cannot arrive unplaced. Derivation, per member:
#:
#: * ``kind`` / ``level`` — refused **upstream**, at reconcile time: ``_block_type()``
#:   classifies both images through ``compose()`` and a difference is
#:   ``block-type-mutation`` (a heading2 and a heading3 are different Lark block types);
#: * ``children`` / ``rows`` — refused **here**, by :func:`_expressible_as_one_block`: a
#:   nested subtree or a table is blocks of its own, not one block's text;
#: * ``header_row`` — ``TABLE`` only, and a composed table always carries ``rows``, so it
#:   never reaches this comparison without the ``rows`` refusal firing first;
#: * ``language`` — ``CODE`` only, and **the residual instance**: two fences differing only
#:   in their token compose to the same kind, level and text, so before LD-574 the compiled
#:   request rewrote the body with itself and the language did not move;
#: * ``theme`` — ``MERMAID`` only, reachable the same way ``language`` is;
#: * ``spans`` — created runs are unstyled and the dialect's parser emits no span, so this is
#:   only reachable through a hand-built plan; it is enumerated rather than assumed absent.
#:
#: Every member is covered by the same refusal, because the consumer-visible fact is one
#: fact: the compiled request would write nothing new.
EDIT_UNWRITABLE_BLOCK_FIELDS = frozenset({
    "kind", "level", "language", "children", "rows", "header_row", "theme", "spans",
})

#: The composed kinds whose text the DIALECT does not decode for us — the one moving part
#: of the escaping policy (see the module docstring, § the escaping policy). A fenced code
#: block's body is verbatim to CommonMark itself: inside it a backslash is a backslash, so
#: the projection's escape survives ``compose()`` and would reach Lark as authored intent.
#: Named once, here, rather than open-coded at each call site — a second spelling of "which
#: contexts are verbatim" is the shape of the defect this closes (LD-454).
VERBATIM_KINDS = frozenset({NewBlockKind.CODE})

#: The request families a reconciliation compiles to — **the shipped ones, and only
#: those**. Named as the classes themselves rather than as strings so "did a fourth family
#: appear?" is a question about real types the engine already dispatches on.
COMPILED_REQUEST_FAMILIES = (EditRequest, InsertRequest, DeleteRequest)

#: What compiling a reconciliation promises, shipped WITH the answer — a consumer holding
#: only the wheel cannot open the document these rules were written in.
RECONCILIATION_COMPILER_CONTRACT = (
    "A reconciliation plan compiles to the write engine's own shipped request families "
    "and to nothing else: an edit, an insert or a delete, every one of them anchored by "
    "block id against a block the projection itself emitted. Nothing is compiled for an "
    "unchanged or a conserved block, so a no-op reconciliation is an empty batch and a "
    "one-block edit is one request. A change the reconciler counted but this compiler "
    "cannot write is REFUSED rather than compiled: an edit whose only difference is a "
    "property a whole-block replacement does not carry — a code fence's language, a "
    "nesting change, a Markdown respelling of the same block — and added content that "
    "composes to no block at all both refuse with change-not-expressible, naming the "
    "property and the two-commit route, because a green apply log is a receipt and an "
    "entry that would write bytes identical to what is live must never become one. A "
    "todo's checkbox is NOT in that residual: an edited projection whose checkbox was "
    "flipped compiles to an edit that carries the bit and moves it. "
    "No compiled request targets content another request "
    "in the same batch creates. No compiled body carries an identity marker for a block "
    "this projection emitted — on the insert path the authoring compiler already refuses "
    "marker-bearing Markdown, and on the edit path, where a replacement is a plain string "
    "nobody parses and Lark stores marker-shaped text verbatim, a marker for an emitted "
    "block anywhere in the text is refused: on a line of its own or in the middle of a "
    "sentence, in the text as written or in its escaped form, and nothing is quietly "
    "rewritten to make it fit. Marker-shaped prose that names no emitted block survives as "
    "the content it is. The batch goes through the shipped dry-run gate unchanged, and "
    "the whole-document revision guard is the engine's own: pass the revision the "
    "projection was read at and any drift refuses the whole batch with zero writes. "
    + COMMIT_THEN_ANCHOR_RULE
)

_Request = Union[EditRequest, InsertRequest, DeleteRequest]


def compile_reconciliation(
    plan: ReconciliationPlan,
    projection: BlockIdProjection,
) -> Tuple[_Request, ...]:
    """Compile ``plan`` into the batch of shipped write requests that realizes it.

    ``projection`` is the one the plan was reconciled against: its emitted identifiers are
    what makes an anchor legitimate and what the marker guard is aware of, so it is the
    input rather than a bare id list a caller could get wrong.

    Returns the requests in the order they must be **issued** (see the module docstring —
    it is the engine's index semantics, not the plan's reading order). Hand them to
    :func:`~larkdocio.write.preview.dry_run` with the document revision and then to
    :func:`~larkdocio.write.apply.apply`: there is no second gate here and no apply path of
    its own.

    Raises :class:`~larkdocio.write.model.RefusedError` — carrying the typed refusal — for
    a plan that refused (there is nothing to compile), and for the one compile-time
    refusal this rung owns: a body that would have carried an identity marker.
    """
    if not isinstance(plan, ReconciliationPlan):
        raise TypeError(
            "compile_reconciliation() takes the ReconciliationPlan reconcile() returned, "
            f"got {type(plan).__name__}"
        )
    if not isinstance(projection, BlockIdProjection):
        raise TypeError(
            "compile_reconciliation() takes the BlockIdProjection the plan was "
            f"reconciled against, got {type(projection).__name__}"
        )
    if not plan.ok:
        raise RefusedError(plan.refusals[0])

    known = projection.block_ids
    edits: List[EditRequest] = []
    inserts: List[InsertRequest] = []
    deletes: List[DeleteRequest] = []
    #: consecutive inserts sharing an anchor + side are ONE request (see the docstring).
    group_key: Optional[Tuple[Optional[str], str]] = None
    group: List[object] = []
    groups: List[Tuple[Tuple[Optional[str], str], List[object]]] = []

    for entry in plan.changes:
        if entry.state is ReconciliationState.INSERTED:
            key = (entry.anchor_block_id, entry.anchor_position)
            content = _content_for(entry, known)
            if key == group_key:
                group.extend(content)
            else:
                group = list(content)
                group_key = key
                groups.append((key, group))
            continue
        # Anything else closes the run of inserts: content the editor added between two
        # changed blocks is not the same insertion point as content after them.
        group_key = None
        if entry.state is ReconciliationState.EDITED:
            edits.append(_edit_for(entry, known))
        elif entry.state is ReconciliationState.DELETED:
            deletes.append(DeleteRequest(target=AnchorById(block_id=entry.block_id)))

    for key, content in groups:
        inserts.extend(_inserts_for(key, content, projection))

    # Bottom-up: the latest document position first, so no insert shifts an index a later
    # insert already had computed off the same pre-batch tree. Deletes last, for the
    # mirror reason: a delete shifts every index below it.
    return tuple(edits) + tuple(reversed(inserts)) + tuple(deletes)


# --------------------------------------------------------------------------- #
# One entry at a time.                                                         #
# --------------------------------------------------------------------------- #

def _edit_for(entry, known: Sequence[str]) -> EditRequest:
    """One ``edited`` entry → one whole-block :class:`EditRequest`.

    The replacement is the block's **text**, and the authoring compiler is what says what
    a piece of Markdown's text is — a heading's replacement is its title, not ``## title``.
    Deriving it here with a pattern of this module's own would be a second definition of
    the dialect, drifting from the one the reconciler already classified the block with.

    An edit carries **text** and, since LD-574, a ``todo``'s ``done`` bit; nothing else fits
    in it. Content that composes to a nested subtree, a table, or to several blocks that are
    not all plain paragraphs describes a shape one whole-block replacement cannot express —
    and approximating it (flattening a list into a run of lines) would rewrite the block into
    something the editor did not ask for. That refuses, naming the two-commit route that
    works.

    **And a counted change that compiles to nothing REFUSES here** — the compiled-no-op
    class (LD-574). The reconciler compares the two images' *decoded text*, which is the
    right question for "did anything change" and the wrong one for "can this be written":
    ``- [ ] x`` and ``- [x] x`` differ as text and used to compile to a replacement equal to
    the live text, so the plan was ``ok``, the apply log said ``applied``, and the checkbox
    did not move. The discrimination therefore belongs **here**, where the request is built
    and where :func:`~larkdocio.write.compose.compose` already defines what a block's text
    is: both images are composed by that one function, the writable projection
    (:data:`EDIT_WRITABLE_BLOCK_FIELDS`) is compared, and an entry whose write would be
    byte-identical to its own pre-image refuses instead of becoming a receipt for nothing. A
    second, parallel definition of the dialect's transforms would drift silently, which is
    the whole reason this is not a predicate of its own.
    """
    where = f"block {entry.block_id!r}"
    composed = _decoded_verbatim(compose(entry.after_markdown), where)
    if not _expressible_as_one_block(composed):
        raise RefusedError(Refusal.not_in_dialect(
            f"block {entry.block_id!r}: its edited Markdown is structure — "
            f"{_shape_of(composed)} — and an edit replaces one block's TEXT, so there is "
            f"no honest way to write it as one replacement; flattening it would rewrite "
            f"the block into something else. Nothing was compiled. Delete the block and "
            f"insert the replacement structure as two separate commits. "
            + COMMIT_THEN_ANCHOR_RULE
        ))
    pre_image = _composed_pre_image(entry, where)
    if pre_image is not None and _writable_image(pre_image) == _writable_image(composed):
        raise RefusedError(Refusal.change_not_expressible(
            _no_op_detail(entry.block_id, pre_image, composed)))
    return EditRequest(
        anchor=AnchorById(block_id=entry.block_id),
        replacement=_marker_guarded_text(
            "\n\n".join(item.text for item in composed),
            known,
            where,
        ),
        todo_done=_moved_done_bit(pre_image, composed),
    )


# --------------------------------------------------------------------------- #
# The compiled-no-op discrimination — one path, the dialect's own (LD-574).     #
# --------------------------------------------------------------------------- #

def _composed_pre_image(entry, where: str):
    """The block as it stands, composed by the **same** function as the edited image.

    ``None`` when the pre-image is not comparable, which is deliberately not treated as
    evidence of anything: an older serialized plan carries no ``before_markdown``, and a
    pre-image the dialect refuses is a plan the reconciler would already have refused (it
    classified both images through ``compose()`` to compare their block types). Failing open
    here is the choice that cannot produce a **false** refusal, which is the failure mode
    this whole rung is weighted against.
    """
    if not entry.before_markdown:
        return None
    try:
        return _decoded_verbatim(compose(entry.before_markdown), where)
    except (RefusedError, LarkEscapeError):
        return None


def _writable_image(composed):
    """Exactly what a whole-block edit would WRITE for ``composed`` — and nothing else.

    Read off the composed tree rather than the Markdown, so it is the request's own content
    by construction: the replacement string the engine sends, plus the ``done`` bit when the
    block is a todo. Two images with the same writable projection compile to the same bytes,
    whatever else about their Markdown differs.
    """
    return ("\n\n".join(item.text for item in composed), _done_bit_of(composed))


def _done_bit_of(composed):
    """The ``done`` state of ``composed`` when it is one todo block, else ``None``."""
    if len(composed) != 1:
        return None
    item = composed[0]
    if isinstance(item, NewBlock) and item.kind is NewBlockKind.TODO:
        return bool(item.done)
    return None


def _moved_done_bit(pre_image, composed):
    """The ``done`` bit to write — ``None`` unless it actually MOVES.

    Set only on a real flip, for two reasons that both matter. The engine writes one oneof
    per call, so an unconditional bit would double the write cost of every todo text edit;
    and a request carrying a value equal to the live one is exactly the no-op receipt this
    change exists to stop being possible.
    """
    after = _done_bit_of(composed)
    if after is None or pre_image is None:
        return None
    return after if after != _done_bit_of(pre_image) else None


def _no_op_detail(block_id, pre_image, composed) -> str:
    """The refusal's detail: the block, the property, and the route that works."""
    differing = _unwritable_differences(pre_image, composed)
    if differing:
        what = (
            f"the only difference is {', '.join(differing)}, which a whole-block edit does "
            f"not carry — it replaces the block's TEXT (and a todo's checkbox) and nothing "
            f"else"
        )
    else:
        what = (
            "the two spellings compose to the same block, so the edited Markdown differs "
            "only in a way the authoring dialect does not carry"
        )
    return (
        f"block {block_id!r}: {what}. The request this would compile to writes bytes "
        f"identical to what is already in the block, so applying it would report SUCCESS "
        f"for a change that never happened — and a green apply log is a receipt. Nothing "
        f"was compiled and no call was made. To make this change, delete the block and "
        f"insert the replacement as two separate commits (its identifier changes, and "
        f"anything anchored to it — comment anchors most pointedly — goes with it). "
        + COMMIT_THEN_ANCHOR_RULE
    )


def _unwritable_differences(pre_image, composed) -> Tuple[str, ...]:
    """The names of the composed-block properties that differ and cannot be written.

    Compared over :data:`EDIT_UNWRITABLE_BLOCK_FIELDS` — the enumerated residual — so the
    detail names a real property rather than gesturing at one, and a field that joins
    :class:`~larkdocio.write.model.NewBlock` without joining that enumeration reddens a
    guard rather than silently going unnamed.
    """
    if len(pre_image) != len(composed):
        return ("how many blocks the Markdown is",)
    names: List[str] = []
    for before, after in zip(pre_image, composed):
        for name in sorted(EDIT_UNWRITABLE_BLOCK_FIELDS):
            a, b = getattr(before, name, None), getattr(after, name, None)
            if a != b and name not in names:
                names.append(name)
    return tuple(names)


def _expressible_as_one_block(composed) -> bool:
    """Whether ``composed`` is text a single whole-block replacement can carry.

    One block of any kind is (its text is exactly what the dialect says it is — a
    heading's title, not ``## title``). Several are only when every one of them is a plain
    paragraph, which is what a block whose own text holds a blank line projects as.
    Children or table rows never are: those are blocks of their own.
    """
    if not composed:
        return False
    if any(getattr(item, "children", ()) or getattr(item, "rows", ()) for item in composed):
        return False
    return len(composed) == 1 or all(_is_paragraph(item) for item in composed)


def _is_paragraph(item) -> bool:
    return isinstance(item, NewParagraph) or item.kind is NewBlockKind.PARAGRAPH


def _shape_of(composed) -> str:
    kinds = [
        "paragraph" if isinstance(i, NewParagraph) else i.kind.value for i in composed
    ]
    nested = any(getattr(i, "children", ()) for i in composed)
    return (
        f"{len(kinds)} block(s) ({', '.join(kinds)})"
        + (" with nested children" if nested else "")
    )


def _content_for(entry, known: Sequence[str]) -> Tuple[object, ...]:
    """One ``inserted`` entry → the typed content to create.

    Compiled from the entry's **Markdown** rather than its decoded text: decoding first
    would turn escaped literal text back into markup and author a heading where the editor
    wrote about one. The dialect's parser then undoes the projection's escaping as it reads
    — except in a verbatim context, which :func:`_decoded_verbatim` closes.
    """
    where = (
        f"content inserted {entry.anchor_position} block {entry.anchor_block_id!r}"
        if entry.anchor_block_id
        else "content inserted at the top of the document"
    )
    composed = _decoded_verbatim(compose(entry.after_markdown), where)
    if not composed:
        # THE SECOND ARM of the compiled-no-op class, and it is reachable (LD-574):
        # `_inserts_for` emits one request per chunk of composed content, so content that
        # composes to ZERO blocks emits none — `change_count` counted a change and the batch
        # came out empty. A link-reference definition and a footnote
        # definition are such content: `compose()` returns an empty tuple for them and
        # raises nothing, because CommonMark consumes them as document metadata rather than
        # as a block. Refused with the same reason as the edit arm, because it is the same
        # consumer-visible fact.
        raise RefusedError(Refusal.change_not_expressible(
            f"{where}: the added Markdown "
            f"{entry.after_markdown.strip()!r} composes to no block at all — CommonMark "
            f"reads a link-reference or footnote definition as document metadata, not as "
            f"content, so there is nothing to create. The reconciliation counted it as a "
            f"change; compiling it would have produced an empty batch and a green run that "
            f"wrote nothing. Nothing was compiled. Write the content as a block — a "
            f"paragraph carrying the link inline, for instance — and re-run."
        ))
    return tuple(
        _marker_guarded_content(item, known, where) for item in composed
    )


def _inserts_for(key, content, projection: BlockIdProjection) -> List[InsertRequest]:
    """One group of adjacent inserted content → the :class:`InsertRequest`\\ s for it.

    A group wider than the engine's own per-call child limit is split **by that limit** —
    ``MAX_CHILDREN_PER_CALL``, imported, not a number of this module's own — into chunks
    that are then emitted bottom-up like any other insert.
    """
    anchor_block_id, position = key
    if anchor_block_id is None:
        # Content that arrived ahead of the first marker: the top of the document, which
        # is expressible as "before the first block the projection emitted". When that
        # first block is the page node itself — which is what a projection of a real tree
        # emits first — there IS no sibling position above it, and the shipped resolver
        # says so typed (``cannot-hold-siblings``, naming the position that works) at
        # dry-run time. Guessing a different anchor here would be this module inventing a
        # position the engine does not have.
        if not projection.block_ids:
            raise RefusedError(Refusal.not_in_dialect(
                "content was added ahead of the first marker, but the projection emitted "
                "no block to anchor it to — there is no block-level position in an empty "
                "document to insert relative to. Insert into a document that has at least "
                "one block."
            ))
        anchor_block_id, position = projection.block_ids[0], InsertPosition.BEFORE.value
    reference = AnchorById(block_id=anchor_block_id)
    return [
        InsertRequest(
            reference=reference,
            position=InsertPosition(position),
            content=tuple(content[start:start + MAX_CHILDREN_PER_CALL]),
        )
        for start in range(0, len(content), MAX_CHILDREN_PER_CALL)
    ]


# --------------------------------------------------------------------------- #
# The escaping policy's one seam — the inverse, where the dialect has none.     #
# --------------------------------------------------------------------------- #

def _decoded_verbatim(composed, where: str):
    """``composed`` with every VERBATIM body decoded out of the projection's escaping.

    The projection escapes literal text; :func:`~larkdocio.write.compose.compose` undoes
    that for free wherever the dialect's parser resolves backslash escapes as it reads —
    which is everywhere except a **verbatim** context (:data:`VERBATIM_KINDS`), where a
    backslash is a backslash by CommonMark's own rule. Left alone, a fenced code block's
    body reached Lark escaped: ``deploy rollback \\-\\-service $SERVICE`` written into a
    runbook line the caller never edited (LD-454).

    Applied through the composed **tree**, so a code block nested under a list item is
    decoded like a top-level one, and to nothing else: a table cell and a paragraph were
    already decoded by the parser, and decoding them twice would eat a literal backslash
    the editor meant.

    A body the escape policy could never have produced **refuses** rather than guesses —
    the reconciler's own rule for undecodable text (:func:`~larkdocio.write.reconcile`
    rule 3), applied at the last seam before a request is built. In practice a plan the
    reconciler produced cannot reach this: it decoded the same text to compare it, so an
    undecodable body refused there first. The guard is for a plan rebuilt from a dict.
    """
    return tuple(_decoded_item(item, where) for item in composed)


def _decoded_item(item, where: str):
    if isinstance(item, NewParagraph):
        return item
    if not isinstance(item, NewBlock):
        return item
    children = tuple(_decoded_item(c, where) for c in item.children)
    text = _decode_verbatim_text(item.text, where) if item.kind in VERBATIM_KINDS else item.text
    if text == item.text and children == item.children:
        return item
    return replace(item, text=text, children=children)


def _decode_verbatim_text(text: str, where: str) -> str:
    try:
        return unescape_literals(text)
    except LarkEscapeError as e:
        raise RefusedError(Refusal.undecodable_text(
            f"{where}: the verbatim body cannot be decoded out of the projection's "
            f"escaping — {e}. A fenced code block's text is written back through the "
            f"exact inverse of the escape the projection applied, and a backslash that "
            f"escape never emits means this text did not come from it. Nothing was "
            f"compiled; two readings are possible and neither is safe to assume."
        )) from e


# --------------------------------------------------------------------------- #
# The marker guard — the ONE guarantee on the edit path (AC6b).                #
# --------------------------------------------------------------------------- #

def _marker_guarded_text(text: str, known: Sequence[str], where: str) -> str:
    """``text`` unchanged — or a refusal, if it carries a marker for an **emitted** block.

    Two properties, and each closes a way of getting this wrong.

    **It is set-aware**, and the rule is
    :func:`~larkdocio.model.projection.find_emitted_block_id_marker`'s rather than a second
    one here: a marker naming an identifier this projection emitted is identity and cannot
    be written back as content, while a marker-**shaped** string naming anything else is
    the document's own prose and passes through untouched. The decoded form is checked too,
    because the projection escapes literal text and an escaped marker decodes back into a
    real one on its way through the dialect — a body the escape policy never produced is
    read as "not a marker" rather than as an error, because it is content.

    **It is position-independent** (LD-239). Here the text is arbitrary consumer prose that
    nobody parses and Lark stores verbatim, so a marker does not have to occupy a line of
    its own to reach the document — line-anchoring the question let one ride a compiled
    body from the middle of a sentence. Reading an *edited projection* is the other
    direction and keeps its line grammar (see
    :func:`~larkdocio.model.projection.strip_block_id_markers`): there a marker IS a line,
    and matching one mid-sentence would delete a consumer's prose.

    Nothing is removed either way — **it refuses**: handing back a body with the marker
    quietly taken out of it would be a silent rewrite of prose nobody asked to change, and
    this is exactly the document where a silent rewrite is unacceptable.
    """
    found = _emitted_marker_in(text, known)
    if found is not None:
        raise RefusedError(Refusal.not_in_dialect(
            f"{where}: the text carries an identity marker for {found!r}, a block this "
            f"document's projection emitted — anywhere in the text counts, on a line of "
            f"its own or in the middle of a sentence. A marker is identity, not content: "
            f"writing one into the document's own text would make the next projection "
            f"ambiguous, and taking it out quietly would rewrite content nobody asked to "
            f"change. Remove the marker from the text and re-run."
        ))
    return text


def _emitted_marker_in(text: str, known: Sequence[str]) -> Optional[str]:
    """The identifier of the first emitted-block marker in ``text``, raw or escaped.

    Line by line, so a body whose one undecodable line is content does not blind the check
    to the rest of it — a marker never spans a line break in either domain.
    """
    for line in text.splitlines():
        found = find_emitted_block_id_marker(line, known)
        if found is not None:
            return found
        try:
            decoded = unescape_literals(line)
        except LarkEscapeError:
            continue
        found = find_emitted_block_id_marker(decoded, known)
        if found is not None:
            return found
    return None


def _marker_guarded_cell(cell, known: Sequence[str], where: str):
    """The same guarantee over one table cell — plain text, or a span sequence.

    A cell authored as a sequence of :class:`~larkdocio.write.model.TextSpan` (the in-cell
    link anchor) is checked **span by span**, on the same rule: the anchor text is consumer
    prose that reaches the document verbatim, so a marker riding it is identity written back
    as content. **The link URL is not checked, and that is a fact rather than an omission:** a
    projected marker contains **spaces** — the shape is
    :data:`~larkdocio.model.renderer.BLOCK_ID_MARKER_RE`'s, never restated here — and a
    ``TextSpan`` refuses a URL with whitespace in it at construction, so no URL that can
    exist is able to carry one.
    """
    if isinstance(cell, str):
        return _marker_guarded_text(cell, known, where)
    return tuple(
        replace(span, text=_marker_guarded_text(span.text, known, where))
        for span in cell
    )


def _marker_guarded_content(item, known: Sequence[str], where: str):
    """The same guarantee, over authored content — its text, its children, its cells."""
    if isinstance(item, NewParagraph):
        return replace(item, text=_marker_guarded_text(item.text, known, where))
    if isinstance(item, NewBlock):
        return replace(
            item,
            text=_marker_guarded_text(item.text, known, where),
            children=tuple(
                _marker_guarded_content(c, known, where) for c in item.children
            ),
            rows=tuple(
                tuple(_marker_guarded_cell(cell, known, where) for cell in row)
                for row in item.rows
            ),
        )
    return item
