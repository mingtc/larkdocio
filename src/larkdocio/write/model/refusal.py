"""larkdocio.write.model.refusal — the typed skip reasons (never guess, always skip).

:class:`Refusal` / :class:`RefusalReason` are the typed reasons the resolver (S2) and
apply engine (S4) return when an anchor cannot be safely applied. The W1 four are defined
here — ``ambiguous-N-candidates`` (carrying the candidate ids/count), ``not-found``,
``write-hostile-target``, ``stale-anchor`` — even though ``stale-anchor`` is only *produced*
by S4 (LD-068); the whole chain shares one vocabulary from S1. The table path (W2 / LD-070)
**reuses** those four where they genuinely fit and adds **one** new reason,
``column-not-found``; the insert/delete path (W3 / LD-074) adds ``cannot-hold-children``
and — since LD-131 — its sibling mirror ``cannot-hold-siblings``; the sub-span path
(W3 / LD-077) adds ``span-not-splittable``; **table creation** (LD-135) adds
``merge-not-expressible`` — the one reason produced at **construction** time (an authored
grid that is not rectangular is the merged-cell shape Markdown cannot express), carried to
the caller by :class:`RefusedError`; and the **Markdown compiler** (LD-136) adds
``not-in-dialect`` — produced at **compile** time when a fragment names a construct the
creatable set has no block for, likewise carried by :class:`RefusedError`. The
**whole-block edit** path adds ``comment-anchors-present`` — produced at **plan** time when
the target block carries inline comment anchors its single-run rebuild cannot honor, with
the sub-span edit named as the recovery. The **comment ops** (LD-202) add three:
``comment-anchor-not-creatable`` and ``comment-surface-unsupported`` at **plan** time (the
two capabilities the API does not have, refused with its own captured rejections rather than
attempted), and ``comment-thread-not-solely-authored`` at **apply** time (an ownership fact
that only the live thread can settle) — while a thread that is simply **not there** reuses
``not-found``. The **table-grow** op (LD-575) adds ``table-grow-unsupported`` at **plan**
time — the table resolved and the grow asked for is not the one that ships — while a
**non-table** anchor reuses ``write-hostile-target`` and a missing or over-matching one reuses
``not-found`` / ``ambiguous-N-candidates``.

**The apply-time DISPOSITION family is the newest addition, and it is a different KIND of
reason.** Every reason above is a claim about the document or the request — found, not found,
ambiguous, hostile, stale, inexpressible — decided before a call or instead of one. The eight
below (``api-error``, ``permission-denied``, ``rate-limited``, ``transport-failure``,
``pagination-unterminated``, ``unexpected-error``, ``unverified-write``, ``not-attempted``) say
what happened to a call that was actually made, and they are produced in exactly one place:
:mod:`larkdocio.write.disposition`, the boundary the apply engine dispatches each entry inside.
Seven of the eight are spelled with the **same wire values** the sheets and Base engines
publish, deliberately — one condition should not have two names across two engines — while
``pagination-unterminated`` is this surface's own, for the one failure the others do not have.

**``detail`` is MANDATORY on every refusal (LD-131 / AC2).** A refusal exists to tell a
consumer *what* failed and *why*, recoverably — an agent that reads ``{"reason":
"not-found"}`` with no detail has **nothing** to recover from, and that
costs the consumer their first write. So ``detail`` is a **required constructor argument**,
non-empty, on
:class:`Refusal` itself and on **every** factory below: a detail-less refusal is
structurally unconstructable (``TypeError`` when omitted, ``ValueError`` when blank), and
:meth:`Refusal.from_dict` refuses a detail-less wire record rather than revive a lying
refusal. Each factory's caller supplies the **identifier the refusal is about** (the quote,
the span, the row-key, the resolved ``block_id``), so the detail is actionable rather than
decorative.

**Table refusal mapping (LD-070, AC3)** — the row/column locator cases
the table resolver (S2) will return, and which reason each maps to::

    table-not-found   -> RefusalReason.NOT_FOUND         (reuse — Refusal.table_not_found)
    ambiguous-table   -> RefusalReason.AMBIGUOUS + ids   (reuse — Refusal.ambiguous_table)
    row-not-found     -> RefusalReason.NOT_FOUND         (reuse — Refusal.row_not_found)
    ambiguous-row     -> RefusalReason.AMBIGUOUS + ids   (reuse — Refusal.ambiguous_row)
    covered/merged    -> RefusalReason.WRITE_HOSTILE     (reuse — Refusal.write_hostile)
    column-not-found  -> RefusalReason.COLUMN_NOT_FOUND  (NEW   — Refusal.column_not_found)

*Why ``column-not-found`` is new and the rest are reused:* a missing **table** or **row**
is genuinely a *not-found* target (the locator matched no block), and an over-matching
table/row is genuinely *ambiguous* — reusing ``NOT_FOUND`` / ``AMBIGUOUS`` keeps one
vocabulary. But **column-not-found is different in kind**: the table and row *were*
resolved, yet the requested column-target (header quote or index) has no such column.
Folding it into ``NOT_FOUND`` would conflate "I couldn't find your row" with "I found the
row but there's no such column" — two failures a consumer fixes differently (correct the
row-key vs. correct the column designation). It is not ambiguity, not write-hostility, not
staleness, so none of the W1 four fit; it earns its own typed reason. ``table-not-found``
and ``row-not-found`` deliberately **share** ``NOT_FOUND`` (distinct call-sites, one reused
reason) per the maintainer mapping.

**Insert/delete refusal mapping (LD-074, AC4, extended by LD-131)** — the
W3 insert/delete resolver (S2) cases, and which reason each maps to::

    reference-not-found     -> RefusalReason.NOT_FOUND            (reuse — Refusal.reference_not_found)
    ambiguous-reference     -> RefusalReason.AMBIGUOUS + ids      (reuse — Refusal.ambiguous_reference)
    reference-write-hostile -> RefusalReason.WRITE_HOSTILE        (reuse — Refusal.reference_write_hostile)
    target-not-found        -> RefusalReason.NOT_FOUND            (reuse — Refusal.target_not_found)
    ambiguous-target        -> RefusalReason.AMBIGUOUS + ids      (reuse — Refusal.ambiguous_target)
    target-write-hostile    -> RefusalReason.WRITE_HOSTILE        (reuse — Refusal.target_write_hostile)
    append-into-leaf        -> RefusalReason.CANNOT_HOLD_CHILDREN (NEW   — Refusal.cannot_hold_children)
    before/after-on-root    -> RefusalReason.CANNOT_HOLD_SIBLINGS (NEW LD-131 — Refusal.cannot_hold_siblings)

*Why ``cannot-hold-children`` is new and the rest are reused:* a missing insert
**reference** or delete **target** is genuinely *not-found*; an over-matching one is
genuinely *ambiguous*; a synced/image/board/embed reference-or-target is genuinely
*write-hostile* — so all three reuse the W1 reasons and keep one vocabulary. But
``cannot-hold-children`` is **different in kind**: the reference *was* resolved (found,
unique, write-friendly), yet an ``append-into`` cannot proceed because the block is a leaf
that cannot parent children. Folding it into ``NOT_FOUND`` would conflate "I couldn't find
your reference" with "I found it but it can't hold children" — two failures a consumer
fixes differently (correct the anchor vs. pick ``before``/``after`` or a container
reference). It is not ambiguity, hostility, staleness, or a column problem, so none of the
existing reasons fit; it earns its own — exactly as ``column-not-found`` did for the table
path.

*Why ``cannot-hold-siblings`` joined it (LD-131 — the F5 bug):* the **sibling** mirror had
no reason of its own, so a ``before``/``after`` insert whose reference resolved to the
document **root** (the page node — it has no parent, so there is no sibling position beside
it) collapsed into ``not-found`` — **a lie**: the anchor *was* found, and the identical
anchor with ``append-into`` resolves to a real ``block_id``. ``not-found`` sends the
consumer hunting for a better quote (the wrong repair) when the fix is to change the
*position*. The taxonomy already distinguished the children case; the sibling case is the
same kind of failure (resolved-but-position-incapable) and earns the same treatment.

Dumb typed data; depends only on the standard library.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Sequence, Tuple

from larkdocio.errors import LarkConfigError


# --------------------------------------------------------------------------- #
# Refusal reasons — the typed skip reasons (never guess, always skip)            #
# --------------------------------------------------------------------------- #

class RefusalReason(Enum):
    """Why an edit request could not be safely applied.

    Distinct, inspectable values shared by the resolver and apply engine.
    The ``value`` string is the stable serialized form (also what a consumer sees in
    the apply-log).
    """

    AMBIGUOUS = "ambiguous-N-candidates"
    NOT_FOUND = "not-found"
    WRITE_HOSTILE = "write-hostile-target"
    STALE_ANCHOR = "stale-anchor"
    #: W2 / LD-070 — the table row was resolved but its column-target (header quote or
    #: index) has no matching column. New because the W1 four don't fit: it is neither
    #: a not-found *target* (the row WAS found) nor ambiguity/hostility/staleness. See
    #: the module docstring's "Table refusal mapping".
    COLUMN_NOT_FOUND = "column-not-found"
    #: W3 / LD-074 — an ``append-into`` insert whose reference block was resolved (found,
    #: unique, write-friendly) but **cannot parent children** (a leaf paragraph). New
    #: because the W1/W2 set doesn't fit: the reference WAS found (not not-found), is a
    #: friendly paragraph (not write-hostile), is unique (not ambiguous), unchanged (not
    #: stale), and it is not a column problem. See the module docstring's "Insert/delete
    #: refusal mapping".
    CANNOT_HOLD_CHILDREN = "cannot-hold-children"
    #: LD-131 (the F5 bug) — a ``before``/``after`` insert whose reference block was
    #: resolved but **cannot hold siblings**: it has no parent in the document tree (it IS
    #: the root / page node), so no sibling position exists beside it. The exact mirror of
    #: :data:`CANNOT_HOLD_CHILDREN`, and new for the same reason — the reference WAS found
    #: (folding it into ``NOT_FOUND`` told the consumer to fix the *quote* when the fix is
    #: the *position*).
    CANNOT_HOLD_SIBLINGS = "cannot-hold-siblings"
    #: W3 / LD-077 — a **sub-span** edit whose span does not map to **exactly one
    #: uniformly-styled contiguous run region**: it occurs >1 time in the block (multiple
    #: candidate regions), crosses runs of **differing** style (the replacement style would
    #: be a guess — the spike's "silent killer"), or overlaps a **non-text** inline
    #: (mention / equation, which cannot be split). New because none of the others fit: the
    #: block WAS found (not not-found — the span *text* is present), is a friendly paragraph
    #: (not write-hostile), and this is neither a column problem nor an append-into leaf. It
    #: is the exactly-one-or-refuse boundary for sub-span, and the tool **never guesses** a
    #: replacement style. See :class:`SubSpanEditRequest`.
    SPAN_NOT_SPLITTABLE = "span-not-splittable"
    #: LD-135 — an authored **table** cannot be expressed as a plain
    #: R×C grid: its rows differ in width, which is the shape a **merged** (colspan /
    #: rowspan) table produces. Markdown has no span syntax, so a merge is **documented
    #: lossiness** and an authoring request implying one is refused — never approximated
    #: by padding or truncating the grid. New because none of the others fit: nothing was
    #: resolved at all (not not-found / ambiguous / write-hostile / stale), no column was
    #: looked up, and no span was split — the *authored content itself* is inexpressible.
    #: Produced at **construction** time (see
    #: :meth:`~larkdocio.write.model.requests.NewBlock.table`), carried by
    #: :class:`RefusedError`.
    MERGE_NOT_EXPRESSIBLE = "merge-not-expressible"
    #: LD-574 — a reconciliation entry the reconciler accepted as a **change** compiles to a
    #: request set that would write bytes **identical to what is already live**, so applying
    #: it would report success for a change that never happened. Two shapes, one reason
    #: because the consumer-visible fact is the same: an edit whose only difference is a
    #: property a whole-block replacement cannot carry (a code block's fence language, a
    #: nesting change, a Markdown respelling of the same block), and added content that
    #: composes to **no block at all** (a link-reference or footnote definition). New because
    #: none of the others fit: nothing was resolved (not not-found / ambiguous /
    #: write-hostile / stale), no column was looked up, no span was split, it is not a merge,
    #: and the authored source is perfectly **in** the dialect — it simply reaches a property
    #: this operation does not write. Decided at **compile** time by
    #: :func:`~larkdocio.write.compiler.compile_reconciliation`, where the request is built,
    #: and carried by :class:`RefusedError`; nothing is compiled and no call is made. The
    #: defect it closes was measured in round 5 (a checkbox flip reported ``applied`` while
    #: the bit did not move) and the ``done`` bit itself is now writable — this reason covers
    #: what is left.
    CHANGE_NOT_EXPRESSIBLE = "change-not-expressible"
    #: LD-575 — a **table-grow** request asked for a grow this operation does not perform. Two
    #: triggers, one reason, because the consumer-visible fact is the same — *the table was
    #: found, it is a table, and this is not the grow that ships* — and the ``detail`` says
    #: which and what to do instead:
    #:
    #: * a ``row_index`` other than :data:`~larkdocio.write.model.requests.APPEND_ROW_INDEX`.
    #:   **Stated as UNMEASURED, never as impossible**: mid-table insertion has never been
    #:   called from this tree and no measurement in it covers one, so the refusal names the
    #:   append spelling as the remedy rather than claiming Lark refuses the other;
    #: * a grow that would take the grid past
    #:   :data:`~larkdocio.write.model.MAX_TABLE_CELLS` — larkdocio's own authoring cap, so a
    #:   table this library refuses to AUTHOR at a size is one it refuses to GROW to. That is a
    #:   shipped cap and the detail says so, which is a different sentence from the unmeasured
    #:   one above and must stay one.
    #:
    #: New because none of the others fit: the anchor WAS found (not not-found), it is unique
    #: (not ambiguous), it is a perfectly writable table (not write-hostile — the *non*-table
    #: case reuses that reason), it has not drifted (not stale), no column was looked up and no
    #: span was split. Folding it into ``NOT_FOUND`` would send a caller hunting for a better
    #: anchor when the anchor is right and the *request* is outside the operation. Decided at
    #: **plan** time, where :func:`~larkdocio.write.preview.dry_run` is structurally incapable
    #: of a network call — so asking for the unshipped grow costs nothing and is answered
    #: honestly, instead of being attempted against a live table.
    TABLE_GROW_UNSUPPORTED = "table-grow-unsupported"
    #: LD-136 — a **Markdown construct** in a composed fragment is
    #: outside the dialect the creatable set can express: an image, a raw-HTML block, an
    #: inline style (bold / italic / strikethrough / inline code — created runs are
    #: unstyled), a thematic break, a footnote, a block child inside a list item or a
    #: blockquote, an unknown code-fence language, or a nesting depth past the documented
    #: cap. New because none of the others fit: nothing was resolved (not not-found /
    #: ambiguous / write-hostile / stale), no column was looked up, no span was split, and
    #: it is not a merge — the *authored source* names a construct that has no creatable
    #: block. Produced by :func:`~larkdocio.write.compose.compose` at **compile** time and
    #: carried to the caller by :class:`RefusedError`, so an out-of-dialect construct is
    #: **refused with the construct and its line named** — never silently dropped and
    #: never approximated (the strict authoring doctrine).
    NOT_IN_DIALECT = "not-in-dialect"
    #: LD-139 (D9) — the **whole document** changed under the plan. The
    #: plan cached the document's ``revision_id``; the apply engine re-read it immediately
    #: before the batch and it differs (or could not be established), so the **ENTIRE batch**
    #: is refused with **ZERO writes issued**. New because it is the only refusal that is a
    #: property of the *document* rather than of one target: every other reason (including
    #: :data:`STALE_ANCHOR`) is decided per entry, and the rest of the batch still applies
    #: around it. Folding document drift into ``STALE_ANCHOR`` would be a lie in both
    #: directions — the anchored blocks may be pristine (drift *around* an anchor is exactly
    #: the case ``STALE_ANCHOR`` cannot see), and the outcome is all-or-nothing rather than a
    #: per-entry skip. Produced by :func:`larkdocio.write.apply.apply`; see
    #: :mod:`larkdocio.write.revision` for the contract and the never-silent marker.
    STALE_DOCUMENT = "stale-document"
    #: The target block of a **whole-block** (element-level) text edit carries **inline
    #: comment anchors** — a reviewer's comment is anchored to specific words inside it.
    #: That path collapses the block to a single run, so per-passage anchors have nowhere to
    #: attach: the edit is refused at plan time with the **sub-span** edit named as the
    #: recovery (that path splits the runs and re-emits each run's anchors). New because
    #: none of the others fit: the block WAS found (not not-found), is unique (not
    #: ambiguous), is an ordinary narrative paragraph (not write-hostile), is unchanged (not
    #: stale), and no column or span is involved. Folding it into ``WRITE_HOSTILE`` would
    #: tell a consumer the block is not text-patchable when it is — by the other path, on
    #: the very same anchor. The two rejected alternatives are why this is a refusal at all:
    #: carrying the leading run's ids onto the collapsed run silently drops every other
    #: run's, and unioning them all onto it relocates each anchor over the whole paragraph
    #: — a comment that moves to the wrong text is a lie about what a reviewer objected to,
    #: which is worse than a refusal that names the path that works. There is deliberately
    #: **no** flag, opt-in or force escape past it.
    COMMENT_ANCHORS_PRESENT = "comment-anchors-present"
    #: LD-202 — a comment-create request asked for the comment to be **anchored** to a
    #: passage (a block id, a quote, or ``is_whole:false``). New because it is the only
    #: refusal about a capability that **does not exist at all**: every other reason says
    #: *this target* cannot be written, while this one says *no target of this shape is
    #: reachable through the API*. Folding it into ``NOT_FOUND`` would send the consumer
    #: hunting for a better block id, and folding it into ``WRITE_HOSTILE`` would say the
    #: passage is unwritable when the passage is irrelevant — the route is absent.
    #:
    #: **It exists because the API's answer is a lie, not an error.** The v1 create route
    #: accepts ``anchor`` / ``quote`` / ``is_whole:false``, answers ``code 0``, and
    #: **silently creates a plain whole-document comment**; a bogus block id and a quote
    #: absent from the document are likewise not errors. So a pass-through would report an
    #: anchored comment that was never created — which is why this must be a refusal and
    #: not a best-effort. See :mod:`larkdocio.write.comments` for the captured evidence the
    #: ``detail`` quotes.
    COMMENT_ANCHOR_NOT_CREATABLE = "comment-anchor-not-creatable"
    #: LD-202 — a comment-create request named a **file type Lark's own enum rejects**.
    #: Comment creation exists for ``doc`` and ``docx`` and for nothing else: a spreadsheet
    #: is refused at the enum with ``99992402`` and a ``field_violations`` entry printing
    #: ``options: [doc,docx]`` verbatim — at **every** granularity, whole-file attempt
    #: included. New because none of the others fit: nothing was resolved, no target was
    #: looked up, and the request is not hostile or stale — the *surface* has no such
    #: operation. Distinct from :data:`COMMENT_ANCHOR_NOT_CREATABLE` on purpose: that one is
    #: "no comment can be anchored anywhere", this one is "no comment can be created on
    #: this kind of file", and a consumer fixes them differently (drop the anchor vs. use
    #: the read surface, which **does** accept a spreadsheet).
    COMMENT_SURFACE_UNSUPPORTED = "comment-surface-unsupported"
    #: LD-202 — a comment-removal was asked for on a thread the application did not author
    #: **or is not alone in**. New because it is an *ownership* refusal, and none of the
    #: others carries that meaning: the thread was found (not not-found), it is a perfectly
    #: ordinary comment (not hostile), it has not drifted (not stale). The API enforces the
    #: same rule — a reply the caller did not write is refused ``1069303 "forbidden"``,
    #: HTTP 403 — so this refusal exists to make the boundary visible **before** any reply
    #: is deleted: a thread carrying somebody else's reply cannot be removed at all, and
    #: deleting the part that *is* removable would leave a half-deleted thread that
    #: misrepresents the conversation and cannot be undone.
    COMMENT_THREAD_NOT_SOLELY_AUTHORED = "comment-thread-not-solely-authored"

    # -- reconciliation (LD-233) -------------------------------------------------- #
    # The reconciler diffs an EDITED PROJECTION against the projection that produced it,
    # and every one of these is decided **pre-I/O**, at plan time, with nothing written.
    # They are new rather than reused because each names a fact about the MARKED TEXT
    # coming back in, not about an anchor resolving in a document: no anchor was looked
    # up, nothing was found or over-matched, no target is hostile and nothing is stale.
    # This is the subset LD-233's own AC earn; the rest of LD-197's loss taxonomy —
    # `dropped` vs `content-absent`, `relocated`, `mangled`, `orphaned` — is minted by the
    # reconciliation refusal-set story, which adopts that table whole.
    # THAT STORY HAS LANDED (LD-235): the four below complete the taxonomy, one typed
    # reason per row, and **no reason above changed its name or its value** —
    # `marker-absent` keeps meaning what it always meant (the marker AND the content both
    # gone, which is formally indistinguishable from a heavy rewrite that dropped the
    # marker), and `marker-dropped` is the strictly narrower case it could not tell apart
    # before: the block's own text plainly came back, so the loss is the marker alone.

    #: An edited projection carries a marker whose id the projection **never emitted**.
    #: **This is the anti-forgery rule** (D11), not an "unknown id" lookup: the emitted id
    #: set is the only identity source there is, so an id outside it did not come from the
    #: document — it was invented, whether by an editor hallucinating one or by a
    #: consumer's own prose being marker-shaped. Never matched by content instead.
    MARKER_INVENTED = "marker-invented"
    #: The same marker id appears more than once in the edited projection. Refused
    #: pre-I/O naming the id: picking one occurrence would attribute an edit to a block on
    #: the strength of a coin toss.
    MARKER_DUPLICATED = "marker-duplicated"
    #: A block the projection emitted has no marker in the edited projection. **Absence
    #: is not deletion** (D10): a marker gone together with its content is formally
    #: indistinguishable from a heavy rewrite that dropped the marker, and the two
    #: readings differ by destroying content. Deletion is available only under the
    #: caller's explicit disposition. An **opaque** block never earns this refusal — it is
    #: conserved instead, which is the conservation contract.
    MARKER_ABSENT = "marker-absent"
    #: A block's marker is gone but **the block's own text plainly came back** — so this
    #: is a dropped marker, not a deletion and not a rewrite. Refused naming the block and
    #: quoting the text that survived: the block is **never** re-attached to that text by
    #: content similarity, because an identifier is not recoverable from what a block
    #: happens to say, and a wrong re-attachment rewrites the wrong block.
    MARKER_DROPPED = "marker-dropped"
    #: A surviving marker came back sitting on a **different** projected block's text.
    #: Applying it would rewrite two blocks with each other's content — the one corruption
    #: that cannot be noticed by reading either block afterwards — so it refuses naming
    #: both blocks rather than treating either side as an edit.
    MARKER_RELOCATED = "marker-relocated"
    #: A **marker-shaped** line that is not the canonical form, byte for byte. Refused
    #: quoting the mangled bytes and the canonical form, and deliberately **not
    #: normalized**: a marker-shaped line that is not byte-exact may be content that
    #: merely looks like one, and repairing it would guess which.
    MARKER_MANGLED = "marker-mangled"
    #: A surviving marker came back with **no content under it at all**. An emptied block
    #: is a deletion expressed ambiguously — it may mean "delete this" or it may be
    #: content lost in editing — so it refuses rather than picking one reading.
    MARKER_ORPHANED = "marker-orphaned"
    #: The surviving markers appear in a different order than the document's. A move is
    #: not expressible in the shipped request families, and faking it as delete+insert
    #: destroys the block's identity and everything anchored to it (D12).
    MARKER_ORDER_CHANGED = "marker-order-changed"
    #: A marked block's edited form is a **different block type** (a paragraph edited into
    #: a heading). Reconciliation never promotes a block: the working route is delete +
    #: insert as two commits, which the ``detail`` names.
    BLOCK_TYPE_MUTATION = "block-type-mutation"
    #: A marker's segment holds several pieces of content and **none of them is the marked
    #: block** — so an edit-then-insert cannot be told apart from an insert-then-edit, and
    #: choosing would rewrite the wrong block with the other's text.
    SEGMENT_AMBIGUOUS = "segment-ambiguous"
    #: Content the projection emitted **without a marker** (the document's own title
    #: block, which carries no identifier) came back changed. It carries no identity, so
    #: no request can be attributed to it.
    UNMARKED_CONTENT_CHANGED = "unmarked-content-changed"
    #: A piece of the edited projection cannot be decoded out of the projection's escaping
    #: (D7.1). The decode is the exact inverse of the reader's escape policy and refuses
    #: rather than guess; comparison happens in the decoded domain, so an undecodable
    #: piece cannot be compared at all.
    UNDECODABLE_TEXT = "undecodable-text"
    #: A block the plan **conserves** — an opaque block, which is never edited, never
    #: deleted and **never re-created** — would ALSO have been planned as new content,
    #: because its marker is gone from the edited Markdown while its own content came back
    #: unmarked. Applying that would leave the document holding the block twice while the
    #: plan claimed it was conserved, so it refuses instead. Dropping the insert silently
    #: is **not** the alternative: content that legitimately appears beside a conserved
    #: block is real content, and discarding it would destroy an edit the caller made.
    CONSERVED_BLOCK_RE_CREATED = "conserved-block-re-created"

    # -- the APPLY-TIME disposition boundary ------------------------------------ #
    # Every reason below is produced by :mod:`larkdocio.write.disposition` when an
    # exception is raised *while applying* an entry — never at plan time, and never by a
    # resolver. They are the docx spelling of a vocabulary the sheets and Base engines
    # already publish, and the WIRE VALUES ARE DELIBERATELY THE SAME STRINGS
    # (``api-error``, ``permission-denied``, ``rate-limited``, ``transport-failure``,
    # ``unexpected-error``, ``unverified-write``, ``not-attempted``): a consumer holding a
    # log from two engines must not have to learn two names for one condition. What is NOT
    # shared is the classification — on docx every one of them HALTS the batch, which is
    # this surface's own doctrine and is stated on ``classify_apply_exception``.
    #
    # They are new rather than reused because none of the reasons above can carry an
    # apply-time failure honestly: every one of those says something was *found*, *not
    # found*, *ambiguous*, *hostile*, *stale* or *inexpressible* — claims about the
    # document and the request, decided before or instead of a call. These say what
    # happened to a call that was actually made.

    #: Lark answered this entry's write with a non-zero ``code``. Nothing landed for it.
    API_ERROR = "api-error"
    #: Lark refused because the app lacks a required SCOPE. Nothing landed. The repair is a
    #: console grant, and the detail relays Lark's own denial — this library never requests,
    #: widens or escalates a scope. Distinct from :data:`API_ERROR` (which it is a coded
    #: subclass of on the wire) because a consumer fixes the two in different places.
    PERMISSION_DENIED = "permission-denied"
    #: Lark's rate limit survived the write transport's own backoff-and-retry. Nothing
    #: landed, and the batch stops rather than hammering a throttled endpoint.
    RATE_LIMITED = "rate-limited"
    #: The call failed BELOW Lark — no ``code`` came back at all — so whether this entry's
    #: write landed is INDETERMINATE. Never reported as a refusal: "nothing landed" would be
    #: a guess, and the honest answer is that the engine does not know.
    TRANSPORT_FAILURE = "transport-failure"
    #: A cursor-paged read this entry depends on could not be run to exhaustion (a repeated
    #: cursor, or fresh cursors past the walk's page cap), so what the entry would have
    #: written cannot be derived from a list that may be short. Its own reason rather than
    #: :data:`UNEXPECTED_ERROR` because it is not a library bug and there is no traceback
    #: worth reporting: it is a server answering in a shape the walk refuses to guess past.
    PAGINATION_UNTERMINATED = "pagination-unterminated"
    #: An un-modelled exception escaped this entry's apply step. It becomes a typed entry
    #: rather than a traceback, but its blast radius is unknown, so whether the write landed
    #: is INDETERMINATE and the traceback is worth reporting.
    UNEXPECTED_ERROR = "unexpected-error"
    #: This entry's write RETURNED — the change IS in the document — and a step AFTER it
    #: failed. Recorded as applied with an incomplete verification record, never as a
    #: refusal: a log that called a landed write "nothing landed" would be a log that lies.
    UNVERIFIED_WRITE = "unverified-write"
    #: The batch halted at an earlier entry, so this one was never attempted. It is a
    #: logged outcome rather than an absent one, because "no entry" and "an entry that was
    #: never run" are the two readings a consumer of a half-applied batch cannot afford to
    #: confuse.
    NOT_ATTEMPTED = "not-attempted"


@dataclass(frozen=True)
class Refusal:
    """A typed refusal: a :class:`RefusalReason`, a **mandatory** actionable ``detail``,
    plus — for ``AMBIGUOUS`` — the candidate ids the anchor matched (the tool **never
    auto-picks** among duplicates).

    ``detail`` is a **required, non-empty** string naming *what* failed and *why*:
    the identifier the refusal is about (the anchor quote, the span, the
    row-key, the resolved ``block_id``) plus the recovery. It cannot be omitted
    (``TypeError``) or blank (``ValueError``) — through the constructor *or* any factory —
    so no code path can emit the detail-less ``{"reason": "not-found"}`` that an earlier
    release could produce.

    Build one via the classmethod matching the reason — :meth:`ambiguous`,
    :meth:`not_found`, :meth:`write_hostile`, :meth:`stale_anchor`, … — so the candidate
    detail is only ever attached to the ambiguous case.
    """

    reason: RefusalReason
    detail: str
    candidate_ids: Tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.detail, str):
            raise TypeError(
                f"Refusal.detail must be a str naming what failed and why, got "
                f"{type(self.detail).__name__} — every docx refusal carries a detail"
            )
        if not self.detail.strip():
            raise ValueError(
                "Refusal.detail must be a NON-EMPTY explanation (a detail-less "
                "refusal gives a consumer nothing to recover from)"
            )
        object.__setattr__(self, "candidate_ids", tuple(self.candidate_ids))

    @property
    def candidate_count(self) -> int:
        """How many blocks the anchor matched (>1 ⇒ ambiguous; 0 otherwise)."""
        return len(self.candidate_ids)

    @classmethod
    def ambiguous(cls, candidate_ids: Sequence[str], detail: str) -> "Refusal":
        """The anchor resolved to more than one block — carry the candidate ids."""
        return cls(RefusalReason.AMBIGUOUS, detail, tuple(candidate_ids))

    @classmethod
    def not_found(cls, detail: str) -> "Refusal":
        """The anchor's quote + breadcrumb matched no block."""
        return cls(RefusalReason.NOT_FOUND, detail)

    @classmethod
    def write_hostile(cls, detail: str) -> "Refusal":
        """The target is write-hostile content (not a plain narrative paragraph)."""
        return cls(RefusalReason.WRITE_HOSTILE, detail)

    @classmethod
    def stale_anchor(cls, detail: str) -> "Refusal":
        """The block changed under the anchor since it was captured (produced by the
        apply engine)."""
        return cls(RefusalReason.STALE_ANCHOR, detail)

    # -- table-locator cases (W2 / LD-070) -------------------------------------- #
    # The table resolver (S2) returns these. Missing/ambiguous table+row REUSE the
    # W1 reasons (one vocabulary); only column-not-found is a new reason. See the
    # module docstring's "Table refusal mapping" for the full rationale.

    @classmethod
    def table_not_found(cls, detail: str) -> "Refusal":
        """No table matched the locator's row-key + breadcrumb (reuses NOT_FOUND)."""
        return cls.not_found(detail)

    @classmethod
    def ambiguous_table(cls, candidate_ids: Sequence[str], detail: str) -> "Refusal":
        """The row-key matched rows in >1 table and the breadcrumb did not narrow to
        one — carry the candidate table ids (reuses AMBIGUOUS; never auto-picks)."""
        return cls.ambiguous(candidate_ids, detail)

    @classmethod
    def row_not_found(cls, detail: str) -> "Refusal":
        """No row in the resolved table has a key cell matching the row-key
        (reuses NOT_FOUND)."""
        return cls.not_found(detail)

    @classmethod
    def ambiguous_row(cls, candidate_ids: Sequence[str], detail: str) -> "Refusal":
        """The row-key matched >1 row in the resolved table — carry the candidate row
        (cell) ids (reuses AMBIGUOUS; never auto-picks)."""
        return cls.ambiguous(candidate_ids, detail)

    @classmethod
    def column_not_found(cls, detail: str) -> "Refusal":
        """The row resolved, but the column-target (header quote or index) matches no
        column in the table — the one table case the four narrative reasons don't fit."""
        return cls(RefusalReason.COLUMN_NOT_FOUND, detail)

    # -- insert/delete cases (W3 / LD-074 + LD-131) ------------------------------ #
    # The insert/delete resolver (S2) returns these. A not-found / ambiguous /
    # write-hostile reference-or-target REUSES the W1 reasons (one vocabulary); the two
    # position-capability cases — cannot-hold-children (an append-into leaf) and
    # cannot-hold-siblings (a before/after on the root) — are their own reasons. See the
    # module docstring's "Insert/delete refusal mapping" for the full rationale.

    @classmethod
    def reference_not_found(cls, detail: str) -> "Refusal":
        """An InsertRequest's reference anchor matched no block (reuses NOT_FOUND)."""
        return cls.not_found(detail)

    @classmethod
    def ambiguous_reference(cls, candidate_ids: Sequence[str], detail: str) -> "Refusal":
        """The reference anchor matched >1 block and the breadcrumb did not narrow to
        one — carry the candidate ids (reuses AMBIGUOUS; never auto-picks)."""
        return cls.ambiguous(candidate_ids, detail)

    @classmethod
    def reference_write_hostile(cls, detail: str) -> "Refusal":
        """The reference resolves to write-hostile content (synced/image/board/embed) —
        you cannot anchor an insertion to it (reuses WRITE_HOSTILE)."""
        return cls.write_hostile(detail)

    @classmethod
    def target_not_found(cls, detail: str) -> "Refusal":
        """A DeleteRequest's target anchor matched no block (reuses NOT_FOUND)."""
        return cls.not_found(detail)

    @classmethod
    def ambiguous_target(cls, candidate_ids: Sequence[str], detail: str) -> "Refusal":
        """The delete target anchor matched >1 block — carry the candidate ids
        (reuses AMBIGUOUS; never auto-picks)."""
        return cls.ambiguous(candidate_ids, detail)

    @classmethod
    def target_write_hostile(cls, detail: str) -> "Refusal":
        """The delete target resolves to write-hostile content (a synced block) — refuse
        rather than delete it (reuses WRITE_HOSTILE)."""
        return cls.write_hostile(detail)

    @classmethod
    def cannot_hold_children(cls, detail: str) -> "Refusal":
        """An ``append-into`` reference block cannot parent children (a leaf paragraph) —
        the ``detail`` names the resolved block and the working alternative."""
        return cls(RefusalReason.CANNOT_HOLD_CHILDREN, detail)

    @classmethod
    def cannot_hold_siblings(cls, detail: str) -> "Refusal":
        """A ``before``/``after`` reference block cannot hold siblings — it has no parent
        in the document tree (it IS the root / page node), so there is no sibling position
        beside it. The mirror of :meth:`cannot_hold_children`; the ``detail``
        names the **resolved** block (the anchor *was* found) and points at
        ``append-into`` / a child anchor as the repair."""
        return cls(RefusalReason.CANNOT_HOLD_SIBLINGS, detail)

    # -- sub-span case (W3 / LD-077) -------------------------------------------- #

    @classmethod
    def span_not_splittable(cls, detail: str) -> "Refusal":
        """A sub-span edit's span does not map to exactly one uniformly-styled contiguous
        run region (occurs >1 time, crosses differing run styles, or overlaps a non-text
        inline) — refuse rather than guess a replacement style (the absolute
        exactly-one-or-refuse invariant)."""
        return cls(RefusalReason.SPAN_NOT_SPLITTABLE, detail)

    # -- inline review anchors on a whole-block edit ----------------------------- #

    @classmethod
    def comment_anchors_present(cls, detail: str) -> "Refusal":
        """A whole-block text edit's target carries **inline comment anchors**, which its
        single-run rebuild cannot honor. The ``detail`` names the resolved block, the
        anchors in the way, why this path cannot keep them, and the **sub-span** edit that
        can — the anchor *was* found and the block *is* patchable, so the repair is the
        granularity, not the anchor."""
        return cls(RefusalReason.COMMENT_ANCHORS_PRESENT, detail)

    # -- comment ops (LD-202) ---------------------------------------------------- #
    # A missing / already-removed comment thread REUSES ``NOT_FOUND`` (one vocabulary — a
    # thread that is not there is genuinely a not-found target, exactly as a missing table
    # or row is); the three cases that are different in kind get their own reasons. See the
    # ``RefusalReason`` members for the per-reason rationale.

    @classmethod
    def comment_anchor_not_creatable(cls, detail: str) -> "Refusal":
        """A comment-create asked to be **anchored** to a passage, and no such creation
        exists. The ``detail`` names which anchoring field was supplied, quotes the captured
        evidence that the API accepts it and silently drops it, and names the two things that
        DO work (a whole-document comment, or reading the anchors that already exist)."""
        return cls(RefusalReason.COMMENT_ANCHOR_NOT_CREATABLE, detail)

    @classmethod
    def comment_surface_unsupported(cls, detail: str) -> "Refusal":
        """A comment-create named a file type outside Lark's ``[doc,docx]`` enum. The
        ``detail`` carries Lark's own rejection body and points at the comment **read**,
        which a spreadsheet does accept."""
        return cls(RefusalReason.COMMENT_SURFACE_UNSUPPORTED, detail)

    @classmethod
    def comment_thread_not_solely_authored(cls, detail: str) -> "Refusal":
        """A comment-removal targeted a thread the application did not author or is not
        alone in. The ``detail`` names the foreign author id(s) and states that **nothing
        was deleted** — the refusal is whole-thread by construction."""
        return cls(RefusalReason.COMMENT_THREAD_NOT_SOLELY_AUTHORED, detail)

    @classmethod
    def comment_thread_not_found(cls, detail: str) -> "Refusal":
        """The comment thread a removal named is not there — already removed, never
        existed, or belongs to another file (reuses ``NOT_FOUND``)."""
        return cls.not_found(detail)

    # -- table-creation case (LD-135) -------------------------------------------- #

    @classmethod
    def merge_not_expressible(cls, detail: str) -> "Refusal":
        """An authored table is not a plain R×C grid — the shape a **merged** (colspan /
        rowspan) table produces, which Markdown cannot express. The ``detail`` names the
        offending row and its width against the grid's, so the author can fix the grid;
        the engine never pads or truncates it into shape."""
        return cls(RefusalReason.MERGE_NOT_EXPRESSIBLE, detail)

    # -- compiled-no-op case (LD-574) -------------------------------------------- #

    @classmethod
    def change_not_expressible(cls, detail: str) -> "Refusal":
        """A counted change compiles to a request set that would write nothing new.

        The ``detail`` names the block, the property the compiled request cannot carry (or
        says the two spellings compose to the same block), and the route that works — the
        difference between a refusal a caller acts on and one that sends them into the source.
        Nothing is compiled: a green apply log is a receipt, so an entry the engine cannot
        realise never becomes one."""
        return cls(RefusalReason.CHANGE_NOT_EXPRESSIBLE, detail)

    # -- table-grow boundary (LD-575) -------------------------------------------- #

    @classmethod
    def table_grow_unsupported(cls, detail: str) -> "Refusal":
        """The table resolved, and the grow asked for is not the one that ships.

        The ``detail`` names the resolved table and **which** boundary was met — a spelling
        this tree has never measured (with the append spelling as the remedy) or larkdocio's
        own authoring cap (with a second table as the remedy). The two sentences stay distinct
        on purpose: an unmeasured route reported as a hard limit is a claim wider than its
        evidence, and a shipped cap reported as unmeasured invites a caller to retry it."""
        return cls(RefusalReason.TABLE_GROW_UNSUPPORTED, detail)

    # -- Markdown-compile case (LD-136) ------------------------------------------ #

    @classmethod
    def not_in_dialect(cls, detail: str) -> "Refusal":
        """A composed Markdown fragment names a construct the creatable set cannot
        express. The ``detail`` names **the construct and its 1-based source line** plus
        why it is inexpressible and what to do instead — the fragment is never partly
        composed, never flattened, and never approximated."""
        return cls(RefusalReason.NOT_IN_DIALECT, detail)

    # -- whole-document staleness (LD-139 / D9) ---------------------------------- #

    @classmethod
    def stale_document(cls, detail: str) -> "Refusal":
        """The **whole document** changed under the plan (or could not be confirmed
        unchanged), so the ENTIRE batch is refused with **zero writes issued**.

        The ``detail`` is built by :mod:`larkdocio.write.revision`
        (:func:`~larkdocio.write.revision.stale_document_detail` /
        :func:`~larkdocio.write.revision.unconfirmable_document_detail`) so every instance
        names the drift, states that nothing was written, and carries the re-download +
        re-plan recovery and the do-not-edit-concurrently warning in the guide's own words.
        Unlike every other reason this one is **not** a per-entry skip: it is stamped on
        every entry of the batch, because positioning is a property of the document."""
        return cls(RefusalReason.STALE_DOCUMENT, detail)

    # -- reconciliation (LD-233) --------------------------------------------------- #
    # One factory per reason, so a reconciliation refusal is built by naming what
    # happened rather than by hand-assembling an enum member and a string.

    @classmethod
    def marker_invented(cls, detail: str) -> "Refusal":
        """The edited projection named a block id the projection never emitted."""
        return cls(RefusalReason.MARKER_INVENTED, detail)

    @classmethod
    def marker_duplicated(cls, detail: str) -> "Refusal":
        """One marker id appears more than once in the edited projection."""
        return cls(RefusalReason.MARKER_DUPLICATED, detail)

    @classmethod
    def marker_absent(cls, detail: str) -> "Refusal":
        """A projected block has no marker in the edited projection — and absence is
        not deletion, so it refuses unless the caller dispositioned otherwise."""
        return cls(RefusalReason.MARKER_ABSENT, detail)

    @classmethod
    def marker_dropped(cls, detail: str) -> "Refusal":
        """A projected block has no marker in the edited projection, but the block's own
        text plainly came back with it — the marker was dropped, not the block."""
        return cls(RefusalReason.MARKER_DROPPED, detail)

    @classmethod
    def marker_relocated(cls, detail: str) -> "Refusal":
        """A surviving marker came back sitting on a different projected block's text."""
        return cls(RefusalReason.MARKER_RELOCATED, detail)

    @classmethod
    def marker_mangled(cls, detail: str) -> "Refusal":
        """A marker-shaped line that is not the canonical form, byte for byte."""
        return cls(RefusalReason.MARKER_MANGLED, detail)

    @classmethod
    def marker_orphaned(cls, detail: str) -> "Refusal":
        """A surviving marker came back with no content under it at all."""
        return cls(RefusalReason.MARKER_ORPHANED, detail)

    @classmethod
    def marker_order_changed(cls, detail: str) -> "Refusal":
        """The surviving markers are in a different order than the document, and a
        move is not expressible in the shipped request families."""
        return cls(RefusalReason.MARKER_ORDER_CHANGED, detail)

    @classmethod
    def block_type_mutation(cls, detail: str) -> "Refusal":
        """A marked block's edited form is a different block type."""
        return cls(RefusalReason.BLOCK_TYPE_MUTATION, detail)

    @classmethod
    def segment_ambiguous(cls, detail: str) -> "Refusal":
        """A marker's segment holds several pieces and none of them is the block."""
        return cls(RefusalReason.SEGMENT_AMBIGUOUS, detail)

    @classmethod
    def unmarked_content_changed(cls, detail: str) -> "Refusal":
        """Content the projection emitted without a marker came back changed."""
        return cls(RefusalReason.UNMARKED_CONTENT_CHANGED, detail)

    @classmethod
    def undecodable_text(cls, detail: str) -> "Refusal":
        """A piece of the edited projection cannot be decoded out of the projection's
        escaping, so it cannot be compared without guessing."""
        return cls(RefusalReason.UNDECODABLE_TEXT, detail)

    @classmethod
    def conserved_block_re_created(cls, detail: str) -> "Refusal":
        """A block the plan conserves would also have been planned as new content, which
        would leave the document holding it twice."""
        return cls(RefusalReason.CONSERVED_BLOCK_RE_CREATED, detail)

    # -- the apply-time disposition boundary ------------------------------------ #
    # One factory per apply-time reason, so the mandatory ``detail`` discipline is reachable
    # by name for each of them exactly as it is for every reason above.
    #
    # SCOPED, because the universal this comment used to state was false: it claimed "no call
    # site constructs a raw ``Refusal`` for them", and `larkdocio.write.disposition`'s
    # `disposition_refusal` does exactly that — it is handed a `Disposition` whose `reason` is
    # already the enum member, so dispatching back out to a factory keyed on that same member
    # would be a lookup table with one entry per row and nothing to check. The sheets engine
    # constructs its refusal the same way, at the same seam. Nothing is lost by it: `Refusal`'s
    # own `__post_init__` is what enforces a non-empty `detail`, on the constructor as much as
    # on any factory, so the discipline holds for every path either way. What the factories buy
    # is a NAMED constructor for a caller (or a test) that has a reason and a sentence and not a
    # `Disposition`.

    @classmethod
    def api_error(cls, detail: str) -> "Refusal":
        """Lark rejected this entry's write with a code. Nothing landed for it."""
        return cls(RefusalReason.API_ERROR, detail)

    @classmethod
    def permission_denied(cls, detail: str) -> "Refusal":
        """The app lacks a required scope — the detail relays Lark's own denial."""
        return cls(RefusalReason.PERMISSION_DENIED, detail)

    @classmethod
    def rate_limited(cls, detail: str) -> "Refusal":
        """Lark's rate limit survived the write transport's backoff-and-retry."""
        return cls(RefusalReason.RATE_LIMITED, detail)

    @classmethod
    def transport_failure(cls, detail: str) -> "Refusal":
        """The call failed below Lark; whether the write landed is indeterminate."""
        return cls(RefusalReason.TRANSPORT_FAILURE, detail)

    @classmethod
    def pagination_unterminated(cls, detail: str) -> "Refusal":
        """A paged read this entry depends on could not be run to exhaustion."""
        return cls(RefusalReason.PAGINATION_UNTERMINATED, detail)

    @classmethod
    def unexpected_error(cls, detail: str) -> "Refusal":
        """An un-modelled exception escaped this entry's apply step."""
        return cls(RefusalReason.UNEXPECTED_ERROR, detail)

    @classmethod
    def unverified_write(cls, detail: str) -> "Refusal":
        """The write returned and a step after it failed — applied, unverified."""
        return cls(RefusalReason.UNVERIFIED_WRITE, detail)

    @classmethod
    def not_attempted(cls, detail: str) -> "Refusal":
        """The batch halted earlier; this entry was never attempted."""
        return cls(RefusalReason.NOT_ATTEMPTED, detail)

    def to_dict(self) -> dict:
        d = {"reason": self.reason.value, "detail": self.detail}
        if self.candidate_ids:
            d["candidate_ids"] = list(self.candidate_ids)
            d["candidate_count"] = self.candidate_count
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Refusal":
        detail = d.get("detail")
        if not isinstance(detail, str) or not detail.strip():
            raise ValueError(
                "a Refusal wire record must carry a non-empty 'detail' (detail "
                f"is mandatory on every docx refusal); got {detail!r}"
            )
        return cls(
            reason=RefusalReason(d["reason"]),
            detail=detail,
            candidate_ids=tuple(d.get("candidate_ids", ())),
        )


class RefusedError(LarkConfigError, ValueError):
    """A **construction-time** refusal that carries its typed :class:`Refusal`.

    Some refusals cannot wait for the resolver: content that is *inexpressible* — an
    authored table whose rows differ in width, i.e. the merged-cell shape Markdown has no
    syntax for — must be refused where it is built, before it can reach a plan. The
    already refused impossible content at construction with a ``ValueError``; this subclass
    keeps that contract (``except ValueError`` still catches it, and every existing test of
    the construction discipline is unchanged) while **carrying the typed refusal** so a
    caller does not have to parse a message string:

    >>> try:                                                  # doctest: +SKIP
    ...     NewBlock.table([["a", "b"], ["c"]])
    ... except RefusedError as e:
    ...     e.refusal.reason, e.refusal.detail
    (<RefusalReason.MERGE_NOT_EXPRESSIBLE: 'merge-not-expressible'>, '…')

    That matters for the compiler rung (``compose(markdown)``), which turns a caught
    refusal straight into the refusal list it reports — one vocabulary end to end, with
    the mandatory ``detail`` intact.

    Also a :class:`~larkdocio.errors.LarkConfigError` — a local, pre-API unsupported-input
    problem, which is what an inexpressible-content refusal is — so ``except LarkDocIOError``
    catches it, as the base class promises. The ``ValueError`` half above is unchanged.
    """

    def __init__(self, refusal: Refusal):
        super().__init__(refusal.detail)
        self.refusal = refusal
