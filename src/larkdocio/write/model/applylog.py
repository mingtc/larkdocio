"""larkdocio.write.model.applylog — the JSON-serializable record of applying edits.

:class:`ApplyLogEntry` / :class:`ApplyLog` are the record of processing a request:
**applied** (target ``block_id`` + before/after text), **refused** (the typed reason),
**inserted** (the created ``block_id``\\ s), or **deleted** (the removed ``block_id`` + the
**full removed-block payload** so a destructive delete stays reconstructable — W3 / LD-074).
An :class:`ApplyLog` round-trips through ``json.dumps``/``loads`` via :meth:`to_dict` /
:meth:`from_dict` (or :meth:`to_json` / :meth:`from_json`) losslessly.

This is what the apply engine (S5) returns to the consumer; the consumer decides what to do
with its own state afterward (larkdocio does not). Dumb typed data — it depends on the
standard library plus the anchor and refusal vocabularies
(:mod:`larkdocio.write.model.anchors`, :mod:`larkdocio.write.model.refusal`).
"""
import json
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple, Union

from .anchors import (
    Anchor,
    AnchorById,
    CommentThread,
    TableLocator,
    WholeDocument,
    _anchor_from_dict,
)
from .refusal import Refusal

#: The anchor shapes an apply-log entry can carry — the union over every request family's
#: own anchor field (the plan entry's annotation is held identical to it by
#: ``tests/test_dry_run_preview.py``, because a log entry carries the same anchor off the
#: same request). Named once so widening a family widens both records together.
LoggedAnchor = Union[Anchor, TableLocator, AnchorById, WholeDocument, CommentThread]

#: The apply-log key carrying an insert's **measured cost** — how many mutating write calls
#: the engine issued for that one entry. Spelled here and nowhere else in the package, so the
#: wire name and the documents that state it cannot drift apart.
INSERT_WRITE_CALLS_KEY = "mutating_write_calls"

#: The apply-log key carrying the **consequence** derived from that count.
INSERT_ATOMIC_KEY = "atomic"

#: The stability contract for the two keys above — what a consumer may rely on, and what may
#: change under them. Authored once here and projected verbatim into the shipped guide.
INSERT_COST_CONTRACT = (
    "Every `inserted` apply-log entry carries `mutating_write_calls` — a MEASUREMENT, counted "
    "from the write calls the engine actually issued for that entry — and `atomic`, which is "
    "true when that count is one and false otherwise. RELY ON: both keys being present on "
    "every `inserted` entry; the unit being MUTATING write calls, so a paginated read is not "
    "one of them and a single batched call carrying many updates is exactly one; and "
    "`atomic: false` meaning a failure partway through can leave part of that content in the "
    "document, where `atomic: true` means it landed whole or not at all. DO NOT RELY ON: the "
    "number itself for any given content. How the engine gets your content into a document — "
    "which calls it uses, how much each one carries, and where it splits them — is internal "
    "and changes without notice. Read the number the entry reports; never predict it, and "
    "never compose to a boundary you inferred from it."
)


#: The three outcomes the **apply-time disposition boundary**
#: (:mod:`larkdocio.write.disposition`) produces. Named here, once, because both
#: :meth:`ApplyLogEntry.to_dict` and the landed/did-not-land split below have to agree about
#: which outcomes carry a classifying refusal.
_DISPOSITION_OUTCOMES = frozenset({"applied-unverified", "failed", "not-attempted"})

#: Every outcome whose change **is on the document**. Stated as a set rather than as
#: ``outcome != "refused"`` — which is what this used to be — because that spelling was only
#: correct while ``refused`` was the sole non-landing outcome, and it would silently have
#: counted ``failed`` and ``not-attempted`` as applied the moment they existed. For the six
#: outcomes that shipped before the boundary the two spellings give the identical answer, so
#: nothing a consumer could hold changed meaning here.
_LANDED_OUTCOMES = frozenset({
    "applied", "inserted", "deleted", "commented", "comment-removed",
    "applied-unverified",
})


# --------------------------------------------------------------------------- #
# Apply-log — JSON-serializable record of processing each edit request           #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ApplyLogEntry:
    """The outcome of processing ONE request (edit, insert, or delete).

    Exactly one of four shapes, discriminated by ``outcome``:

    * **applied** — a whole-block replace succeeded: ``block_id`` (the patched target) +
      ``before`` / ``after`` text.
    * **refused** — the typed ``refusal``; the other fields stay ``None`` / empty.
    * **inserted** — an insert succeeded: ``created_block_ids`` carries the
      block id(s) ``create_children`` returned for the new paragraphs. (Population with
      real ids happens in the apply engine; the model defines the shape.) It also carries
      what the insert **cost** and what follows from that — see
      :data:`INSERT_COST_CONTRACT`, which is the stability contract for
      :attr:`mutating_write_calls` and :attr:`atomic`, quoted here in full because a key a
      consumer parses without a stated contract is the next thing to go wrong:

      ``INSERT_COST_CONTRACT``
    * **deleted** — a delete succeeded: ``block_id`` (the removed block) +
      ``removed_payload``, the **full removed-block payload** — ``elements`` + per-run
      ``style`` + block-level ``style``, and for a block whose content is not an ``elements``
      container at all, its own content object verbatim — a diagram's ``add_ons``, an
      image's ``image`` — captured **before** the delete so a consumer can say
      exactly what was removed. Deletion is destructive; this payload is the non-negotiable
      safety record. For an image it is a **reference** record and not a restore: the token
      names bytes that still exist, but nothing here re-binds a captured token to a new block
      (Real capture happens in the apply engine; the model defines the shape — a
      JSON-serializable dict, e.g. ``{"block_id", "block_type", "elements", "style"}``,
      shaped so a consumer can recreate the block via ``create_children``.)

    Two more, for the comment ops — the review conversation, not the document body,
    so neither has a ``block_id``:

    * **commented** — a whole-document comment was created: ``comment_record`` carries its
      ``comment_id``, its ``reply_ids``, the ``author_id`` it landed as (the application's
      own bot open_id — the id a later removal must state, and the one thing about this op a
      consumer cannot look up) and the ``scope`` / ``file_type`` it was created at.
    * **comment-removed** — a thread the application solely owned was removed:
      ``comment_record`` carries the ``comment_id`` and the ``removed_reply_ids`` in the order
      they went. Removal is irreversible and the record is the whole account of it, exactly as
      ``removed_payload`` is for a block delete.

    Three more come from the **apply-time disposition boundary**
    (:mod:`larkdocio.write.disposition`), which is what makes this log 1:1 with the plan even
    when a write raises mid-batch. All three carry the typed ``refusal`` that classifies the
    failure:

    * **applied-unverified** — the write **RETURNED** (the change IS in the document) and a
      step after it failed, so the change landed with an incomplete verification record. It
      is deliberately not called ``refused``: a log that reported a landed write as "nothing
      landed" would be a log that lies, and that is the one failure the boundary exists to
      prevent.
    * **failed** — the attempt leaves whether it landed **INDETERMINATE** (a transport
      failure below Lark, an unterminable paged read, an un-modelled exception). Also
      deliberately not ``refused``, and for the mirror reason: "nothing landed" would be a
      guess.
    * **not-attempted** — the batch halted at an earlier entry and this one never ran. It is
      a *logged* outcome rather than an absent one, because "there is no entry" and "there is
      an entry that never ran" are the two readings a consumer of a half-applied batch cannot
      afford to confuse.

    ``comment_record`` is additionally set on a **refused** comment removal that failed
    *partway* — the one case a pre-check cannot make impossible — because which replies
    already went is precisely what a consumer needs and cannot recover.

    ``anchor`` is carried on every entry so a consumer can correlate the outcome back to
    the request it submitted (an insert's reference anchor / a delete's target anchor / a
    comment's whole-document or thread target) without larkdocio knowing the consumer's own
    ids — whichever anchor shape it used (:data:`LoggedAnchor`; one dispatcher reads them all
    back, so any log round-trips losslessly). Build one via :meth:`applied` /
    :meth:`refused` / :meth:`inserted` / :meth:`deleted` / :meth:`commented` /
    :meth:`comment_removed` — never the raw constructor.
    """

    outcome: str
    anchor: LoggedAnchor
    block_id: Optional[str] = None
    before: Optional[str] = None
    after: Optional[str] = None
    refusal: Optional[Refusal] = None
    created_block_ids: Tuple[str, ...] = ()
    removed_payload: Optional[dict] = None
    #: The **comment op's** record (LD-202) — a JSON-native dict, ``None`` for every other
    #: outcome. Omitted from :meth:`to_dict` when unset, so every shipped log's wire form is
    #: byte-unchanged.
    comment_record: Optional[dict] = None
    #: An **insert's measured cost** (LD-562) — how many MUTATING write calls the engine
    #: issued for this entry, counted from the calls it actually made rather than predicted
    #: from the content. ``None`` on every other outcome and on any entry built without a
    #: measurement, and omitted from :meth:`to_dict` when unset, so every log written before
    #: this shipped serializes byte-identically. :attr:`atomic` is derived from it.
    mutating_write_calls: Optional[int] = None
    #: The **checkbox state this entry set** (LD-574) — ``True`` / ``False`` on an applied
    #: edit that moved a ``todo``'s bit, ``None`` on every other entry, and omitted from
    #: :meth:`to_dict` when unset so every log written before this shipped serializes
    #: byte-identically.
    #:
    #: It is on the log because a receipt has to say what happened: a pure checkbox flip
    #: leaves ``before`` and ``after`` equal (the text was not the thing that changed), and a
    #: log entry reading ``applied`` with identical images is precisely the shape of the
    #: defect this change closes. This field is what tells the two apart.
    todo_done: Optional[bool] = None

    def __post_init__(self):
        object.__setattr__(self, "created_block_ids", tuple(self.created_block_ids))

    @property
    def atomic(self) -> Optional[bool]:
        """Whether this entry's content landed **whole or not at all** — ``None`` when no
        measurement was taken.

        Derived from :attr:`mutating_write_calls` and from nothing else: one call is atomic,
        more than one is not. Never from *which* internal route ran — some content that does
        not take the single-subtree route is still exactly one call, and a flag keyed on the
        branch would report that content as non-atomic when it is not.
        """
        if self.mutating_write_calls is None:
            return None
        return self.mutating_write_calls == 1

    @classmethod
    def applied(cls, *, anchor: LoggedAnchor, block_id: str, before: str, after: str,
                todo_done: Optional[bool] = None) -> "ApplyLogEntry":
        return cls(outcome="applied", anchor=anchor, block_id=block_id, before=before,
                   after=after, todo_done=todo_done)

    @classmethod
    def refused(cls, *, anchor: LoggedAnchor, refusal: Refusal,
                comment_record: Optional[dict] = None) -> "ApplyLogEntry":
        """A refused request. ``comment_record`` is set **only** for a comment removal that
        failed partway through its cascade, where what already went cannot be inferred and
        cannot be undone."""
        return cls(outcome="refused", anchor=anchor, refusal=refusal,
                   comment_record=comment_record)

    @classmethod
    def inserted(cls, *, anchor: LoggedAnchor, created_block_ids: Sequence[str],
                 mutating_write_calls: Optional[int] = None) -> "ApplyLogEntry":
        """A successful insert — carry the created block id(s) and what the insert **cost**.

        ``mutating_write_calls`` is the engine's own count of the write calls it issued for
        this entry; :attr:`atomic` follows from it. It is optional only so a hand-built or
        replayed entry can exist without a measurement — the engine always passes one.
        """
        return cls(outcome="inserted", anchor=anchor,
                   created_block_ids=tuple(created_block_ids),
                   mutating_write_calls=mutating_write_calls)

    @classmethod
    def deleted(cls, *, anchor: LoggedAnchor, block_id: str, removed_payload: dict) -> "ApplyLogEntry":
        """A successful delete — carry the removed block id + its **full** removed payload
        (elements + style) so the destructive edit is reconstructable."""
        return cls(outcome="deleted", anchor=anchor, block_id=block_id, removed_payload=removed_payload)

    @classmethod
    def commented(cls, *, anchor: LoggedAnchor, comment_record: dict) -> "ApplyLogEntry":
        """A whole-document comment was created — carry its id, its replies and the bot
        ``author_id`` it landed as (which is what a later removal is judged against)."""
        return cls(outcome="commented", anchor=anchor, comment_record=comment_record)

    @classmethod
    def comment_removed(cls, *, anchor: LoggedAnchor, comment_record: dict) -> "ApplyLogEntry":
        """A comment thread was removed — carry the ids of every reply deleted, in order.
        Removal is irreversible, so this record is the whole account of it."""
        return cls(outcome="comment-removed", anchor=anchor, comment_record=comment_record)

    # -- the apply-time disposition boundary's three outcomes -------------------- #

    @classmethod
    def applied_unverified(cls, *, anchor: LoggedAnchor, refusal: Refusal,
                           block_id: Optional[str] = None) -> "ApplyLogEntry":
        """The write returned and a step after it failed — **applied**, with an incomplete
        verification record. ``block_id`` is carried when the failing step knew it."""
        return cls(outcome="applied-unverified", anchor=anchor, refusal=refusal,
                   block_id=block_id)

    @classmethod
    def failed(cls, *, anchor: LoggedAnchor, refusal: Refusal) -> "ApplyLogEntry":
        """The attempt leaves whether it landed **indeterminate** — never mislabelled a
        refusal, because "nothing landed" would be a guess."""
        return cls(outcome="failed", anchor=anchor, refusal=refusal)

    @classmethod
    def not_attempted(cls, *, anchor: LoggedAnchor, refusal: Refusal) -> "ApplyLogEntry":
        """The batch halted earlier and this entry never ran — logged, never dropped."""
        return cls(outcome="not-attempted", anchor=anchor, refusal=refusal)

    @property
    def is_applied(self) -> bool:
        """Whether this entry's change **LANDED** on the document.

        The one place the outcome vocabulary is split into landed / did-not-land, so
        :attr:`ApplyLog.applied` and :attr:`ApplyLog.refusals` cannot answer it differently.
        ``applied-unverified`` is here because the write returned; ``failed`` is NOT, because
        indeterminate is not the same claim as landed and this accessor may not guess.
        """
        return self.outcome in _LANDED_OUTCOMES

    def to_dict(self) -> dict:
        d: dict = {"outcome": self.outcome, "anchor": self.anchor.to_dict()}
        if self.outcome == "applied":
            d["block_id"] = self.block_id
            d["before"] = self.before
            d["after"] = self.after
            # Trailing + conditional, the ``mutating_write_calls`` pattern: an edit that
            # moved no checkbox serializes exactly as it did before LD-574.
            if self.todo_done is not None:
                d["todo_done"] = self.todo_done
        elif self.outcome == "inserted":
            d["created_block_ids"] = list(self.created_block_ids)
            # Trailing + conditional, the ``comment_record`` pattern: an entry carrying no
            # measurement serializes exactly as it did before this shipped. ``atomic`` is
            # derived at every projection rather than stored, so the flag cannot drift away
            # from the count it is a consequence of.
            if self.mutating_write_calls is not None:
                d[INSERT_WRITE_CALLS_KEY] = self.mutating_write_calls
                d[INSERT_ATOMIC_KEY] = self.atomic
        elif self.outcome == "deleted":
            d["block_id"] = self.block_id
            d["removed_payload"] = self.removed_payload
        elif self.outcome in ("commented", "comment-removed"):
            d["comment_record"] = self.comment_record
        elif self.outcome in _DISPOSITION_OUTCOMES:
            # The boundary's three. They carry the classifying refusal, and
            # ``applied-unverified`` additionally carries the block it wrote when the failing
            # step knew it — trailing + conditional, the ``comment_record`` pattern.
            d["refusal"] = self.refusal.to_dict() if self.refusal else None
            if self.block_id is not None:
                d["block_id"] = self.block_id
        else:
            d["refusal"] = self.refusal.to_dict() if self.refusal else None
            # Trailing + conditional (the partial-removal case only), so every refusal that
            # shipped before LD-202 serializes byte-identically.
            if self.comment_record is not None:
                d["comment_record"] = self.comment_record
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ApplyLogEntry":
        anchor = _anchor_from_dict(d["anchor"])
        outcome = d["outcome"]
        if outcome == "applied":
            return cls.applied(
                anchor=anchor,
                block_id=d["block_id"],
                before=d["before"],
                after=d["after"],
                todo_done=d.get("todo_done"),
            )
        if outcome == "inserted":
            # ``atomic`` is not read back: it is derived from the count, so reading it would
            # let a hand-edited log carry a flag its own number contradicts.
            return cls.inserted(anchor=anchor,
                                created_block_ids=tuple(d["created_block_ids"]),
                                mutating_write_calls=d.get(INSERT_WRITE_CALLS_KEY))
        if outcome == "deleted":
            return cls.deleted(anchor=anchor, block_id=d["block_id"], removed_payload=d["removed_payload"])
        if outcome == "commented":
            return cls.commented(anchor=anchor, comment_record=d["comment_record"])
        if outcome == "comment-removed":
            return cls.comment_removed(anchor=anchor, comment_record=d["comment_record"])
        if outcome == "applied-unverified":
            return cls.applied_unverified(anchor=anchor,
                                          refusal=Refusal.from_dict(d["refusal"]),
                                          block_id=d.get("block_id"))
        if outcome == "failed":
            return cls.failed(anchor=anchor, refusal=Refusal.from_dict(d["refusal"]))
        if outcome == "not-attempted":
            return cls.not_attempted(anchor=anchor, refusal=Refusal.from_dict(d["refusal"]))
        return cls.refused(anchor=anchor, refusal=Refusal.from_dict(d["refusal"]),
                           comment_record=d.get("comment_record"))


# The contract is written ONCE (:data:`INSERT_COST_CONTRACT`) and projected into the class's
# own docstring, so ``help(ApplyLogEntry)`` and the shipped guide cannot state it differently.
ApplyLogEntry.__doc__ = (ApplyLogEntry.__doc__ or "").replace(
    "``INSERT_COST_CONTRACT``", INSERT_COST_CONTRACT)


@dataclass(frozen=True)
class ApplyLog:
    """An ordered log of :class:`ApplyLogEntry` — one per processed edit request.

    JSON-round-trippable as a whole via :meth:`to_json` / :meth:`from_json` (or
    :meth:`to_dict` / :meth:`from_dict` for the plain structure). This is what the
    apply engine returns to the consumer; the consumer decides what to do with
    its own state afterward (larkdocio does not).

    :attr:`revision_guard` carries the batch's **whole-document staleness disclosure**
    (``"active"`` / ``"unavailable"``, copied from the plan that produced this log),
    so a consumer holding only the apply-log can tell whether the document-level
    compare-and-swap was in force. It sits on the **log**, not on each entry, because the
    guard is a property of the batch by construction: it either refuses the whole batch or
    none of it. ``None`` means "not stated" and is **omitted** from :meth:`to_dict`, so a
    hand-built log's wire form is byte-unchanged.

    :attr:`halt` is the batch-level disclosure the apply-time disposition boundary sets: which
    entry stopped the batch, why, and how many entries were therefore never attempted. It sits
    on the **log** rather than being inferred from the entries because "the batch halted" is a
    statement about the run, and a consumer must not have to reconstruct it by scanning for the
    first non-landing outcome. ``None`` means the batch ran to the end, and it is **omitted**
    from :meth:`to_dict` when unset, so every log written before the boundary shipped
    serializes byte-identically.
    """

    entries: Tuple[ApplyLogEntry, ...] = ()
    revision_guard: Optional[str] = None
    halt: Optional[dict] = None

    def __post_init__(self):
        object.__setattr__(self, "entries", tuple(self.entries))

    def __iter__(self):
        """Iterate the entries (LD-458). ``for entry in log:`` is the obvious idiom and it
        used to raise ``TypeError`` — **after** a live write had already landed."""
        return iter(self.entries)

    def __len__(self) -> int:
        """How many entries — 1:1 with the plan, so this is the batch's size."""
        return len(self.entries)

    @property
    def applied(self) -> Tuple[ApplyLogEntry, ...]:
        """Every entry whose change **landed** — applied / inserted / deleted / commented /
        comment-removed, plus ``applied-unverified`` (the write returned; only its
        verification record is incomplete). Answered by :attr:`ApplyLogEntry.is_applied`, so
        this and :attr:`refusals` split the log at exactly one place."""
        return tuple(e for e in self.entries if e.is_applied)

    @property
    def refusals(self) -> Tuple[ApplyLogEntry, ...]:
        """Every entry that did **not** land — ``refused``, and since the apply-time
        disposition boundary also ``failed`` (whether it landed is indeterminate, and
        indeterminate is not landed) and ``not-attempted``. This is the set
        :func:`larkdocio.errors.gate_refusals` raises on unless the caller passed
        ``allow_partial=True``."""
        return tuple(e for e in self.entries if not e.is_applied)

    @property
    def not_attempted(self) -> Tuple[ApplyLogEntry, ...]:
        """Every entry the batch never reached because it halted earlier."""
        return tuple(e for e in self.entries if e.outcome == "not-attempted")

    @property
    def indeterminate(self) -> Tuple[ApplyLogEntry, ...]:
        """Every entry whose attempt leaves whether it landed **unknown** — the entries a
        consumer has to reconcile by reading the document rather than by re-running."""
        return tuple(e for e in self.entries if e.outcome == "failed")

    def to_dict(self) -> dict:
        d: dict = {"entries": [e.to_dict() for e in self.entries]}
        if self.revision_guard is not None:
            d["revision_guard"] = self.revision_guard
        if self.halt is not None:
            d["halt"] = self.halt
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ApplyLog":
        return cls(entries=tuple(ApplyLogEntry.from_dict(e) for e in d.get("entries", [])),
                   revision_guard=d.get("revision_guard"),
                   halt=d.get("halt"))

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), **kwargs)

    @classmethod
    def from_json(cls, s: str) -> "ApplyLog":
        return cls.from_dict(json.loads(s))
