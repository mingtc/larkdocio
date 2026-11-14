"""Match an edited projection back to the document it came from, and say what changed.

A block-identity projection hands an agent Markdown that names each of its blocks. The
agent edits that Markdown and hands the whole thing back. **This module is the half in
between**: it matches every marker to a real block, works out per block whether it is
unchanged, edited, newly inserted, deleted or conserved, and hands back a typed
:class:`ReconciliationPlan` that says so. It issues **no requests and makes no network
call** — reading the plan is the point, and compiling it is a separate step.

Four rules do all the work, and each closes a way of getting this catastrophically wrong.

**1. Identity comes from the emitted id set, never from content.** Matching resolves a
marker against the identifiers the projection itself emitted
(:attr:`~larkdocio.model.projection.BlockIdProjection.block_ids`) — exactly one or
refuse. An id outside that set is **invented** and refuses, whether an editor hallucinated
it or a consumer's own prose happens to be marker-shaped. There is deliberately **no
content-based fallback**: "anything marker-shaped" is not an identity test, and a fallback
would guess in exactly the case where guessing destroys content.

**2. A segment is the marked block PLUS any unmarked content that travels with it.**
Everything between one marker and the next belongs to that marker. Inside a segment the
marked block is located by matching the block's own text; whatever else is there is
**content the editor added**, planned as an insert anchored to that surviving marker —
before or after the block, whichever side it arrived on. An insert is therefore **never
anchored to another inserted block**, which is what keeps a compiled batch free of
requests that depend on each other. Content that arrives ahead of the first marker anchors
at the document root.

**3. Comparison happens in the DECODED domain.** The projection escapes literal text (that
is what makes a marker unforgeable), so an editor that merely normalized ``99\\.9`` back to
``99.9`` has changed nothing. Every comparison here runs
:func:`~larkdocio.model.projection.unescape_literals` — the exact inverse of the reader's
own escaper — over both sides first. An undecodable piece refuses rather than guesses.

**4. Absence is evidence about the Markdown, not an instruction about the document.** A
block whose marker did not come back is **not** deleted: a marker gone with its content is
formally indistinguishable from a heavy rewrite that dropped the marker, and the two
readings differ by destroying content. So absence **refuses** unless the caller passes
:attr:`AbsentBlockDisposition.DELETE`, and an **opaque** block is conserved even then.

What this rung deliberately refuses rather than attempts: a **reorder** (a move is not
expressible in the shipped request families, and faking it as delete+insert would destroy
the block's identity and everything anchored to it), a **block-type mutation** (a paragraph
edited into a heading — the working route is delete + insert as two commits), and a segment
whose marked block cannot be located among several pieces of content. Opaque blocks — the
images, tables, embeds and unknown types the authoring dialect cannot recreate — are
**conserved**: never edited, never deleted, never re-created, even when the edited
projection dropped them entirely or changed their visible text.

    >>> from larkdocio.model import project_block_ids       # doctest: +SKIP
    >>> projection = project_block_ids(tree)                # doctest: +SKIP
    >>> plan = reconcile(projection, edited_markdown)       # doctest: +SKIP
    >>> plan.ok, plan.change_count                          # doctest: +SKIP
    (True, 1)
"""
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from markdown_it.tree import SyntaxTreeNode

from larkdocio.errors import LarkEscapeError
from larkdocio.model.projection import BlockIdProjection, unescape_literals

# The one canonical marker line form, imported rather than re-expressed: a second regular
# expression for the marker is a second definition of identity (LD-230 owns the first).
from larkdocio.model.renderer import (
    BLOCK_ID_MARKER_LINE_RE,
    BLOCK_ID_MARKER_SHAPED_LINE_RE,
    block_id_marker,
)
from larkdocio.write.compose import _parser
from larkdocio.write.model import (
    InsertPosition,
    NewBlockKind,
    Refusal,
    RefusalReason,
    RefusedError,
)
from larkdocio.write.model.requests import NewParagraph

__all__ = [
    "ABSENT_DISPOSITION_MEANINGS",
    "CONSERVED_BODY_DIFFERS_MEANING",
    "RECONCILIATION_CONTRACT",
    "RECONCILIATION_REFUSAL_REASONS",
    "RECONCILIATION_STATE_MEANINGS",
    "AbsentBlockDisposition",
    "ReconciliationEntry",
    "ReconciliationPlan",
    "ReconciliationState",
    "reconcile",
]

#: What a reconciliation promises, shipped WITH the answer — a consumer holding only the
#: wheel cannot open the document these rules were written in.
RECONCILIATION_CONTRACT = (
    "A marker resolves only against the identifiers the projection itself emitted, "
    "exactly one or refuse: an identifier outside that set names no block and refuses, "
    "and there is no content-based fallback. A marker's segment is the marked block plus "
    "any unmarked content that came back with it, so added content is planned as an "
    "insert anchored to that surviving marker (or to the document root ahead of the "
    "first one) and never to another inserted block. Every comparison happens in the "
    "decoded domain, so an editor that only normalized the projection's escaping changes "
    "nothing. A block whose marker did not come back is NOT deleted: absence refuses "
    "unless the caller dispositions the deletion explicitly. An opaque block is conserved "
    "under either disposition — never edited, never deleted, never re-created — even if "
    "the edited Markdown dropped it entirely or changed its visible text. A reorder and a "
    "block-type change are refused, not approximated. The plan issues no request and "
    "makes no network call; reading it before anything is applied is the point. "
    "The supported shape is a whole document, in and out: hand the editor the whole "
    "projection and hand the whole edited document back. A patch, a unified diff or an "
    "edited fragment is not supported and is not tested — nothing here accepts one, and a "
    "fragment describes a document that lost every block the fragment left out. Apply a "
    "patch to the projection yourself and pass the complete result."
)


#: What a conserved-opaque entry's ``body_differs`` disclosure means — the ONE definition.
#: Every documented spelling of it (the shipped state meanings, the guide) projects from this
#: string rather than restating it, so a later "simplification" to *the body was edited*
#: cannot ship in one place while the truth stays in another. The fact is ambiguous BY
#: CONSTRUCTION and the wording carries the ambiguity instead of resolving it: refusing on
#: this predicate would produce refusals on documents nobody edited, wherever an opaque
#: projection is not round-trip stable.
CONSERVED_BODY_DIFFERS_MEANING = (
    "body_differs discloses that the block's body read back differently from the Markdown "
    "the projection emitted for it. That is one fact and it settles nothing: EITHER the "
    "consumer edited that body, OR the projection reshaped it and the editor normalised the "
    "reshaping. The plan asserts neither reading and compiles nothing either way — the block "
    "is conserved, left exactly alone. None means no opinion, which is not the same as "
    "False: a conserved block whose marker never came back has no read-back to compare."
)


#: Every typed reason a reconciliation can refuse with, so "what can this tell me?" is a
#: question the registry answers rather than one a consumer discovers by hitting each.
#: The last two are the authoring compiler's own, propagated unchanged when the edited
#: Markdown names something the creatable set has no block for — one vocabulary end to
#: end rather than a second word for the same fact.
RECONCILIATION_REFUSAL_REASONS = (
    RefusalReason.MARKER_INVENTED,
    RefusalReason.MARKER_DUPLICATED,
    RefusalReason.MARKER_ABSENT,
    RefusalReason.MARKER_DROPPED,
    RefusalReason.MARKER_RELOCATED,
    RefusalReason.MARKER_MANGLED,
    RefusalReason.MARKER_ORPHANED,
    RefusalReason.MARKER_ORDER_CHANGED,
    RefusalReason.CONSERVED_BLOCK_RE_CREATED,
    RefusalReason.BLOCK_TYPE_MUTATION,
    RefusalReason.SEGMENT_AMBIGUOUS,
    RefusalReason.UNMARKED_CONTENT_CHANGED,
    RefusalReason.UNDECODABLE_TEXT,
    RefusalReason.NOT_IN_DIALECT,
    RefusalReason.MERGE_NOT_EXPRESSIBLE,
    #: LD-574 — the compiler's own: a counted change whose compiled request set would write
    #: bytes identical to what is live. Listed here, in the reconciliation registry, because
    #: it is reached by reconciling and compiling a projection and a consumer discovering
    #: "what can this tell me?" reads this tuple, not the compiler's source.
    RefusalReason.CHANGE_NOT_EXPRESSIBLE,
)


class ReconciliationState(Enum):
    """What a reconciliation found for one block. The closed vocabulary the plan answers
    in, and the ``value`` is the stable serialized form."""

    #: The block's decoded text is what it always was. Compiles to nothing.
    UNCHANGED = "unchanged"
    #: The block's decoded text changed, and its type did not. Compiles to one edit.
    EDITED = "edited"
    #: Content the editor added, anchored to a surviving block (or to the document root).
    #: Carries no ``block_id`` — the block does not exist yet.
    INSERTED = "inserted"
    #: The block's marker did not come back **and** the caller dispositioned absence as
    #: deletion. Never produced by default.
    DELETED = "deleted"
    #: The block is one the authoring dialect cannot recreate, so it is left exactly
    #: alone — not edited, not deleted, not re-created, whatever the edited projection did
    #: with it.
    CONSERVED_OPAQUE = "conserved-opaque"


class AbsentBlockDisposition(Enum):
    """What the caller wants done about a block whose marker did not come back.

    ``REFUSE`` is the default and the safe reading: absence is ambiguous, and the
    ambiguity is resolved by asking rather than by destroying content. ``DELETE`` is the
    caller stating that they meant it — and even then, an opaque block is conserved.
    """

    REFUSE = "refuse"
    DELETE = "delete"


#: What each state means, shipped alongside the vocabulary rather than left to prose a
#: consumer cannot reach.
RECONCILIATION_STATE_MEANINGS = {
    ReconciliationState.UNCHANGED.value: (
        "The block's decoded text is what the projection emitted, so nothing is "
        "compiled for it — a no-op reconciliation rewrites nothing."
    ),
    ReconciliationState.EDITED.value: (
        "The block's decoded text changed and its type did not, so it compiles to one "
        "edit against that block's own identifier."
    ),
    ReconciliationState.INSERTED.value: (
        "Content the editor added inside a surviving marker's segment (or ahead of the "
        "first marker), compiled as an insert anchored to that marker or to the document "
        "root — never to another inserted block. It carries no identifier of its own."
    ),
    ReconciliationState.DELETED.value: (
        "The block's marker did not come back AND the caller dispositioned absence as "
        "deletion. Never produced by default."
    ),
    ReconciliationState.CONSERVED_OPAQUE.value: (
        "The authoring dialect cannot recreate this block, or the reader's Markdown for "
        "it is a reshaping rather than its own content, so it is left exactly alone: not "
        "edited, not deleted, not re-created, whatever the edited Markdown did with it. "
        # Projected from the one definition above rather than restated, so the shipped
        # capability record and the guide cannot drift from the field's own meaning.
        + CONSERVED_BODY_DIFFERS_MEANING
    ),
}

#: What each disposition means. The default is the safe reading, and it is stated.
ABSENT_DISPOSITION_MEANINGS = {
    AbsentBlockDisposition.REFUSE.value: (
        "The default. A block whose marker did not come back refuses, naming the block "
        "and quoting the text it still has in the document — a marker dropped together "
        "with its content cannot be told apart from a rewrite that dropped the marker, "
        "and the two readings differ by destroying content."
    ),
    AbsentBlockDisposition.DELETE.value: (
        "The caller states that the omission was meant, so an absent editable block "
        "compiles to a delete. An opaque block is still conserved."
    ),
}

#: The states that compile into a request. Everything else is a statement about the
#: document, not an instruction to change it.
_CHANGE_STATES = frozenset(
    {ReconciliationState.EDITED, ReconciliationState.INSERTED, ReconciliationState.DELETED}
)


@dataclass(frozen=True)
class ReconciliationEntry:
    """One block's verdict, with the images the verdict is about.

    Non-forgeable in the manner of the other plan objects: the combination of state and
    images is validated on construction, so an entry cannot claim to be an edit with no
    pre-image, a deletion carrying a post-image, an unchanged block whose two images
    differ, or an insert that names a block id it cannot have. Build one through the
    classmethod named for the state.

    ``before`` and ``after`` are **decoded** text — the domain the comparison happened in.
    ``after_markdown`` is the edited projection's own Markdown for the entry, kept
    alongside because an insert has to be compiled from Markdown and decoding it first
    would turn escaped literal text back into markup. ``before_markdown`` is the same thing
    for the **pre-image** — the projection's own Markdown for the block as it stands — and
    it is carried for exactly one reason: the compiler has to know what its request
    would be *replacing*, and reading that out of the decoded text instead is a false-refusal
    generator. A block whose live text is ``a *b*`` projects as ``a \\*b\\*``; composing the
    decoded form parses the asterisks as markup, so a caller who really did rewrite it to
    ``a b`` would look like a no-op. Both images therefore travel as Markdown and are
    composed by the same dialect, which is what makes the comparison apples-to-apples.

    ``body_differs`` is the CONSERVED_OPAQUE state's own disclosure and only ever that
    state's — an entry whose state cannot hold an opinion about a read-back does not carry
    one, and construction enforces that the way it enforces the image invariants above. Its
    meaning is stated once, in :data:`CONSERVED_BODY_DIFFERS_MEANING`, and nowhere restated.
    What a consumer may rely on: ``True`` and ``False`` are answers about a conserved block,
    ``None`` is **no opinion** and not ``False``, and the key is trailing and conditional in
    :meth:`to_dict` — an entry with nothing to disclose serializes byte-identically to every
    plan written before this field existed, and :meth:`from_dict` accepts a plan written
    without it.
    """

    state: ReconciliationState
    block_id: Optional[str] = None
    before: Optional[str] = None
    after: Optional[str] = None
    after_markdown: Optional[str] = None
    anchor_block_id: Optional[str] = None
    anchor_position: Optional[str] = None
    opaque_kind: Optional[str] = None
    before_markdown: Optional[str] = None
    body_differs: Optional[bool] = None

    def __post_init__(self):
        state = self.state
        if not isinstance(state, ReconciliationState):
            raise TypeError(
                f"ReconciliationEntry.state must be a ReconciliationState, got "
                f"{type(state).__name__}"
            )
        if state is ReconciliationState.INSERTED:
            if self.block_id is not None:
                raise ValueError(
                    "an inserted entry cannot carry a block_id — the block does not exist "
                    "until the request that creates it is applied"
                )
            if not self.after:
                raise ValueError("an inserted entry must carry the content to insert")
            if self.before is not None:
                raise ValueError("an inserted entry has no pre-image")
            if self.anchor_position not in (
                InsertPosition.BEFORE.value, InsertPosition.AFTER.value
            ):
                raise ValueError(
                    "an inserted entry must say which side of its anchor it goes on "
                    f"('before' or 'after'), got {self.anchor_position!r}"
                )
        elif not self.block_id:
            raise ValueError(
                f"a {state.value!r} entry must name the block it is about"
            )

        if state is ReconciliationState.EDITED:
            if self.before is None or self.after is None:
                raise ValueError(
                    f"an edited entry must carry both images (block {self.block_id!r})"
                )
            if self.before == self.after:
                raise ValueError(
                    f"an edited entry whose images are equal is not an edit "
                    f"(block {self.block_id!r})"
                )
        if state is ReconciliationState.UNCHANGED and self.before != self.after:
            raise ValueError(
                f"an unchanged entry cannot carry two different images "
                f"(block {self.block_id!r})"
            )
        if state in (ReconciliationState.DELETED, ReconciliationState.CONSERVED_OPAQUE):
            if self.after is not None:
                raise ValueError(
                    f"a {state.value!r} entry has no post-image — carrying one would "
                    f"describe a write that must not happen (block {self.block_id!r})"
                )
        if self.body_differs is not None:
            if not isinstance(self.body_differs, bool):
                raise TypeError(
                    f"ReconciliationEntry.body_differs must be a bool or None, got "
                    f"{type(self.body_differs).__name__}"
                )
            if state is not ReconciliationState.CONSERVED_OPAQUE:
                raise ValueError(
                    f"only a conserved-opaque entry discloses whether its body read back "
                    f"differently — a {state.value!r} entry has no such opinion to carry "
                    f"(block {self.block_id!r})"
                )

    # -- factories, one per state ------------------------------------------------ #

    @classmethod
    def unchanged(cls, block_id: str, text: str) -> "ReconciliationEntry":
        """The block came back exactly as it went out."""
        return cls(ReconciliationState.UNCHANGED, block_id, before=text, after=text)

    @classmethod
    def edited(
        cls, block_id: str, before: str, after: str, after_markdown: str,
        before_markdown: Optional[str] = None,
    ) -> "ReconciliationEntry":
        """The block's decoded text changed and its type did not.

        ``before_markdown`` is optional only so a plan rebuilt from an older dict still
        constructs; the reconciler always passes it, and the compiler treats its absence as
        "the pre-image is not comparable" rather than as evidence of anything.
        """
        return cls(
            ReconciliationState.EDITED,
            block_id,
            before=before,
            after=after,
            after_markdown=after_markdown,
            before_markdown=before_markdown,
        )

    @classmethod
    def inserted(
        cls,
        after: str,
        after_markdown: str,
        anchor_block_id: Optional[str],
        anchor_position: str,
    ) -> "ReconciliationEntry":
        """Content the editor added, anchored to a surviving block or to the root."""
        return cls(
            ReconciliationState.INSERTED,
            after=after,
            after_markdown=after_markdown,
            anchor_block_id=anchor_block_id,
            anchor_position=anchor_position,
        )

    @classmethod
    def deleted(cls, block_id: str, before: str) -> "ReconciliationEntry":
        """The block's marker did not come back and the caller dispositioned deletion."""
        return cls(ReconciliationState.DELETED, block_id, before=before)

    @classmethod
    def conserved_opaque(
        cls, block_id: str, before: str, opaque_kind: Optional[str] = None,
        body_differs: Optional[bool] = None,
    ) -> "ReconciliationEntry":
        """The block is left exactly alone, whatever the edited projection did.

        ``body_differs`` defaults to ``None`` — no opinion — because a caller that made no
        comparison must not imply one; see :data:`CONSERVED_BODY_DIFFERS_MEANING`.
        """
        return cls(
            ReconciliationState.CONSERVED_OPAQUE,
            block_id,
            before=before,
            opaque_kind=opaque_kind,
            body_differs=body_differs,
        )

    def to_dict(self) -> dict:
        """The JSON-serializable form — plain types only, keys always present."""
        return {
            "state": self.state.value,
            "block_id": self.block_id,
            "before": self.before,
            "after": self.after,
            "after_markdown": self.after_markdown,
            "anchor_block_id": self.anchor_block_id,
            "anchor_position": self.anchor_position,
            "opaque_kind": self.opaque_kind,
            # Trailing + conditional (LD-574), the convention every additive plan field on
            # this surface follows — both of the ones below do: an entry that carries no
            # pre-image Markdown (every state but EDITED) and nothing to disclose about a
            # read-back (every state but CONSERVED_OPAQUE) serializes byte-identically to
            # every plan written before those fields existed.
            **({"before_markdown": self.before_markdown}
               if self.before_markdown is not None else {}),
            **({"body_differs": self.body_differs}
               if self.body_differs is not None else {}),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ReconciliationEntry":
        """Rebuild from :meth:`to_dict`, through the same validation."""
        return cls(
            state=ReconciliationState(d["state"]),
            block_id=d.get("block_id"),
            before=d.get("before"),
            after=d.get("after"),
            after_markdown=d.get("after_markdown"),
            anchor_block_id=d.get("anchor_block_id"),
            anchor_position=d.get("anchor_position"),
            opaque_kind=d.get("opaque_kind"),
            before_markdown=d.get("before_markdown"),
            body_differs=d.get("body_differs"),
        )


@dataclass(frozen=True)
class ReconciliationPlan:
    """What a reconciliation found, whole — every block's verdict, or every reason it
    refused.

    A plan either **describes** the reconciliation or **refuses** it; it never does half of
    each. A document whose marker state is ambiguous is exactly the document where a
    partial plan is dangerous, so a plan carrying refusals carries no entries, and that is
    enforced on construction rather than left to a convention.

    Read it before anything is applied: :attr:`changes` is precisely the set that would
    compile into requests, and :attr:`touched_block_ids` is every identifier one of those
    requests would name — so "does anything in this plan touch that block?" is a question
    the plan answers, not one a caller has to re-derive.
    """

    entries: Tuple[ReconciliationEntry, ...] = ()
    refusals: Tuple[Refusal, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "entries", tuple(self.entries))
        object.__setattr__(self, "refusals", tuple(self.refusals))
        if self.refusals and self.entries:
            raise ValueError(
                "a reconciliation that refuses refuses WHOLE: a plan carrying refusals "
                "cannot also carry entries, because a half-plan over a document whose "
                "marker state is ambiguous is the dangerous artifact"
            )

    @property
    def ok(self) -> bool:
        """Whether the reconciliation produced a plan rather than refusing."""
        return not self.refusals

    @property
    def changes(self) -> Tuple[ReconciliationEntry, ...]:
        """The entries that would compile into a request — everything else is a
        statement about the document, not an instruction to change it."""
        return tuple(e for e in self.entries if e.state in _CHANGE_STATES)

    @property
    def change_count(self) -> int:
        """How many requests this plan would compile into. **Zero for a no-op.**"""
        return len(self.changes)

    @property
    def touched_block_ids(self) -> Tuple[str, ...]:
        """Every identifier a compiled request would name — as a target or as an
        anchor — in document order, each once."""
        seen: List[str] = []
        for entry in self.changes:
            for block_id in (entry.block_id, entry.anchor_block_id):
                if block_id and block_id not in seen:
                    seen.append(block_id)
        return tuple(seen)

    @property
    def conserved_block_ids(self) -> Tuple[str, ...]:
        """The blocks this plan conserves — left exactly alone by construction."""
        return tuple(
            e.block_id
            for e in self.entries
            if e.state is ReconciliationState.CONSERVED_OPAQUE and e.block_id
        )

    @property
    def conserved_block_ids_that_read_back_differently(self) -> Tuple[str, ...]:
        """The conserved blocks whose bodies came back changed, in document order.

        A subset of :attr:`conserved_block_ids`, and a **disclosure** rather than a verdict:
        see :data:`CONSERVED_BODY_DIFFERS_MEANING`. A conserved entry carrying no opinion
        (``body_differs is None``) is not in here — absence is not a denial.
        """
        return tuple(
            e.block_id
            for e in self.entries
            if e.state is ReconciliationState.CONSERVED_OPAQUE
            and e.block_id
            and e.body_differs
        )

    def to_dict(self) -> dict:
        """The JSON-serializable form: lists, never tuples, all the way down."""
        return {
            "entries": [e.to_dict() for e in self.entries],
            "refusals": [r.to_dict() for r in self.refusals],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ReconciliationPlan":
        """Rebuild from :meth:`to_dict`, through the same validation."""
        return cls(
            entries=tuple(
                ReconciliationEntry.from_dict(e) for e in d.get("entries", ())
            ),
            refusals=tuple(Refusal.from_dict(r) for r in d.get("refusals", ())),
        )


# --------------------------------------------------------------------------- #
# Segmentation — the edited projection, cut at its markers.                    #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class _Segment:
    """One marker and everything that travels with it. ``block_id`` is ``None`` for the
    head segment — whatever arrived ahead of the first marker."""

    block_id: Optional[str]
    body: str


@dataclass
class _Scan:
    segments: List[_Segment] = field(default_factory=list)
    order: List[str] = field(default_factory=list)
    invented: List[str] = field(default_factory=list)
    duplicated: List[str] = field(default_factory=list)
    #: Every marker-shaped line that is NOT the canonical form, as ``(line number, the
    #: line's own bytes)`` — quoted back rather than repaired.
    mangled: List[Tuple[int, str]] = field(default_factory=list)
    #: Where each emitted id's marker was seen, by 1-based line number. A duplicate is
    #: named by both of its occurrences rather than by the bare fact that there are two.
    occurrences: Dict[str, List[int]] = field(default_factory=dict)


def _scan(text: str, known_ids: Sequence[str]) -> _Scan:
    """Cut ``text`` into segments at every marker whose id was emitted.

    A marker-shaped line carrying an id that was **not** emitted is recorded as invented
    and dropped from the body: it is not identity, and leaving it in the text would let it
    be compared as content. A line that is marker-*shaped* but not the canonical form is
    recorded as **mangled** and left exactly where it is: it is not identity either, and
    it is not repaired into the marker it resembles — repairing would guess whether it was
    a marker at all.
    """
    known = set(known_ids)
    scan = _Scan()
    head: List[str] = []
    current_id: Optional[str] = None
    current: List[str] = []
    indent = ""

    def close():
        if current_id is not None:
            scan.segments.append(_Segment(current_id, _dedent("\n".join(current), indent)))

    for number, line in enumerate(text.splitlines(), start=1):
        bare = line.rstrip("\r\n")
        match = BLOCK_ID_MARKER_LINE_RE.match(bare)
        if match is None:
            if BLOCK_ID_MARKER_SHAPED_LINE_RE.match(bare):
                scan.mangled.append((number, bare))
            (current if current_id is not None else head).append(line)
            continue
        block_id = match.group(1)
        if block_id not in known:
            scan.invented.append(block_id)
            continue
        scan.occurrences.setdefault(block_id, []).append(number)
        if block_id in scan.order:
            scan.duplicated.append(block_id)
            continue
        close()
        scan.order.append(block_id)
        current_id = block_id
        current = []
        indent = line[: len(line) - len(line.lstrip(" \t>"))]
    close()
    scan.segments.insert(0, _Segment(None, "\n".join(head)))
    return scan


def _dedent(body: str, indent: str) -> str:
    """Strip the marker's own line-leading prefix off its block's lines.

    A marker takes the indentation of the block it introduces, so a nested list item's
    segment arrives indented. Comparing it against the same block's text at its own
    indentation is what the diff is about, not the indentation itself.
    """
    if not indent:
        return body
    return "\n".join(
        line[len(indent):] if line.startswith(indent) else line
        for line in body.split("\n")
    )


@lru_cache(maxsize=1)
def _md():
    # The compiler's own parser, deliberately: splitting an edited segment with a second
    # Markdown configuration would be a second definition of the dialect, and the pieces
    # this splits out are exactly the pieces `compose()` will later compile.
    return _parser()


def _units(text: str) -> List[str]:
    """Split ``text`` into its top-level Markdown blocks, in order.

    A segment's content is one or more whole Markdown blocks, and the boundary between
    them is the parser's, not a blank-line heuristic — a fenced code block holding a blank
    line is one unit, and so is a list or a table.
    """
    stripped = text.strip("\n")
    if not stripped.strip():
        return []
    lines = stripped.split("\n")
    units = []
    for child in SyntaxTreeNode(_md().parse(stripped)).children:
        if child.map is None:
            continue
        start, end = child.map
        chunk = "\n".join(lines[start:end]).strip("\n").rstrip()
        if chunk.strip():
            units.append(chunk)
    return units or [stripped.strip()]


def _decode(text: str) -> str:
    """The projection's escaping, undone. Refuses rather than guesses."""
    return unescape_literals(text)


def _decoded_units(body: str) -> Optional[List[str]]:
    """A piece of Markdown as its decoded top-level units, or ``None`` if it cannot be
    decoded at all. Undecodable text is not "no match" — it is not comparable, which is a
    different fact and one the caller must not read as evidence either way."""
    try:
        return [_decode(u) for u in _units(body)]
    except LarkEscapeError:
        return None


class _Incomparable:
    """A returned unit that could not be decoded, standing in its own POSITION.

    Undecodable text *"is not comparable, which is a different fact and one the caller must
    not read as evidence either way"* (:func:`_decoded_units`). A placeholder is what makes
    both halves of that true at once: it matches nothing, so it is never evidence a block's
    text came back; and it occupies the position, so the units either side of it cannot
    close over the gap and manufacture the claim that the text came back *whole*.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return "<undecodable unit>"


_INCOMPARABLE = _Incomparable()


def _comparable_units(body: str) -> List[object]:
    """``body``'s top-level units, decoded, with each undecodable unit held as
    :data:`_INCOMPARABLE` rather than dropped.

    Per unit, not per segment: :func:`_decoded_units` answers all-or-nothing because its
    two callers compare a whole block's text, but the RETURNED corpus is a document, and
    one unreadable unit in it is not evidence about any other unit (LD-634).
    """
    units: List[object] = []
    for unit in _units(body):
        try:
            units.append(_decode(unit))
        except LarkEscapeError:
            units.append(_INCOMPARABLE)
    return units


def _all_units(scan: "_Scan") -> List[object]:
    """Every unit the edited Markdown came back with, in order, markers aside — decoded
    where it can be, and held as an incomparable placeholder where it cannot.

    This is what tells a **dropped marker** (the block's own text plainly came back, just
    without its marker) from a **content-absent** block (marker and content both gone) —
    the one distinction in the loss taxonomy that needs to look at the whole document
    rather than at one segment.

    **An undecodable unit does not remove its NEIGHBOURS from the corpus** (LD-634). It
    used to: the corpus was built segment by segment and a segment that failed to decode
    was skipped whole, so a single stray escape anywhere in a segment turned the narrower,
    actionable ``marker-dropped`` into ``marker-absent`` — and, because this runs at stage
    3 and ``undecodable-text`` is raised at stage 4, the consumer was never told about the
    undecodable text either. Nothing was ever written on either path; what was lost was the
    reason a consumer could act on.
    """
    out: List[object] = []
    for segment in scan.segments:
        out.extend(_comparable_units(segment.body))
    return out


def _locate(original: Sequence[str], edited: Sequence[object]) -> Optional[int]:
    """Where ``original``'s units sit inside ``edited``'s, or ``None``.

    Both sides are compared decoded. The first match wins; there is no scoring and no
    nearest-match, because a "best" match is a guess and a wrong one rewrites a block with
    another block's text.
    """
    if not original:
        return 0
    span = len(original)
    for start in range(0, len(edited) - span + 1):
        if edited[start:start + span] == list(original):
            return start
    return None


# --------------------------------------------------------------------------- #
# Block-type classification — the compiler's own answer, not a second one.     #
# --------------------------------------------------------------------------- #

def _block_type(markdown: str):
    """``(kind, level)`` for a piece of Markdown, as the authoring compiler reads it.

    Classification goes through ``compose()`` rather than a pattern of its own: the
    compiler already defines what each piece of Markdown becomes, and a second classifier
    would be a second definition that can drift from the first. A fragment the dialect
    cannot express raises, and the caller turns that into the compiler's own refusal.
    """
    from larkdocio.write.compose import compose

    blocks = compose(markdown)
    if not blocks:
        return (None, None)
    first = blocks[0]
    if isinstance(first, NewParagraph):
        return (NewBlockKind.PARAGRAPH, None)
    return (first.kind, getattr(first, "level", None))


def _type_mutation_detail(block_id: str, before, after) -> str:
    def name(pair):
        kind, level = pair
        label = kind.value if hasattr(kind, "value") else str(kind)
        return f"{label} (level {level})" if level is not None else label

    return (
        f"block {block_id}: the edited Markdown is a {name(after)} where the block is a "
        f"{name(before)}. A reconciliation never changes a block's type — the block would "
        f"have to be destroyed and re-created, losing its identifier and everything "
        f"anchored to it (comment anchors most pointedly). To make this change, delete "
        f"the block and insert the replacement as two separate commits."
    )


# --------------------------------------------------------------------------- #
# The stages, in the order reconcile() runs them. Each answers one question    #
# and the ORDER between them is behavior: a plan that refused for reason A     #
# must still refuse for reason A, so no stage may be hoisted above another.    #
# --------------------------------------------------------------------------- #

def _refuse_marker_identity(edit: "_Scan") -> List[Refusal]:
    """Stage 1 — is every marker one real block? Invented, then duplicated, then mangled.

    Nothing else can be trusted until this holds, which is why it runs first and refuses
    the whole reconciliation rather than the marker it found. The three loops report in
    that fixed order: a document wrong in more than one way names each fault once, in the
    order the identity rules are stated.
    """
    refusals: List[Refusal] = []
    for block_id in edit.invented:
        refusals.append(Refusal.marker_invented(
            f"the edited Markdown carries a marker for block {block_id!r}, which this "
            f"document's projection never emitted. Identity comes only from the "
            f"identifiers the projection returned, so this marker names no block: it was "
            f"either invented by the editor or is text that happens to be marker-shaped. "
            f"Remove it, or re-project the document and edit that."
        ))
    for block_id in edit.duplicated:
        where = edit.occurrences.get(block_id, [])
        occurrences = ", ".join(f"line {n}" for n in where) or "more than one place"
        refusals.append(Refusal.marker_duplicated(
            f"the marker for block {block_id!r} appears more than once in the edited "
            f"Markdown ({occurrences}). One identifier names one block, so there is no "
            f"honest way to choose which occurrence the block's new content is; nothing "
            f"was planned. Keep the one occurrence that holds the block's text, delete "
            f"the other, and re-run."
        ))
    for number, line in edit.mangled:
        refusals.append(Refusal.marker_mangled(
            f"line {number} of the edited Markdown is marker-shaped but is not a marker: "
            f"{line!r}. A marker is matched byte for byte, and the canonical form is "
            f"exactly {block_id_marker('<block id>')!r} on a line of its own. A "
            f"marker-shaped line that is not byte-exact is not repaired into the marker "
            f"it resembles, because it may be content that merely looks like one and "
            f"repairing it would guess which. Nothing was planned. Restore the line to "
            f"the exact form the projection emitted for that block, or — if it is your "
            f"own content rather than a marker — remove that line and re-run."
        ))
    return refusals


def _refuse_reordered_markers(
    source: "_Scan", edit: "_Scan", surviving: set
) -> Optional[Refusal]:
    """Stage 2 — did the surviving markers come back in the document's own order?

    Detection is exact: the document's order with the non-surviving ids removed, compared
    against the edited order. ``None`` means they agree. A reorder is refused rather than
    approximated, so this stage answers with at most one refusal — the first difference
    names the move, and a second name would not tell the consumer anything more.
    """
    expected = [b for b in source.order if b in surviving]
    if expected == edit.order:
        return None
    moved = [b for a, b in zip(expected, edit.order) if a != b]
    return Refusal.marker_order_changed(
        f"the surviving markers come back in a different order than the document "
        f"has them (first difference at {', '.join(repr(m) for m in moved[:2])}). "
        f"Moving a block is not expressible: the only way to express it would be to "
        f"delete the block and insert a copy, which destroys its identifier and "
        f"everything anchored to it. Nothing was planned. Restore the original order "
        f"and make the content changes on their own."
    )


def _source_block_texts(source: "_Scan") -> Dict[str, List[str]]:
    """Each projected block's own decoded units, by id — computed once for the whole diff.

    Two stages read it and neither can be correct with a private copy: the per-segment
    diff needs every *other* block's text to tell a relocation from an edit, and the
    conservation check needs the conserved block's own text to recognise it coming back
    unmarked.

    **A block whose text cannot be decoded is OMITTED, not recorded as empty** — the same
    reading of ``None`` stage 3 takes forty lines below, rather than a third one (LD-634). An absent key is *"not comparable"*, which both readers already treat as no
    evidence; recording it as ``[]`` said the block HAS no text, which is a different claim.
    The input makes this hard to hit at all — it is ``projection.markdown``, which
    larkdocio itself escaped, so a source segment that fails ``unescape_literals`` would
    mean the reader's escaper and its inverse disagree, a far larger defect that the
    coercion would have masked. It is corrected because the second of two identical
    conflations left in place is how the next reader concludes the pattern was intentional.
    """
    texts: Dict[str, List[str]] = {}
    for segment in source.segments:
        if segment.block_id is None:
            continue
        own = _decoded_units(segment.body)
        if own is not None:
            texts[segment.block_id] = own
    return texts


def _refuse_absent_markers(
    source: "_Scan",
    edit: "_Scan",
    surviving: set,
    opaque: set,
    absent: AbsentBlockDisposition,
) -> List[Refusal]:
    """Stage 3 — **ORDER-SENSITIVE**: which blocks did not come back, and how to read it.

    Two orderings are behavior here and neither may be rearranged.

    **Per block**, the narrower reading is tried first: a block whose own text plainly
    came back somewhere in the edited Markdown is a ``marker-dropped`` (the loss is the
    marker alone). Only when it did not is the block ``marker-absent``. Swapping the two
    would report the alarming reading for the recoverable case.

    **Across blocks**, the document's own segment order — so a consumer reading the
    refusal list walks their document top to bottom.

    Under :attr:`AbsentBlockDisposition.DELETE` the stage yields nothing at all: the
    caller has stated the omission was meant, and the absent blocks are planned by the
    per-segment diff instead. An opaque block is skipped under either disposition — it is
    conserved, which is the whole conservation contract.
    """
    refusals: List[Refusal] = []
    returned_units = _all_units(edit)
    for segment in source.segments:
        block_id = segment.block_id
        if block_id is None or block_id in surviving or block_id in opaque:
            continue
        if absent is AbsentBlockDisposition.DELETE:
            continue
        try:
            surviving_text = _decode(segment.body.strip())
        except LarkEscapeError:
            surviving_text = segment.body.strip()
        own = _decoded_units(segment.body)
        if own is not None and _locate(own, returned_units) is not None:
            refusals.append(Refusal.marker_dropped(
                f"block {block_id!r} has no marker in the edited Markdown, but the "
                f"block's own text came back with it, reading: {surviving_text!r}. That "
                f"is a dropped marker, not a deletion and not a rewrite — and the block "
                f"is never re-attached to text by resemblance, because an identifier "
                f"cannot be recovered from what a block happens to say and a wrong "
                f"re-attachment rewrites the wrong block. Nothing was planned. Put the "
                f"block's own marker line back immediately above that text and re-run."
            ))
            continue
        refusals.append(Refusal.marker_absent(
            f"block {block_id!r} has no marker in the edited Markdown, and it is still "
            f"in the document reading: {surviving_text!r}. An absent marker is not a "
            f"deletion — a marker dropped together with its content cannot be told apart "
            f"from a rewrite that dropped the marker, and the two readings differ by "
            f"destroying content. Nothing was planned. Put the marker back together with "
            f"the block's text to keep it, or re-run with the deletion disposition to "
            f"mean the deletion."
        ))
    return refusals


def _diff_all_segments(
    source: "_Scan",
    edit: "_Scan",
    surviving: set,
    opaque: set,
    source_texts: Dict[str, List[str]],
    refusals: List[Refusal],
) -> List[ReconciliationEntry]:
    """Stage 4 — **ORDER-SENSITIVE**: every segment's verdict, in the document's order.

    The walk is over the SOURCE's segments, so the head (the content ahead of the first
    marker) is answered first and the blocks follow in the document's own order — which is
    the order both the entries and any refusals come back in. Unlike the earlier stages
    this one does **not** stop at the first refusal: a segment that refuses contributes no
    entry and the walk continues, so a consumer sees every fault in one pass rather than
    one per re-run. The plan is still refused whole by the caller.

    A block that is not among the survivors reaching this stage means stage 3 let it
    through: either the caller dispositioned the deletion or the block is conserved.
    """
    edited_by_id: Dict[str, _Segment] = {s.block_id: s for s in edit.segments if s.block_id}
    edited_head = next(s for s in edit.segments if s.block_id is None)
    entries: List[ReconciliationEntry] = []
    for segment in source.segments:
        block_id = segment.block_id
        if block_id is None:
            entries.extend(_diff_head(segment, edited_head, refusals))
            continue
        if block_id not in surviving:
            try:
                before = _decode(segment.body.strip())
            except LarkEscapeError as e:
                refusals.append(_undecodable(block_id, e))
                continue
            entries.append(
                ReconciliationEntry.conserved_opaque(block_id, before)
                if block_id in opaque
                else ReconciliationEntry.deleted(block_id, before)
            )
            continue
        entries.extend(
            _diff_segment(
                segment,
                edited_by_id[block_id],
                block_id in opaque,
                refusals,
                source_texts,
            )
        )
    return entries


# --------------------------------------------------------------------------- #
# The entry point.                                                            #
# --------------------------------------------------------------------------- #

def reconcile(
    projection: BlockIdProjection,
    edited_markdown: str,
    *,
    absent: AbsentBlockDisposition = AbsentBlockDisposition.REFUSE,
) -> ReconciliationPlan:
    """Diff ``edited_markdown`` against the ``projection`` it was made from.

    ``projection`` is what :func:`~larkdocio.model.projection.project_block_ids` returned
    for the document — it carries the authoritative emitted identifiers and the conserved
    subset, which is why it is the input rather than a bare Markdown string. Matching
    resolves only against those identifiers.

    ``absent`` says what to do about a block whose marker did not come back. The default
    refuses; passing :attr:`AbsentBlockDisposition.DELETE` is the caller stating that the
    omission was meant. An opaque block is conserved under either.

    Returns a :class:`ReconciliationPlan`, always — a refusal is a plan that refuses, not
    an exception. Makes no network call and issues no request.
    """
    if not isinstance(projection, BlockIdProjection):
        raise TypeError(
            "reconcile() takes the BlockIdProjection the document was projected to "
            "(its emitted identifiers are the only identity source there is), got "
            f"{type(projection).__name__}"
        )
    if not isinstance(edited_markdown, str):
        raise TypeError(
            f"reconcile() takes the edited Markdown as a str, got "
            f"{type(edited_markdown).__name__}"
        )

    source = _scan(projection.markdown, projection.block_ids)
    edit = _scan(edited_markdown, projection.block_ids)

    # Stage 1 — identity. Nothing else can be trusted until every marker is one real
    # block, so an invented or duplicated id stops the reconciliation here.
    refusals: List[Refusal] = _refuse_marker_identity(edit)
    if refusals:
        return ReconciliationPlan(refusals=tuple(refusals))

    # Stage 2 — order. A move is not expressible, and detection is exact.
    surviving = set(edit.order)
    reordered = _refuse_reordered_markers(source, edit, surviving)
    if reordered is not None:
        refusals.append(reordered)
        return ReconciliationPlan(refusals=tuple(refusals))

    opaque = set(projection.opaque_block_ids)

    # Stage 3 — absence, in its two readings. A marker gone TOGETHER WITH its content is
    # `marker-absent`: formally indistinguishable from a heavy rewrite that dropped the
    # marker, and refused as such. A marker gone from content that PLAINLY CAME BACK is
    # the narrower `marker-dropped` — the loss is the marker alone, the recovery is to put
    # it back, and the block is never re-attached to that text by content similarity. An
    # opaque block is never absent in this sense: it is conserved, which is the whole
    # conservation contract.
    refusals.extend(_refuse_absent_markers(source, edit, surviving, opaque, absent))
    if refusals:
        return ReconciliationPlan(refusals=tuple(refusals))

    # Stage 4 — the per-segment diff. Each block's own decoded text is computed once, and
    # the whole map travels into the diff: a marker that came back sitting on **another**
    # projected block's text is a relocation, and naming which block it landed on is the
    # difference between a refusal a consumer can act on and one they cannot.
    source_texts = _source_block_texts(source)
    entries = _diff_all_segments(source, edit, surviving, opaque, source_texts, refusals)

    # Stage 5 — the conservation contract, checked against the plan the earlier stages
    # produced rather than asserted in prose. It is the one refusal that cannot be seen
    # from any single segment: the conserved block and the insert that re-creates it are
    # found in different places, and only the assembled plan holds both.
    _refuse_re_created_conserved_blocks(entries, surviving, source_texts, refusals)

    if refusals:
        return ReconciliationPlan(refusals=tuple(refusals))
    return ReconciliationPlan(entries=tuple(entries))


def _refuse_re_created_conserved_blocks(
    entries: Sequence[ReconciliationEntry],
    surviving: Sequence[str],
    source_texts: Dict[str, List[str]],
    refusals: List[Refusal],
) -> None:
    """A conserved block is **never re-created** — so a plan that conserves a block and
    also plans that same block's content as an insert refuses, naming the block.

    The case is an editor that ate an **opaque** block's marker and kept its content: the
    block is conserved (an opaque block is conserved even when its marker did not come
    back), while its now-unmarked content lands in the preceding marker's segment and is
    planned as an addition. Applying that leaves the document holding the block twice
    while the plan says it was conserved — the module's own contract, falsified by its own
    output.

    **The insert is refused, never silently dropped.** Content beside a conserved block
    may be a real addition, and discarding it would destroy an edit the caller made; a
    provably ambiguous loss refuses rather than picking one reading.

    The check is deliberately scoped to a conserved block whose marker did **not** come
    back. With the marker present the block's identity is not in doubt, so a second copy
    of its content beside it is an ordinary insert the caller asked for — and refusing
    that would be the over-eager failure a refusal set invites.
    """
    inserted = [e for e in entries if e.state is ReconciliationState.INSERTED]
    if not inserted:
        return
    for entry in entries:
        block_id = entry.block_id
        if entry.state is not ReconciliationState.CONSERVED_OPAQUE or block_id is None:
            continue
        if block_id in surviving:
            continue
        own = source_texts.get(block_id, [])
        match = next((e for e in inserted if e.after in own), None)
        if match is None:
            continue
        refusals.append(Refusal.conserved_block_re_created(
            f"block {block_id!r} is conserved — a block of this kind is never edited, "
            f"never deleted and never re-created — but its marker is not in the edited "
            f"Markdown and its own content came back unmarked, reading: {match.after!r}. "
            f"Planning that content as an addition would leave the document holding the "
            f"block twice, once conserved and once created, so nothing was planned. The "
            f"content is not discarded either: text beside a conserved block may be a "
            f"real addition, and dropping it would destroy an edit. Put the block's own "
            f"marker line back immediately above that content and re-run; to keep the "
            f"block and add a second copy of it, restore that marker and leave the extra "
            f"copy under the block's own text."
        ))


def _undecodable(where: str, error: Exception) -> Refusal:
    return Refusal.undecodable_text(
        f"{where}: the Markdown cannot be decoded out of the projection's escaping, so "
        f"it cannot be compared with the block's own text without guessing — {error}. "
        f"The projection escapes literal text; a backslash it never emits means the text "
        f"did not come from it."
    )


def _diff_head(
    source: _Segment, edited: _Segment, refusals: List[Refusal]
) -> List[ReconciliationEntry]:
    """Whatever arrived ahead of the first marker.

    That content carries **no identifier** — the document's own title block is the usual
    case — so it can be kept or added to, but a change to it cannot be attributed to any
    block and refuses.
    """
    try:
        original = [_decode(u) for u in _units(source.body)]
        units = _units(edited.body)
        decoded = [_decode(u) for u in units]
    except LarkEscapeError as e:
        refusals.append(_undecodable("the content before the first marker", e))
        return []

    start = _locate(original, decoded)
    if start is None:
        refusals.append(Refusal.unmarked_content_changed(
            "the content before the first marker came back changed. It carries no "
            "identifier — the document's title block is projected without one — so no "
            "request can be attributed to it and nothing was planned. Restore it, and "
            "make the change through a block that carries a marker."
        ))
        return []
    return [
        ReconciliationEntry.inserted(
            decoded[i], units[i], None, InsertPosition.BEFORE.value
        )
        for i in range(len(units))
        if not start <= i < start + len(original)
    ]


def _diff_segment(
    source: _Segment,
    edited: _Segment,
    is_opaque: bool,
    refusals: List[Refusal],
    source_texts: Dict[str, List[str]],
) -> List[ReconciliationEntry]:
    """One surviving marker's segment: its block, and anything that travels with it."""
    block_id = source.block_id
    try:
        source_units = _units(source.body)
        original = [_decode(u) for u in source_units]
        units = _units(edited.body)
        decoded = [_decode(u) for u in units]
        # The same decode, at SEGMENT granularity — see the no-op below. Computed in
        # this try so undecodable text stays "not comparable" and never reaches a
        # comparison at all.
        source_text = _decode(source.body.strip())
        edited_text = _decode(edited.body.strip())
    except LarkEscapeError as e:
        refusals.append(_undecodable(f"block {block_id!r}", e))
        return []

    before = "\n\n".join(original)
    start = _locate(original, decoded)

    if is_opaque:
        # Conserved whichever way the segment came back. When the block's own content is
        # still identifiable, content that travelled with it is still an insert; when it
        # is not — the editor rewrote what the projection only reshaped — the segment is
        # conserved whole and nothing is planned from it. That same position, computed once
        # above for every branch, is the only thing that can tell those two ways apart, so
        # it is DISCLOSED here rather than discarded: `start is None` is exactly the
        # ambiguous fact CONSERVED_BODY_DIFFERS_MEANING states, and nothing refuses on it.
        entry = ReconciliationEntry.conserved_opaque(
            block_id, before, body_differs=start is None)
        if start is None:
            return [entry]
        return _with_inserts(entry, block_id, units, decoded, start, len(original))

    if start is not None:
        entry = ReconciliationEntry.unchanged(block_id, before)
        return _with_inserts(entry, block_id, units, decoded, start, len(original))

    # ESCAPE-ONLY NORMALIZATION — the segment's whole DECODED text is the block's own
    # decoded text, exactly, so nothing was changed however many Markdown units either
    # side parses into. The unit split runs on the RAW Markdown (it has to: the raw
    # chunks are what gets compiled), and escaping is structural — a paragraph whose
    # second line reads `\- item` is one unit escaped and two unescaped. An editor that
    # merely normalized the projection's escaping therefore used to land in the
    # `segment-ambiguous` refusal below, taking every other edit in the document with
    # it. This is AC10's own comparison rule (decode first) applied at SEGMENT
    # granularity rather than unit granularity; it is exact, so it can only ever reach
    # FEWER requests, never a different one. The COMBINED case — normalized AND edited,
    # so the decoded texts differ — is deliberately not covered: with the texts
    # differing there is no evidence separating "normalized escaping plus edited prose"
    # from "deliberately split one block into two", and refusing there is the
    # two-commit route.
    if source_text == edited_text:
        return [ReconciliationEntry.unchanged(block_id, before)]

    # ORPHANED — the marker came back with nothing under it. An emptied block is a
    # deletion expressed ambiguously, and the two readings differ by destroying content.
    if not units and original:
        refusals.append(Refusal.marker_orphaned(
            f"block {block_id!r}: its marker came back with no content under it, where "
            f"the document has {before!r}. An emptied block is a deletion expressed "
            f"ambiguously — it may mean the block should go, or it may be content lost "
            f"while editing — and the two readings differ by destroying content. Nothing "
            f"was planned. Put the block's text back under its marker to keep it; to "
            f"delete it, remove its marker together with its text and re-run under the "
            f"explicit deletion disposition."
        ))
        return []

    # RELOCATED — the marker's own text is not here, but ANOTHER projected block's text
    # is, exactly. Applying that would rewrite two blocks with each other's content, which
    # is the one corruption that cannot be noticed by reading either block afterwards. The
    # match is exact on purpose: a "best" match would be the guess this refuses to make.
    for other_id, other_units in source_texts.items():
        if other_id == block_id or not other_units:
            continue
        if _locate(other_units, decoded) is not None:
            refusals.append(Refusal.marker_relocated(
                f"block {block_id!r}: its segment came back holding block {other_id!r}'s "
                f"text, and this block's own text is not in it. A marker sitting on "
                f"another block's content is not an edit — applying it would rewrite both "
                f"blocks with each other's text, which is the one corruption that reading "
                f"either block afterwards would not reveal. Nothing was planned. Put each "
                f"block's text back under its own marker; to move text between blocks, "
                f"edit each block's own content in place rather than moving the markers."
            ))
            return []

    if len(units) != len(original):
        refusals.append(Refusal.segment_ambiguous(
            f"block {block_id!r}: its segment came back as {len(units)} piece(s) of "
            f"content and none of them is the block's own text, so there is no way to "
            f"tell which piece is the edited block and which was added beside it. "
            f"Choosing would rewrite the block with content that was never meant for it. "
            f"Nothing was planned. Make the edit and the addition in two separate rounds."
        ))
        return []

    after_markdown = "\n\n".join(units)
    after = "\n\n".join(decoded)
    try:
        before_type = _block_type(source.body.strip())
        after_type = _block_type(after_markdown)
    except RefusedError as e:
        refusals.append(e.refusal)
        return []
    if before_type != after_type:
        refusals.append(
            Refusal.block_type_mutation(
                _type_mutation_detail(block_id, before_type, after_type)
            )
        )
        return []
    # The pre-image travels as MARKDOWN beside the decoded text (LD-574): the compiler has
    # to know what its request would be replacing, and the same join the after side uses is
    # what makes the two comparable at all.
    return [ReconciliationEntry.edited(
        block_id, before, after, after_markdown, "\n\n".join(source_units))]


def _with_inserts(
    entry: ReconciliationEntry,
    block_id: str,
    units: Sequence[str],
    decoded: Sequence[str],
    start: int,
    span: int,
) -> List[ReconciliationEntry]:
    """The block's own entry, with the segment's extra content as anchored inserts.

    The anchor is always this surviving marker — never another inserted block — and the
    side records where the content actually arrived, so an editor that wrote its new
    paragraph above the marked block does not have it silently moved below.
    """
    out: List[ReconciliationEntry] = []
    for i in range(start):
        out.append(ReconciliationEntry.inserted(
            decoded[i], units[i], block_id, InsertPosition.BEFORE.value
        ))
    out.append(entry)
    for i in range(start + span, len(units)):
        out.append(ReconciliationEntry.inserted(
            decoded[i], units[i], block_id, InsertPosition.AFTER.value
        ))
    return out
