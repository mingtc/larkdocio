"""larkdocio.write.preview — the mandatory dry-run previewer (LD-067).

The gate that keeps the apply engine safe is a **mandatory dry-run**: a human (or a
consumer's approval UX) must see exactly what will change before anything is written,
and **no code path may apply an unresolved edit** (Decision (c)).

:func:`dry_run` takes a **batch** of write requests + the reader's **parsed node tree** and
runs each through the S2 resolver (:func:`~larkdocio.write.resolve.resolve`, LD-066),
producing a :class:`Plan` whose entries are 1:1 with the batch, in order. Every request
family the engine ships previews here — an :class:`~larkdocio.write.model.EditRequest`
(whole paragraph, or a table cell via a
:class:`~larkdocio.write.model.TableLocator`), an
:class:`~larkdocio.write.model.InsertRequest`, a
:class:`~larkdocio.write.model.DeleteRequest` and a
:class:`~larkdocio.write.model.SubSpanEditRequest` — dispatched through the one op-descriptor
registry (:mod:`larkdocio.write.ops`), so:

* each **resolved** request → a :class:`PlanEntry` carrying the target ``block_id`` and what
  would happen to it: before/after text for an edit, the content-to-create + its computed
  insertion point for an insert, the text-that-would-be-removed for a delete, the span +
  replacement for a sub-span edit;
* each **refused** request → a :class:`PlanEntry` carrying the typed
  :class:`~larkdocio.write.model.Refusal` (and still the intent, so an approval UX can show
  the rejected op).

It performs **zero writes** — it never touches a
:class:`~larkdocio.write.client.WriteClient`; its signature has no client at all, so it
*structurally cannot* write. Fully **offline**: it walks an already-parsed tree
(``before`` is the tree's text; the live re-validation at write time is S4's job — for an
:class:`~larkdocio.write.model.AnchorById` the plan also captures the
``precondition_text`` that re-validation compares against, LD-137/LD-141).

**The hard gate (co-verified at S4).** A :class:`Plan` is the **only** input the S4 apply
engine (LD-068) will accept — there is no "apply directly" entry point. So a plan must
be produced *here*, from the resolver, and cannot be **hand-forged**: :class:`Plan`'s
constructor is guarded by a module-private token, so ``Plan(...)`` from arbitrary
records raises — the *only* way to obtain a plan is :func:`dry_run`. The plan is
read-only/inspectable (:meth:`Plan.to_dict` / :meth:`~Plan.to_json`) so a consumer can
render the before/after preview + refusals for its own approval UX, but there is
deliberately **no** ``Plan.from_dict`` that reconstructs a *trusted* plan from JSON —
that would re-open the forge vector the hard gate closes. (A single :class:`PlanEntry`
record still round-trips via :meth:`PlanEntry.to_dict` / :meth:`~PlanEntry.from_dict`,
mirroring the S1 apply-log record, for inspection — but a bag of entries is not a Plan.)

**The whole-document staleness anchor (LD-139, D9).** ``dry_run`` also takes the
document's ``revision_id`` as a keyword, and the plan carries it plus a **never-silent**
:attr:`Plan.revision_guard` marker (``"active"`` / ``"unavailable"`` + the WHY, both derived,
never stored). Supplied, the apply engine turns it into a whole-batch compare-and-swap;
omitted, the plan says so out loud rather than looking guarded. It stays a scalar the caller
already holds — the previewer performs no read and so still structurally cannot write.

Depends only on S1 (:mod:`larkdocio.write.model`) and S2
(:mod:`larkdocio.write.resolve`) and the standard library.
"""
import json
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple, Union

from larkdocio.common.notes import combine_preview_notes, preview_notes_of
from larkdocio.write.model import (
    Anchor,
    AnchorById,
    CommentThread,
    CreateCommentRequest,
    GrowTableRequest,
    NarrativeAnchor,
    NewContent,
    Refusal,
    RemoveCommentRequest,
    TableLocator,
    WholeDocument,
)

#: :attr:`PlanEntry.preview_note` kind for a resolved **sub-span** edit whose target carries
#: **inline** review anchors — a reviewer has commented on particular words inside the block
#: this edit will rewrite. The one edit path that can proceed on such a target (the whole-block
#: and whole-cell paths refuse ``comment-anchors-present``), so the plan says so rather than
#: leaving an approver unaware that reviewers are involved.
NOTE_KIND_COMMENT_ANCHORS_ON_TARGET = "comment-anchors-present-on-target"

#: The anchor shapes an **edit** entry can carry — the narrative quote+breadcrumb
#: :class:`~larkdocio.write.model.Anchor`, the W2 table-cell
#: :class:`~larkdocio.write.model.TableLocator`, or the LD-137
#: :class:`~larkdocio.write.model.AnchorById`. Spelled out here (rather than reaching for a
#: model-level alias that does not exist) to match
#: :class:`~larkdocio.write.model.ApplyLogEntry`'s own annotation exactly: a plan entry and
#: its apply-log mirror carry the same anchor off the same request. Insert / delete /
#: sub-span are narrative-only and use :data:`~larkdocio.write.model.NarrativeAnchor`.
_EditAnchor = Union[Anchor, TableLocator, AnchorById]

#: The anchor shapes a :class:`PlanEntry` can carry — the **union over every request
#: family**, not one family's. Held identical to
#: :data:`~larkdocio.write.model.applylog.LoggedAnchor` by ``tests/test_dry_run_preview.py``
#: (a plan entry and its apply-log mirror carry the same anchor off the same request), and
#: identical to that union too, so a narrower-than-reality annotation — which is a lie a
#: machine reads, since ``capabilities()`` projects the advertised anchor kinds off these
#: hints — reddens the suite. Deliberately NOT the same alias as :data:`_EditAnchor`: an
#: *edit* family's factory must keep declaring what an edit accepts.
_AnyPlanAnchor = Union[Anchor, TableLocator, AnchorById, WholeDocument, CommentThread]
from larkdocio.write.intrabatch import hedge_intra_batch_not_found
from larkdocio.write.revision import (
    revision_guard_semantics,
    revision_guard_status,
)
from larkdocio.write.resolve import (
    ResolvedCell,
    ResolvedInsertion,
    ResolvedTarget,
    _cell_plain_text,
    _inline_comment_ids,
    _grid_phrase,
    _live_basis_plain_text,
    block_plain_text,
    resolve,
    table_grid,
)

# The private construction token. Only this module holds it, so a :class:`Plan` can be
# built solely via :func:`dry_run` — a caller cannot hand-forge one from raw records.
_PLAN_TOKEN = object()


# --------------------------------------------------------------------------- #
# PlanEntry — the per-edit record (reuses the S1 apply-log record shapes)        #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PlanEntry:
    """The previewed outcome of ONE write request (an edit, insert, delete or sub-span edit).

    Two ``outcome`` shapes — **resolved** (the op would proceed) or **refused** (a typed
    reason) — crossed with an ``op`` discriminator (insert/delete and
    sub-span joined the original edit op). Which payload fields are set depends on ``op``:

    * ``op == "edit"`` — a whole-block/whole-cell replace. Resolved: ``block_id`` (the
      target that would be patched) + ``before`` (the resolved block's current plain
      text) + ``after`` (the replacement) + ``cell`` (table context, table-cell edits
      only). Refused: the typed ``refusal``. ``anchor``/``replacement`` carried on both.
    * ``op == "insert"`` — a block insertion. Resolved: ``block_id`` (the resolved
      **reference**) + ``position`` + ``content`` (the
      :data:`~larkdocio.write.model.NewContent` blocks that WOULD be created — a nestable
      :class:`~larkdocio.write.model.NewBlock` tree) + ``insertion_point`` (the
      computed parent ``block_id`` + index — WHERE they land). Refused: the typed ``refusal``
      (the ``content``/``position`` intent is still carried so an approval UX can show the
      rejected op). ``anchor`` is the reference anchor.
    * ``op == "delete"`` — a block deletion. Resolved: ``block_id`` (the resolved
      **target**) + ``before`` (its current plain text — the text that WOULD be removed).
      Refused: the typed ``refusal``. ``anchor`` is the target anchor.
    * ``op == "subspan"`` — a style-preserving sub-span edit. Resolved:
      ``block_id`` + ``span`` (the verbatim text that would be replaced, also mirrored as
      ``before``) + ``replacement`` (mirrored as ``after``). Refused: the typed ``refusal``,
      still carrying the intended span. The authoritative run-region mapping belongs to
      the apply engine.
    * ``op == "grow-table"`` — a row appended to a table that already exists.
      Resolved: ``block_id`` (the **table** that would be patched) + ``before`` / ``after``
      carrying the grid as it is and as it would be (``"3 rows × 2 columns"`` →
      ``"4 rows × 2 columns"``) — that pair *is* the preview, because a grow changes no text.
      Refused: the typed ``refusal``. ``grow`` carries the request itself on both outcomes, so
      a refused entry still shows which index was asked for.
    * ``op == "comment-create"`` / ``"comment-remove"`` — the two comment ops.
      ``comment`` carries the request itself, because a comment op has **nothing to
      resolve**: a create points at the whole document and a removal at a thread id, so
      there is no ``block_id``, no before/after text and no insertion point to preview —
      the intent *is* the plan. A resolved create additionally carries the authorship
      ``preview_note`` (:data:`~larkdocio.write.comments.NOTE_KIND_COMMENT_AUTHORSHIP`); a
      resolved *removal* is an attempt, since sole ownership of a thread is a live fact the
      apply engine settles immediately before — and as the precondition of — any delete.

    ``anchor`` is carried on **every** entry so a consumer can correlate the preview back
    to the request it submitted without larkdocio knowing the consumer's own ids. A
    ``resolved`` outcome is a *plan*, not an apply-log entry — nothing is written yet.
    Build one via the op-specific classmethods (:meth:`resolved` / :meth:`refused` /
    :meth:`insert_resolved` / :meth:`insert_refused` / :meth:`delete_resolved` /
    :meth:`delete_refused` / :meth:`comment_create_resolved` / …) — never the raw
    constructor.
    """

    outcome: str
    #: The anchor the request carried, verbatim — so a consumer can correlate the preview
    #: back to its own request. Whichever shape that request family accepts (an edit may
    #: carry a table locator; insert / delete / sub-span are narrative-only; a comment op
    #: carries its whole-document or thread target).
    anchor: _AnyPlanAnchor
    op: str = "edit"
    replacement: Optional[str] = None
    block_id: Optional[str] = None
    before: Optional[str] = None
    after: Optional[str] = None
    refusal: Optional[Refusal] = None
    #: Table-cell context (row/column identification + inner text-block ids) — set only
    #: for a **resolved table** edit (W2 / LD-072); ``None`` for the narrative path.
    cell: Optional[ResolvedCell] = None
    #: The blocks an **insert** would create (W3 / LD-075) — the same
    #: :data:`~larkdocio.write.model.NewContent` family an
    #: :class:`~larkdocio.write.model.InsertRequest` carries (LD-134 widened it from
    #: ``NewParagraph`` alone to the typed :class:`~larkdocio.write.model.NewBlock` tree);
    #: empty for edit/delete/sub-span.
    content: Tuple[NewContent, ...] = ()
    #: An **insert**'s :class:`~larkdocio.write.model.InsertPosition` value string
    #: (before/after/append-into); ``None`` for edit/delete.
    position: Optional[str] = None
    #: An **insert**'s computed insertion point (parent block_id + index) — set only for
    #: a **resolved insert** (W3 / LD-075); ``None`` otherwise.
    insertion_point: Optional[ResolvedInsertion] = None
    #: A **sub-span** edit's verbatim span within the block (W3 / LD-077); ``None`` for the
    #: other ops. On a resolved sub-span ``before`` == ``span`` and ``after`` == ``replacement``.
    span: Optional[str] = None
    #: The **by-id staleness precondition** (LD-137): the anchored block's text on the LIVE
    #: basis (text runs only — :func:`~larkdocio.write.resolve._live_basis_plain_text`, the
    #: offline mirror of what the apply engine reads back, per node kind: an inline
    #: ``content`` list, or the page node's ``title`` — LD-141), captured at plan time.
    #:
    #: A quote anchor re-validates against its own quote, so it needs none and this stays
    #: ``None`` (and the key is omitted from the wire form, keeping every shipped
    #: serialization byte-identical). An :class:`~larkdocio.write.model.AnchorById` has no
    #: quote, so the plan carries what it saw and the apply engine requires the live block to
    #: still match it — a compare-and-swap on the anchored block; drift → ``stale-anchor``,
    #: no write. Set for a resolved edit / insert / delete; a sub-span entry needs none (its
    #: own span re-validation is a stricter, more specific precondition).
    precondition_text: Optional[str] = None
    #: A **non-refusing disclosure** about this entry: the op will proceed, and here is what a
    #: human approving it needs to know first. Shape and composition are the shared convention
    #: in :mod:`larkdocio.common.notes` — a single ``{"kind": …, "note": …}`` dict or a
    #: ``"multiple"`` envelope — so a second disclosure can never displace a first. Read it
    #: through :attr:`preview_notes`, which flattens both shapes.
    #:
    #: The docx family's first one is
    #: :data:`NOTE_KIND_COMMENT_ANCHORS_ON_TARGET` on a resolved **sub-span** edit whose target
    #: carries inline review anchors: the whole-block and whole-cell paths *refuse* such a
    #: target, so the sub-span path is the one that proceeds — and a reviewer approving that
    #: preview could not otherwise see that reviewers are involved at all. Costs no API call:
    #: the anchors are already on the tree the plan resolved against.
    preview_note: Optional[dict] = None
    #: The **comment op's** request, verbatim (LD-202) — a
    #: :class:`~larkdocio.write.model.CreateCommentRequest` or a
    #: :class:`~larkdocio.write.model.RemoveCommentRequest`; ``None`` for every other op.
    #:
    #: The request itself rather than destructured fields, because a comment op has nothing
    #: to *resolve*: a create points at the whole document and a removal at a thread id, so
    #: there is no located ``block_id``, no before/after text and no insertion point — the
    #: intent is the entire preview. Carrying the request keeps that honest (and keeps five
    #: near-duplicate fields off an already-wide record), the same way ``cell`` carries a
    #: table edit's structured context in one field instead of four.
    comment: "Optional[Union[CreateCommentRequest, RemoveCommentRequest]]" = None
    #: The **checkbox state this edit would set** (LD-574) — carried verbatim from the
    #: :class:`~larkdocio.write.model.EditRequest`, ``None`` on every other op and on any
    #: edit that does not move the bit, and omitted from :meth:`to_dict` when unset so every
    #: plan written before this shipped serializes byte-identically.
    #:
    #: It is previewed rather than left for the apply log because a preview that shows a text
    #: edit while the apply moves a bit is the same silent-success defect one layer over: a
    #: human approving this plan is approving the checkbox too, and could not otherwise see
    #: it. A ``None`` here means the apply does not touch the checkbox.
    todo_done: Optional[bool] = None
    #: The **table-grow op's** request, verbatim (LD-575) — a
    #: :class:`~larkdocio.write.model.GrowTableRequest`; ``None`` for every other op, and
    #: omitted from :meth:`to_dict` when unset so every plan written before this shipped
    #: serializes byte-identically.
    #:
    #: The request itself rather than a destructured ``row_index``, the same call
    #: :attr:`comment` made and for the same reason: it keeps the intent whole (which index was
    #: asked for, which is the thing a refused entry is *about*) and keeps a near-duplicate
    #: field off an already-wide record. What the entry adds beyond the request is the resolved
    #: ``block_id`` and the grid, in ``before`` / ``after``.
    grow: "Optional[GrowTableRequest]" = None

    def __post_init__(self):
        object.__setattr__(self, "content", tuple(self.content))

    @property
    def preview_notes(self) -> Tuple[dict, ...]:
        """Every individual disclosure on this entry — ``()``, one, or the flattened envelope.

        Prefer this over :attr:`preview_note` whenever you want *all* of them: an entry can
        legitimately earn several, and reading the raw field means handling two shapes. The
        sheets plan entry's accessor of the same name is the same one function.
        """
        return preview_notes_of(self.preview_note)

    # -- edit (W1/W2) ----------------------------------------------------------- #

    @classmethod
    def resolved(
        cls,
        *,
        anchor: _EditAnchor,
        replacement: str,
        block_id: str,
        before: str,
        after: str,
        cell: Optional[ResolvedCell] = None,
        precondition_text: Optional[str] = None,
        todo_done: Optional[bool] = None,
    ) -> "PlanEntry":
        return cls(
            outcome="resolved",
            op="edit",
            anchor=anchor,
            replacement=replacement,
            block_id=block_id,
            before=before,
            after=after,
            cell=cell,
            precondition_text=precondition_text,
            todo_done=todo_done,
        )

    @classmethod
    def refused(cls, *, anchor: _EditAnchor, replacement: str,
                refusal: Refusal, todo_done: Optional[bool] = None) -> "PlanEntry":
        return cls(outcome="refused", op="edit", anchor=anchor, replacement=replacement,
                   refusal=refusal, todo_done=todo_done)

    # -- insert (W3 / LD-075) --------------------------------------------------- #

    @classmethod
    def insert_resolved(
        cls,
        *,
        reference: NarrativeAnchor,
        content: Iterable[NewContent],
        position: str,
        block_id: str,
        insertion_point: ResolvedInsertion,
        precondition_text: Optional[str] = None,
    ) -> "PlanEntry":
        return cls(
            outcome="resolved",
            op="insert",
            anchor=reference,
            content=tuple(content),
            position=position,
            block_id=block_id,
            insertion_point=insertion_point,
            precondition_text=precondition_text,
        )

    @classmethod
    def insert_refused(cls, *, reference: NarrativeAnchor, content: Iterable[NewContent],
                       position: str, refusal: Refusal) -> "PlanEntry":
        return cls(
            outcome="refused",
            op="insert",
            anchor=reference,
            content=tuple(content),
            position=position,
            refusal=refusal,
        )

    # -- delete (W3 / LD-075) --------------------------------------------------- #

    @classmethod
    def delete_resolved(cls, *, target: NarrativeAnchor, block_id: str, before: str,
                        precondition_text: Optional[str] = None) -> "PlanEntry":
        return cls(outcome="resolved", op="delete", anchor=target, block_id=block_id,
                   before=before, precondition_text=precondition_text)

    @classmethod
    def delete_refused(cls, *, target: NarrativeAnchor, refusal: Refusal) -> "PlanEntry":
        return cls(outcome="refused", op="delete", anchor=target, refusal=refusal)

    # -- table grow (LD-575) ---------------------------------------------------- #

    @classmethod
    def grow_table_resolved(cls, *, anchor, request, block_id: str,
                            before: str, after: str) -> "PlanEntry":
        """A row would be appended to the resolved table. ``before`` / ``after`` carry the
        table's grid as it is and as it would be — the whole of what a human approving this
        entry needs, and the reason no new field is minted for it."""
        return cls(outcome="resolved", op="grow-table", anchor=anchor, block_id=block_id,
                   before=before, after=after, grow=request)

    @classmethod
    def grow_table_refused(cls, *, anchor, request, refusal: Refusal) -> "PlanEntry":
        return cls(outcome="refused", op="grow-table", anchor=anchor, refusal=refusal,
                   grow=request)

    # -- sub-span (W3 / LD-077) ------------------------------------------------- #

    @classmethod
    def subspan_resolved(
        cls, *, anchor: NarrativeAnchor, span: str, replacement: str, block_id: str,
        precondition_text: Optional[str] = None,
        preview_note: Optional[dict] = None,
    ) -> "PlanEntry":
        # before == the span (the text that would be replaced); after == the replacement.
        return cls(
            outcome="resolved",
            op="subspan",
            anchor=anchor,
            span=span,
            replacement=replacement,
            block_id=block_id,
            before=span,
            after=replacement,
            precondition_text=precondition_text,
            preview_note=preview_note,
        )

    @classmethod
    def subspan_refused(
        cls, *, anchor: NarrativeAnchor, span: str, replacement: str, refusal: Refusal
    ) -> "PlanEntry":
        return cls(
            outcome="refused",
            op="subspan",
            anchor=anchor,
            span=span,
            replacement=replacement,
            refusal=refusal,
        )

    # -- the comment ops (LD-202) ----------------------------------------------- #

    @classmethod
    def comment_create_resolved(cls, *, anchor: WholeDocument,
                                request: CreateCommentRequest) -> "PlanEntry":
        """A whole-document comment that would be created.

        Carries the authorship disclosure as a preview note, unconditionally: every accepted
        create lands as the application's bot identity, so there is no case in which an
        approver does not need to know it — disclosed here rather than left to be
        discovered. The import is lazy because
        :mod:`larkdocio.write.comments` sits above this module.
        """
        from larkdocio.write.comments import (
            BOT_AUTHORSHIP_DISCLOSURE,
            NOTE_KIND_COMMENT_AUTHORSHIP,
        )

        return cls(
            outcome="resolved",
            op="comment-create",
            anchor=anchor,
            comment=request,
            preview_note={"kind": NOTE_KIND_COMMENT_AUTHORSHIP,
                          "note": BOT_AUTHORSHIP_DISCLOSURE},
        )

    @classmethod
    def comment_create_refused(cls, *, anchor: WholeDocument, request: CreateCommentRequest,
                               refusal: Refusal) -> "PlanEntry":
        """A comment create the API cannot perform — the intent is still carried so an
        approval UX can show the rejected op beside the reason."""
        return cls(outcome="refused", op="comment-create", anchor=anchor,
                   comment=request, refusal=refusal)

    @classmethod
    def comment_remove_resolved(cls, *, anchor: CommentThread,
                                request: RemoveCommentRequest) -> "PlanEntry":
        """A comment removal that would be **attempted**.

        Deliberately not "would succeed": sole ownership of a thread is a live fact, so the
        engine reads the thread and judges it immediately before — and as the precondition
        of — any delete. A resolved removal therefore means "nothing about this request is
        wrong offline", exactly as a resolved edit does not promise the block is still there.
        """
        return cls(outcome="resolved", op="comment-remove", anchor=anchor, comment=request)

    @classmethod
    def comment_remove_refused(cls, *, anchor: CommentThread, request: RemoveCommentRequest,
                               refusal: Refusal) -> "PlanEntry":
        return cls(outcome="refused", op="comment-remove", anchor=anchor,
                   comment=request, refusal=refusal)

    # -- predicates ------------------------------------------------------------- #

    @property
    def is_resolved(self) -> bool:
        return self.outcome == "resolved"

    @property
    def is_insert(self) -> bool:
        return self.op == "insert"

    @property
    def is_delete(self) -> bool:
        return self.op == "delete"

    @property
    def is_subspan(self) -> bool:
        return self.op == "subspan"

    @property
    def is_comment(self) -> bool:
        """Either comment op — the two share a payload field and a target vocabulary, so
        "is this entry about the review conversation rather than the document body?" is one
        question with one answer."""
        return self.op in ("comment-create", "comment-remove")

    def to_dict(self) -> dict:
        """Serialize to the wire dict — dispatched per ``op`` through the **one
        op-descriptor registry** (:mod:`larkdocio.write.ops`). The registry emits the
        shared ``{outcome, anchor}`` head, the ``"op"`` tag for every op except the
        tagless ``"edit"`` (byte-compatibility with the original edit op), then the op's
        own fields in the same order this method historically produced them. Imported lazily to keep this
        lower module free of a load-time cycle."""
        from larkdocio.write import ops

        return ops.serialize_entry(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PlanEntry":
        """Rebuild a :class:`PlanEntry` from its wire dict — dispatched on the ``"op"``
        tag (absent ⇒ the tagless ``"edit"``) through the **one op-descriptor registry**
        (:mod:`larkdocio.write.ops`), whose per-op ``deserialize`` reconstructs the entry
        via the op-specific classmethods. Imported lazily to avoid a load-time cycle."""
        from larkdocio.write import ops

        return ops.deserialize_entry(d)


# --------------------------------------------------------------------------- #
# Plan — the sole hand-off type into the S4 apply engine (non-forgeable)         #
# --------------------------------------------------------------------------- #

class Plan:
    """An ordered, resolver-backed batch of :class:`PlanEntry` — one per edit request.

    The **only** input the apply engine accepts. It cannot be hand-forged:
    its constructor is guarded by a module-private token, so the sole way to obtain a
    :class:`Plan` is :func:`dry_run` (which resolves every edit through the resolver).
    ``Plan(...)`` from arbitrary records raises :class:`TypeError`.

    Inspectable / serializable for a consumer's approval UX: iterate :attr:`entries`
    (or the :attr:`resolved` / :attr:`refusals` partitions), or serialize the whole plan
    with :meth:`to_dict` / :meth:`to_json`. There is intentionally no ``from_dict`` — a
    plan is trusted *because* it came from the resolver, and reconstructing one from JSON
    would re-open the forge vector the hard gate closes.

    **The whole-document staleness anchor.**
    :attr:`document_revision_id` is the document's ``revision_id`` as of the read the plan
    was built from; the apply engine re-reads it immediately before the batch and refuses the
    **entire** batch (``STALE_DOCUMENT``, zero writes) if it differs. :attr:`revision_guard`
    states whether that compare-and-swap is ``"active"`` or ``"unavailable"`` on this plan
    and :attr:`revision_guard_detail` says WHY — both **derived from**
    :attr:`document_revision_id` in the accessors, never stored, so no code path can produce
    a plan whose marker is missing or lying (the never-silent pattern).
    """

    __slots__ = ("_entries", "_document_revision_id")

    def __init__(self, entries: Iterable[PlanEntry] = (), *,
                 document_revision_id=None, _token: object = None):
        if _token is not _PLAN_TOKEN:
            raise TypeError(
                "Plan objects are produced only by larkdocio.write.preview.dry_run(...); "
                "construct a plan via the previewer, not directly."
            )
        object.__setattr__(self, "_entries", tuple(entries))
        object.__setattr__(self, "_document_revision_id", document_revision_id)

    @property
    def entries(self) -> Tuple[PlanEntry, ...]:
        return self._entries

    @property
    def document_revision_id(self):
        """The document ``revision_id`` captured at plan time — the whole-document
        compare-and-swap anchor, or ``None`` when none was supplied."""
        return self._document_revision_id

    @property
    def revision_guard(self) -> str:
        """``"active"`` when this plan carries a usable whole-document anchor, else
        ``"unavailable"``. Derived from :attr:`document_revision_id`, never stored or
        settable — so the guard can never be silently off."""
        return revision_guard_status(self._document_revision_id)

    @property
    def revision_guard_detail(self) -> str:
        """WHY :attr:`revision_guard` reads as it does — including, when unavailable, how to
        activate the guard and what still guards the batch meanwhile."""
        return revision_guard_semantics(self._document_revision_id)["detail"]

    @property
    def resolved(self) -> Tuple[PlanEntry, ...]:
        """The resolved entries, in input order (each would be patched at apply time)."""
        return tuple(e for e in self._entries if e.is_resolved)

    @property
    def refusals(self) -> Tuple[PlanEntry, ...]:
        """The refused entries, in input order (each carries its typed reason)."""
        return tuple(e for e in self._entries if not e.is_resolved)

    def __iter__(self):
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return (f"Plan(resolved={len(self.resolved)}, refused={len(self.refusals)}, "
                f"document_revision_id={self._document_revision_id!r}, "
                f"revision_guard={self.revision_guard})")

    def to_dict(self) -> dict:
        """The plan as JSON-native data — the entries **plus the whole-document staleness
        disclosure**, so an approval UX that renders only the wire form still
        shows the consumer whether the document-level guard is armed and why."""
        semantics = revision_guard_semantics(self._document_revision_id)
        return {
            "entries": [e.to_dict() for e in self._entries],
            "document_revision_id": self._document_revision_id,
            "revision_guard": semantics["status"],
            "revision_guard_detail": semantics["detail"],
        }

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), **kwargs)


# --------------------------------------------------------------------------- #
# dry_run — the mandatory previewer: resolved edits → plan, ZERO writes          #
# --------------------------------------------------------------------------- #

def _by_id_precondition(anchor, node) -> Optional[str]:
    """The by-id staleness precondition for a resolved entry, or ``None`` (LD-137).

    A quote anchor's precondition IS its quote, so it needs nothing captured. An
    :class:`~larkdocio.write.model.AnchorById` has no quote, so the plan captures the
    resolved block's text on the **live basis**
    (:func:`~larkdocio.write.resolve._live_basis_plain_text`) — the offline mirror of the
    ``text_run``-only string the apply engine reads back off the live block. Capturing on the
    *live* basis rather than the richer ``block_plain_text`` (which also counts a mention's
    title) is what stops an unchanged block containing a mention from looking "drifted" at
    write time.

    **One basis per node kind, shared by both sides (LD-141).** The mirror has to hold for
    *every* node an id can reach, not just the ``content``-inline ones: the page node's own
    text lives in its ``title`` (live: ``page.elements``), so a capture that read ``content``
    alone previewed ``''`` against a live document title and made **every** id-anchored write
    against the document ROOT refuse a false ``stale-anchor`` — permanently, and on the one
    anchor an empty document offers. ``_live_basis_plain_text`` carries that arm, so the
    compare-and-swap stays meaningful (a concurrently renamed root still refuses) and by-id
    reaches the same outcome the quote-anchored control always did.

    One helper, called by every op that captures one, so the basis can never diverge per op.
    """
    if isinstance(anchor, AnchorById):
        return _live_basis_plain_text(node)
    return None


def _preview_edit(request, result) -> PlanEntry:
    """One :class:`~larkdocio.write.model.EditRequest` → its plan entry (W1/W2)."""
    if isinstance(result, ResolvedTarget):
        # A table cell carries no OWN plain text (its text lives in an inner block),
        # so its `before` is the cell's descendant text (_cell_plain_text); a
        # narrative block's `before` is its own plain text. The table entry also
        # carries the resolver's cell context (row/column id + inner text-block ids).
        before = (
            _cell_plain_text(result.node)
            if result.cell is not None
            else block_plain_text(result.node)
        )
        return PlanEntry.resolved(
            anchor=request.anchor,
            replacement=request.replacement,
            block_id=result.block_id,
            before=before,
            after=request.replacement,
            cell=result.cell,
            precondition_text=_by_id_precondition(request.anchor, result.node),
            todo_done=request.todo_done,
        )
    return PlanEntry.refused(anchor=request.anchor, replacement=request.replacement,
                             refusal=result, todo_done=request.todo_done)


def _preview_insert(request, result) -> PlanEntry:
    """One :class:`~larkdocio.write.model.InsertRequest` → its plan entry (W3 / LD-075).

    Previews WHAT would be created (the request's ``content`` paragraphs) and WHERE (the
    resolved reference ``block_id`` + the position + the computed insertion point). A
    refusal still carries the intended content + position so an approval UX can show the
    rejected op.
    """
    if isinstance(result, ResolvedTarget):
        return PlanEntry.insert_resolved(
            reference=request.reference,
            content=request.content,
            position=request.position.value,
            block_id=result.block_id,
            insertion_point=result.insertion,
            precondition_text=_by_id_precondition(request.reference, result.node),
        )
    return PlanEntry.insert_refused(
        reference=request.reference,
        content=request.content,
        position=request.position.value,
        refusal=result,
    )


def _preview_delete(request, result) -> PlanEntry:
    """One :class:`~larkdocio.write.model.DeleteRequest` → its plan entry (W3 / LD-075).

    Previews the resolved target ``block_id`` + its current plain text — the text that
    WOULD be removed (deletion is destructive; the consumer sees exactly what goes)."""
    if isinstance(result, ResolvedTarget):
        return PlanEntry.delete_resolved(
            target=request.target,
            block_id=result.block_id,
            before=block_plain_text(result.node),
            precondition_text=_by_id_precondition(request.target, result.node),
        )
    return PlanEntry.delete_refused(target=request.target, refusal=result)


def _preview_grow_table(request, result) -> PlanEntry:
    """One :class:`~larkdocio.write.model.GrowTableRequest` → its plan entry (LD-575).

    Previews the resolved **table**'s ``block_id`` and its grid before and after — the only two
    facts a grow changes, and the pair a human is approving. No precondition text: a grow
    rewrites no text, so there is nothing for the per-entry compare-and-swap to compare; the
    concurrency guarantee this op relies on is the batch-level ``STALE_DOCUMENT`` one, plus the
    apply engine's own live re-read of the block it is about to patch.
    """
    if isinstance(result, ResolvedTarget):
        rows, columns = table_grid(result.node)
        return PlanEntry.grow_table_resolved(
            anchor=request.anchor,
            request=request,
            block_id=result.block_id,
            before=_grid_phrase(rows, columns),
            after=_grid_phrase(rows + 1, columns),
        )
    return PlanEntry.grow_table_refused(anchor=request.anchor, request=request, refusal=result)


def _comment_anchor_note(node, block_id: str) -> Optional[dict]:
    """The reviewer-anchor disclosure for a resolved sub-span target, or ``None``.

    Judged on the block's **inline** (word-level) anchors — the same reduction the whole-block
    and whole-cell paths refuse on (:func:`~larkdocio.write.resolve._inline_comment_ids`), and
    for the same reason it is the right one: a **block-level** comment is on the block as a
    whole, is untouched by a run split, and firing on it would put a disclosure on edits no
    reviewer has any stake in. One helper reading one reduction, so the note and the refusal can
    never disagree about what counts as an anchor.

    **Costs nothing.** The anchors are on the tree the plan already resolved against, so this is
    decided at plan time with no read, no write, and no client — like the refusal it accompanies.
    """
    anchors = _inline_comment_ids(node)
    if not anchors:
        return None
    return {
        "kind": NOTE_KIND_COMMENT_ANCHORS_ON_TARGET,
        "comment_ids": list(anchors),
        "note": (
            f"block {block_id} carries {len(anchors)} inline comment "
            f"{'anchor' if len(anchors) == 1 else 'anchors'} ({', '.join(anchors)}): a "
            f"reviewer's comment is attached to particular words inside the text this edit "
            f"rewrites. This is the ONE edit path that proceeds on such a block — a "
            f"sub-span edit splits the runs at the span boundaries, and each rebuilt run "
            f"re-emits the anchors of the text it replaces, so a comment stays on the words it "
            f"was left on. (A whole-block or whole-cell edit of the same block refuses "
            f"comment-anchors-present instead, because collapsing the block to one run leaves "
            f"per-passage anchors nowhere to attach.) Disclosed so a human approving this "
            f"preview knows reviewers are involved and can read what they said first — the "
            f"comments read joins each anchor id to the reviewer's words."
        ),
    }


def _preview_subspan(request, result) -> PlanEntry:
    """One :class:`~larkdocio.write.model.SubSpanEditRequest` → its plan entry (W3 / LD-077).

    Previews the span that WOULD be replaced + the replacement (``before`` == span,
    ``after`` == replacement) at the resolved block. A refusal still carries the intended
    span + replacement so an approval UX can show the rejected op (mirrors edit / insert /
    delete refusals). The authoritative run-region mapping is the S4 apply engine's job.

    **The plan also DISCLOSES its compare-and-swap basis (LD-150 / dogfood F16).** An
    id-anchored edit / insert / delete has always carried ``precondition_text``; the sub-span
    family alone did not, "in a library whose ethos is *never silently off, always disclosed on
    the plan*". It now captures the same live-basis text through the same one helper
    (:func:`_by_id_precondition`), so no family hides its basis.

    **Disclosure only — no behavior change.** :func:`~larkdocio.write.apply._apply_subspan`
    re-validates the **span** against the live text (a stricter, offset-bearing precondition)
    and never consults ``precondition_text``; it does not route through
    :func:`~larkdocio.write.apply._revalidated_or_stale`. What changes is that a reviewer can
    now *see* what the plan saw.

    **And the plan says when the target is under review (LD-172).** This is the only edit path
    that proceeds on a block a reviewer has commented *inside* — the whole-block and whole-cell
    paths refuse it — so a resolved entry whose target carries inline anchors carries a
    :data:`NOTE_KIND_COMMENT_ANCHORS_ON_TARGET` ``preview_note`` (:func:`_comment_anchor_note`).
    Disclosure only, again: which ids land on which emitted run is the apply engine's job and is
    unchanged; what changes is that an approver can see reviewers are involved. Zero extra API
    calls — the anchors are already on the tree.
    """
    if isinstance(result, ResolvedTarget):
        return PlanEntry.subspan_resolved(
            anchor=request.anchor,
            span=request.span,
            replacement=request.replacement,
            block_id=result.block_id,
            precondition_text=_by_id_precondition(request.anchor, result.node),
            preview_note=_comment_anchor_note(result.node, result.block_id),
        )
    return PlanEntry.subspan_refused(
        anchor=request.anchor, span=request.span, replacement=request.replacement, refusal=result
    )


def dry_run(requests: Iterable, root, *, document_revision_id=None) -> Plan:
    """Preview a batch of write requests (edit / insert / delete / sub-span) against ``root``.

    Runs each request through the resolver and returns a :class:`Plan` whose entries
    are 1:1 with the input batch, in order. Dispatches per request kind through the **one
    op-descriptor registry** (:mod:`larkdocio.write.ops`) — the same ordered classifier
    :func:`~larkdocio.write.resolve.resolve` reads — so an
    :class:`~larkdocio.write.model.InsertRequest` previews content-to-create + location, a
    :class:`~larkdocio.write.model.DeleteRequest` previews text-to-remove, a
    :class:`~larkdocio.write.model.SubSpanEditRequest` previews the span + replacement, an
    :class:`~larkdocio.write.model.EditRequest` previews before/after. **Zero writes** —
    no :class:`~larkdocio.write.client.WriteClient` is involved (there is no client
    parameter). See the module docstring for the full contract.

    **``document_revision_id`` — the whole-document staleness anchor.** Pass the
    ``revision_id`` of the document ``root`` was read from and the apply engine re-reads it
    immediately before the batch, refusing the **entire** batch (``STALE_DOCUMENT``, **zero
    writes**) if it changed. That is the only way to catch drift *around* an anchor, where the
    per-entry ``STALE_ANCHOR`` check is structurally blind. The reader hands the value over
    for free: ``document, blocks = client.get_docx_content(token)`` →
    ``document.revision_id``. Capture it from (or before) that read, never after — anchoring
    on the earlier value can only refuse a document that really did change.

    Omit it and the plan is **marked** ``revision_guard: "unavailable"`` with the WHY and the
    activation instructions (:attr:`Plan.revision_guard` /
    :attr:`Plan.revision_guard_detail`, both also in :meth:`Plan.to_dict`) — the guard is
    never silently off, and the per-entry ``STALE_ANCHOR`` re-validation still runs. It is a
    **keyword with a default**, so this stays a pure addition: the previewer still takes no
    client and so still *structurally cannot write* — the anchor is a scalar the caller
    already holds, not a read this function performs.
    """
    from larkdocio.write import ops

    entries: List[PlanEntry] = []
    for request in requests:
        result = resolve(request, root)
        entries.append(ops.preview_dispatch(request, result))
    # The ONE intra-batch disclosure pass (LD-151 / dogfood F14). Every entry above was
    # resolved in isolation, as it must be — one tree, one batch. Only here, where the whole
    # batch is in scope, can a `not-found` whose text the batch ITSELF would create be told
    # apart from a plain typo, so only here can its detail stop advising a re-read that cannot
    # succeed. Reason-preserving, I/O-free, resolver-blind: see
    # :mod:`larkdocio.write.intrabatch` for the contract and the engine-unchanged rationale.
    return Plan(
        hedge_intra_batch_not_found(entries),
        document_revision_id=document_revision_id,
        _token=_PLAN_TOKEN,
    )
