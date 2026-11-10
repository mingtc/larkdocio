"""larkdocio.write.model.anchors — where an edit points (the locator vocabulary).

The three additive anchor shapes an :class:`~larkdocio.write.model.EditRequest` (and every
apply-log entry) resolves against:

* :class:`Anchor` (the narrative path, W1) — a verbatim **quote** plus a **breadcrumb**
  heading-path, resolving to exactly one *paragraph* block. A quote alone is not a unique
  locator (on the scratch doc one quote matched 5 blocks); the resolver (S2) combines the
  quote with the breadcrumb to resolve to exactly one block.
* :class:`TableLocator` (the table path, W2 / LD-070) — a bare quote is useless in a table
  (the spike found ``97.2%`` in 6 blocks), so a cell is located by its **row's key-cell
  quote** (``row_key``) plus a **column-target** (either a verbatim **row-0** cell quote
  ``column_header`` **or** a 0-based ``column_index`` — exactly one), plus a **breadcrumb**
  that narrows *which* table when the same key cell recurs.
* :class:`AnchorById` (the by-id path, LD-137) — a bare **``block_id``**.
  ``apply()`` has always handed back ``created_block_ids``, but until LD-137 anchors were
  **quote-only**, so following up on a block you just created meant round-tripping a verbatim
  quote copied out of a fresh read: needless indirection *and* a staleness risk (dogfood
  **F19**). An id is the document's own stable, unambiguous handle.

The breadcrumb is **carried on the model** (part of the anchor the consumer supplies), not
recomputed later. The anchor shapes serialize under a discriminating ``kind`` tag —
:class:`TableLocator` emits ``"kind": "table"`` and :class:`AnchorById` emits
``"kind": "by-id"``; the tagless narrative :class:`Anchor` stays byte-compatible with its W1
form, so W1 JSON reads back unchanged. Dumb typed data; depends only on the standard library.
"""
from dataclasses import dataclass
from typing import Optional, Tuple


# --------------------------------------------------------------------------- #
# EditRequest — anchor (quote + breadcrumb) + whole-paragraph replacement       #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Anchor:
    """Where an edit points: a verbatim **quote** plus a **breadcrumb** heading-path.

    A quote alone is not a unique locator (on the scratch doc one quote matched 5
    blocks); the resolver combines the quote with the breadcrumb — the ordered
    heading texts above the target — to resolve to exactly one block. The breadcrumb
    is normalized to an immutable ``tuple`` so an anchor is hashable and two equal
    heading-paths compare equal regardless of how the consumer passed them (list or
    tuple).

    **The quote is matched byte-verbatim, as a substring, against the block's RAW STORED
    text** — never against rendered Markdown. Stored text can carry a *soft return* (a
    literal newline inside one paragraph) that the Markdown shows as an ordinary line wrap,
    so a whole sentence copied off a wrapped paragraph differs from what is stored by one
    invisible character and refuses. **Quote a SHORT fragment that sits on one side of a
    wrap**, not a whole sentence::

        Anchor(quote="Revenue grew 12.4%", breadcrumb=("Overview",))

    Nothing is whitespace-normalized to force a match — exactly-one-or-refuse is the
    contract — but a whitespace-only near-miss is *named* in the refusal, with the stored
    spelling and a fragment of your own quote that does match. For a locator that no
    whitespace can spell wrong, use :class:`AnchorById`.
    """

    quote: str
    breadcrumb: Tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "breadcrumb", tuple(self.breadcrumb))

    def to_dict(self) -> dict:
        return {"quote": self.quote, "breadcrumb": list(self.breadcrumb)}

    @classmethod
    def from_dict(cls, d: dict) -> "Anchor":
        return cls(quote=d["quote"], breadcrumb=tuple(d.get("breadcrumb", ())))


# The row-0 reading of `column_header` is a ruling, not an accident: gating it on
# TableNode.header_row was the alternative and was declined, because it would remove a
# working way to repair a sentence in a header-less table (D-117, in the dev repo:
# requirements/DECISIONS.md; the wording fix it ordered is LD-636).
@dataclass(frozen=True)
class TableLocator:
    """Where a **table-cell** edit points — the table-cell anchor shape.

    A bare quote cannot locate a cell: the spike found the value ``97.2%`` in **6
    blocks** doc-wide (write-spike Test 5), so the table path locates a cell by
    coordinates instead of by text:

    * ``row_key`` — a verbatim **key-cell quote**; the resolver picks the row
      whose key cell matches it (unique-or-refuse *within* the table).
    * a **column-target** — **exactly one** of ``column_header`` (a verbatim quote of a
      **row-0** cell) **or** ``column_index`` (a 0-based column index). **``column_header``
      means "the text in row 0", and it does not require the table to have a header row:**
      the resolver never reads ``TableNode.header_row``, so on a ``header_row=False`` table
      a row-0 *data* cell is a working column target, and resolution stays
      unique-or-refuse either way. What the two spellings differ in is convenience, not
      capability — a quote reads naturally where row 0 names the columns, an index is the
      tool where it does not (and where row 0's text is not unique). A
      ``column-not-found`` refusal says which of the two kinds of table it was looking at.
      Supplying neither (no column) or both (ambiguous designation) is rejected at
      construction.
    * ``breadcrumb`` — the heading path that narrows **which** table when the same key
      cell recurs under more than one heading (the resolver uses it exactly as the narrative
      :class:`Anchor` uses its breadcrumb). Normalized to an immutable ``tuple``.

    Frozen and JSON-round-trippable like :class:`Anchor`; it serializes with a
    ``"kind": "table"`` discriminator so an :class:`EditRequest` / apply-log entry can
    tell a table anchor from a narrative one on the way back in. This type defines the
    *locator shape only* — no resolution happens here — the resolver does that.
    """

    row_key: str
    column_header: Optional[str] = None
    column_index: Optional[int] = None
    breadcrumb: Tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "breadcrumb", tuple(self.breadcrumb))
        has_header = self.column_header is not None
        has_index = self.column_index is not None
        if has_header == has_index:
            raise ValueError(
                "TableLocator needs exactly one column-target: "
                "column_header (a verbatim row-0 cell quote) OR column_index (0-based)."
            )

    def to_dict(self) -> dict:
        d: dict = {
            "kind": "table",
            "row_key": self.row_key,
            "breadcrumb": list(self.breadcrumb),
        }
        if self.column_header is not None:
            d["column_header"] = self.column_header
        else:
            d["column_index"] = self.column_index
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TableLocator":
        return cls(
            row_key=d["row_key"],
            column_header=d.get("column_header"),
            column_index=d.get("column_index"),
            breadcrumb=tuple(d.get("breadcrumb", ())),
        )


@dataclass(frozen=True)
class AnchorById:
    """Where an edit points, by the document's own handle: a bare **``block_id``**.

    The by-id anchor shape. Every
    :class:`~larkdocio.write.model.ApplyLogEntry` for an insert already reports
    ``created_block_ids``, and every block the reader parses carries its ``block_id`` (the
    provenance) — but until now the *only* way to point an edit at one of them was to
    copy its text back out as a verbatim :class:`Anchor` quote. That is indirection with a
    staleness risk baked in, and it simply **cannot** address a block whose text is not
    unique (a quote that matches five blocks refuses, forever).

    An id sidesteps all of it: ``block_id`` is matched by **exact string equality** against
    the parsed tree — never a prefix, a suffix, a case-fold or any other guess — so it
    resolves to **exactly one** block or refuses. The refusals are the same typed vocabulary
    the quote path uses, and each carries the **mandatory actionable ``detail``**
    naming *the id*:

    * an id absent from the tree (it never existed, it belongs to **another document**, or
      the block was deleted) → :meth:`~larkdocio.write.model.Refusal.not_found`;
    * an id that resolves to write-hostile content (image / board / embed / synced) →
      :meth:`~larkdocio.write.model.Refusal.write_hostile` — *hostile*, not not-found: the
      id **was** found, so hunting for a better id is the wrong repair;
    * for a **text-replacing** op (a whole-block edit or a sub-span edit), an id that
      resolves to a **container** whose text lives only in its children (a table, a table
      cell, a grid, a callout) → ``write-hostile`` too, naming the child-id / ``TableLocator``
      repair. A quote can never reach those blocks (their own text is empty), so this is the
      by-id mirror of an invariant the quote path already had, not a new restriction;
    * the position-capability mirrors are unchanged — a ``before``/``after`` insert against
      the document **root** id refuses ``cannot-hold-siblings``, an ``append-into`` against a
      leaf refuses ``cannot-hold-children``.

    **Staleness still applies.** A quote anchor re-validates by checking its own quote is
    still present in the live block; an id has no quote, so the plan captures the block's
    live-basis text at plan time and the engine requires it to be **unchanged** immediately
    before writing — drift → ``stale-anchor``, no write (a compare-and-swap on the anchored
    block, strictly stronger than the quote check). An id that has been **deleted** between
    plan and apply cannot be re-read at all, and that too refuses ``stale-anchor`` rather
    than aborting the batch. See :mod:`larkdocio.write.apply`.

    Frozen and JSON-round-trippable like the other shapes, under its own
    ``"kind": "by-id"`` discriminator so one dispatcher (:func:`_anchor_from_dict`) tells all
    three apart and the tagless :class:`Anchor` form stays byte-compatible. An empty /
    blank id is refused at construction — it locates nothing, and a locator that cannot
    locate must never reach a plan.
    """

    block_id: str

    def __post_init__(self):
        if not isinstance(self.block_id, str):
            raise TypeError(
                f"AnchorById.block_id must be a str (the document's own block handle), got "
                f"{type(self.block_id).__name__}"
            )
        if not self.block_id.strip():
            raise ValueError(
                "AnchorById needs a non-empty block_id — a blank id locates nothing. Use the "
                "block_id the reader parsed (every node carries one) or one of the "
                "created_block_ids apply() returned."
            )

    def to_dict(self) -> dict:
        return {"kind": "by-id", "block_id": self.block_id}

    @classmethod
    def from_dict(cls, d: dict) -> "AnchorById":
        return cls(block_id=d["block_id"])


@dataclass(frozen=True)
class WholeDocument:
    """Where a **whole-document comment** points: the file itself, not a passage in it.

    A comment created through Lark's API is attached to the whole document and to nothing
    smaller. That is not a simplification this library chose — it is the only shape the API
    produces. The v1 create route **accepts** an ``anchor`` / ``quote`` / ``is_whole:false``
    and then **silently ignores** all three, answering ``code 0`` and creating a plain
    whole-document comment; six probe shapes, including a **bogus block id** and a quote
    that does not occur in the document, all did exactly that. A passage anchor is therefore
    not a capability with a gap in it — it does not exist — and this type is what says so in
    the type system rather than in a comment: a comment op's target is *this*, and asking for
    anything narrower is refused with the captured evidence
    (:data:`~larkdocio.write.model.refusal.RefusalReason.COMMENT_ANCHOR_NOT_CREATABLE`).

    Carries no fields — there is nothing to point *at* beyond the document the batch is
    already applying to — so all instances are equal and :data:`WHOLE_DOCUMENT` is the value
    to use. Serializes under its own ``"kind": "whole-document"`` tag like the other shapes.
    """

    def to_dict(self) -> dict:
        return {"kind": "whole-document"}

    @classmethod
    def from_dict(cls, d: dict) -> "WholeDocument":
        return cls()


#: The one :class:`WholeDocument` value. A comment's target has no parameters, so there is
#: nothing to distinguish two instances; naming the value means a caller writes
#: ``WHOLE_DOCUMENT`` instead of constructing a fresh empty object per request.
WHOLE_DOCUMENT = WholeDocument()


@dataclass(frozen=True)
class CommentThread:
    """Where a **comment removal** points: one comment thread, by the API's own id.

    A thread has no textual locator worth having — its content is its replies, and a quote
    of a reply is neither unique nor stable — so the only honest handle is the
    ``comment_id`` the API assigned. Ids are matched by the server, so this anchor never
    resolves against the document tree; what the engine checks live, immediately before
    removing anything, is that the thread is one the caller's application **authored and is
    alone in** (see :mod:`larkdocio.write.comments`).

    A blank id is refused at construction: it locates nothing, and a locator that cannot
    locate must never reach a plan — the :class:`AnchorById` discipline, for the same
    reason.
    """

    comment_id: str

    def __post_init__(self):
        if not isinstance(self.comment_id, str):
            raise TypeError(
                f"CommentThread.comment_id must be a str (the API's own comment id), got "
                f"{type(self.comment_id).__name__}"
            )
        if not self.comment_id.strip():
            raise ValueError(
                "CommentThread needs a non-empty comment_id — a blank id names no thread. "
                "Use the comment_id the comments read reports (Comment.comment_id) or the "
                "one a comment-create apply-log entry handed back."
            )

    def to_dict(self) -> dict:
        return {"kind": "comment-thread", "comment_id": self.comment_id}

    @classmethod
    def from_dict(cls, d: dict) -> "CommentThread":
        return cls(comment_id=d["comment_id"])


def _anchor_from_dict(d: dict):
    """Deserialize whichever anchor shape a serialized form carries.

    The table anchor (:class:`TableLocator`) tags itself ``"kind": "table"``, the by-id
    anchor (:class:`AnchorById`) tags itself ``"kind": "by-id"``, and the two comment shapes
    tag themselves ``"kind": "whole-document"`` (:class:`WholeDocument`) and
    ``"kind": "comment-thread"`` (:class:`CommentThread`); the narrative :class:`Anchor` is
    tagless (its W1 serialization is unchanged), so a missing/other ``kind`` reads back as an
    :class:`Anchor`. Shared by every request's ``from_dict`` and
    :meth:`ApplyLogEntry.from_dict` so the whole chain round-trips every shape through one
    dispatcher.
    """
    kind = d.get("kind")
    if kind == "table":
        return TableLocator.from_dict(d)
    if kind == "by-id":
        return AnchorById.from_dict(d)
    if kind == "whole-document":
        return WholeDocument.from_dict(d)
    if kind == "comment-thread":
        return CommentThread.from_dict(d)
    return Anchor.from_dict(d)


def _describe_anchor(anchor) -> str:
    """A short phrase naming **what the anchor pointed by** — for a refusal ``detail``.

    Every refusal carries a mandatory detail naming the identifier it is about (LD-131), and
    that identifier differs per anchor shape: a quote, a row-key, or a ``block_id``. Routing
    the phrasing through one helper is what lets the resolver's shared refusal messages stay
    truthful for **every** shape instead of hard-coding ``anchor.quote`` (which an
    :class:`AnchorById` does not have). The :class:`Anchor` phrasing is **byte-identical** to
    the pre-LD-137 wording, so no shipped refusal message changed.
    """
    block_id = getattr(anchor, "block_id", None)
    if block_id is not None:
        return f"block_id {block_id!r}"
    row_key = getattr(anchor, "row_key", None)
    if row_key is not None:
        return f"row_key {row_key!r}"
    comment_id = getattr(anchor, "comment_id", None)
    if comment_id is not None:
        return f"comment_id {comment_id!r}"
    if isinstance(anchor, WholeDocument):
        return "the whole document"
    return f"quote {getattr(anchor, 'quote', None)!r}"
