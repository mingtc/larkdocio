"""larkdocio.write.disposition — the docx apply-time DISPOSITION BOUNDARY.

**The invariant this module exists to make structural: an exception raised while APPLYING an
entry does not escape :func:`~larkdocio.write.apply.apply`'s per-entry loop, and every plan
entry ends in a typed, logged outcome.**

The docx engine was the last plan-gated engine without this boundary, and it was the holdout
rather than the pioneer: the sheets engine has had one since a raw
``LarkAPIError: Code 90204`` escaped its per-entry loop mid-batch, both Base engines adopted
it, and all three ride the shared stdlib-only leaf :mod:`larkdocio.common.disposition`. Here,
the entry loop had no ``except`` at all, so a create/patch/delete failure mid-batch propagated
out of ``apply()`` and the consumer received **no apply-log** — including for the entries that
had already written. ``write/README.md`` argued the 1:1 completeness of that log as an
absolute while exactly this outcome was reachable.

**What this module supplies, and what it deliberately does not.**

* :class:`DocxWriteWatch` — the shared
  :class:`~larkdocio.common.disposition.WriteWatch`, defaulted to :data:`WRITE_SEAMS`. **Its
  only content is that default.** The watching mechanism — the forwarding ``__getattr__``, the
  issued/completed accounting, the ``wrote`` answer — is authored ONCE, in the shared leaf, and
  this class adds not one line of it. That is the whole point of the leaf existing: this is the
  fourth surface to bind the boundary and the **first** to arrive without writing a copy of it.
* :func:`classify_apply_exception` — the docx classification table. **Emphatically NOT shared**
  (the leaf's own rule is *share the mechanism, never the classification*): the sheets rows
  encode measured sheets semantics, the Base rows are ruled separately, and the rows below are
  this surface's and are argued from this surface's doctrine.
* :func:`disposition_refusal` — the docx detail templates, formatted through the shared
  :func:`~larkdocio.common.disposition.disposition_detail` skeleton.

**THE DOCX SCOPE RULE, AND WHY IT IS NOT THE SHEETS ONE. Every classified failure HALTS.**

The sheets engine's per-entry doctrine is maintainer-blessed *for sheets*: an entry-scoped API error
refuses that entry and the batch **continues**, because there each entry carries its own
compare-and-swap and partial application is disclosed and expected. Copying that here would be
the one thing this change must not do, for a reason that has nothing to do with taste:

* **Continuing would ISSUE WRITES THAT THE ENGINE DOES NOT ISSUE TODAY.** Before this module
  existed, a mid-batch failure propagated and every later entry was never attempted — that is
  the shipped behaviour, and it is stated in
  :func:`~larkdocio.write.apply._insert_table_in_one_call`'s own docstring ("entries *after* it
  are never attempted"). This change exists to add a **record**, not to add writes. A safety
  fix that quietly starts writing where the previous release stopped is a worse defect than the
  one it closes.
* **The docx doctrine is whole-batch, not per-entry.** The whole-document compare-and-swap
  refuses the ENTIRE batch on drift with zero writes issued, and there is deliberately no
  partial-application accommodation past it. A per-entry "keep going" arm would contradict the
  surface's own stated position.
* **Blast radius is not knowable per entry here.** A docx batch's entries share one document
  and one revision; sheets' per-entry continuation is argued from each entry having its own
  anchor re-judged afresh, which is exactly what a docx batch does not have once the document
  has moved under it.

So :data:`~larkdocio.common.disposition.ENTRY_SCOPED` is imported (it is the shared vocabulary
and a future ruling may earn it a row) but **no row uses it today**, and that is asserted by
this surface's own tests rather than left as prose.

**What the boundary does NOT swallow.** Two escapes are deliberate and both are outside this
module:

* the plan gate — ``apply()`` still raises :class:`TypeError` for a non-``Plan``, before any
  entry exists to log against;
* the whole-document compare-and-swap re-raises a :class:`~larkdocio.errors.LarkRateLimitError`
  rather than treating throttling as drift. It runs **before** the entry loop, so it is not
  behind this boundary, and it is the reason the docx surface still states a position on the
  house apply-log invariant rather than declaring it outright.

**The deliberate ``BaseException`` carve-out.** Nothing here or in the loop catches
:class:`BaseException`: a ``KeyboardInterrupt`` / ``SystemExit`` / ``MemoryError`` is the
interpreter or the operator tearing the process down, and swallowing it into a log entry would
be a worse bug than the one this boundary prevents. The ``except Exception`` in the apply loop
is that carve-out, not an oversight.
"""
# The ONE disposition-boundary core. Imported, never re-implemented — this module is the
# fourth surface to bind it and the first to arrive without a copy of the mechanism.
from larkdocio.common.disposition import (      # noqa: F401 — ENTRY_SCOPED is re-exported
    ENTRY_SCOPED,
    SYSTEMIC,
    Disposition,
    disposition_detail,
    safe_denial,
    safe_text,
)
from larkdocio.common.disposition import WriteWatch as _SharedWriteWatch
from larkdocio.errors import (
    LarkAPIError,
    LarkPaginationError,
    LarkPermissionError,
    LarkRateLimitError,
)
from larkdocio.write.model import Refusal, RefusalReason

# --------------------------------------------------------------------------- #
# The client seam, split by whether a call MUTATES the document                 #
# --------------------------------------------------------------------------- #

#: Every :class:`~larkdocio.write.client.WriteClient` method that **mutates the document
#: body or its review conversation**. The write-watch keys on this set, so a method missing
#: from it would make the engine claim "nothing landed" about a call that landed something —
#: which is the single failure the whole boundary exists to prevent. It is held against the
#: write client's real public surface by this surface's own invariant suite (in the source repository),
#: so a new write op that forgets to register here reddens the suite rather than shipping.
#:
#: ``_patch_block`` is on the list under its private name because that is the name the apply
#: legs actually call; ``patch_block`` (its public wrapper) is on it too, because a seam set
#: that watched only one spelling would depend on which one a future leg picked.
WRITE_SEAMS = frozenset({
    "create_children",
    "create_descendant",
    "patch_block",
    "_patch_block",
    "batch_update_blocks",
    "batch_delete",
    "create_whole_document_comment",
    "delete_comment_reply",
})

#: The client's **file-lifecycle** calls — create / trash the whole DOCUMENT. A third
#: category, not a widening of :data:`WRITE_SEAMS`, and the distinction is a claim about what
#: the engine does: the write-watch proxies a write seam to decide whether **a plan entry's**
#: change landed, and creating or trashing a document is never a plan entry. The apply engine
#: calls neither — that is a caller's own explicit act. Declared so the read/write/lifecycle
#: split over the client surface stays exhaustive and provably so.
FILE_LIFECYCLE_SEAMS = frozenset({
    "create_document",
    "delete_document",
})

#: Every client method the engine calls that **only reads** — the live re-validation read, the
#: whole-document compare-and-swap anchor, the block listing the cell fill derives ids from,
#: and the comment thread's replies. Declared for the same exhaustiveness reason.
READ_SEAMS = frozenset({
    "get_document",
    "get_block",
    "read_document_revision",
    "list_document_blocks",
    "list_comment_replies",
})


class DocxWriteWatch(_SharedWriteWatch):
    """The shared :class:`~larkdocio.common.disposition.WriteWatch`, defaulted to
    :data:`WRITE_SEAMS`.

    **Its only content is that default.** Wrapping the client rather than threading a journal
    through the apply legs is what keeps the legs untouched: the boundary is one seam, and a
    leg cannot forget to report. ``issued`` becomes true when a write seam is *entered*;
    ``wrote`` only when one **returned** — and that difference is what lets the classification
    below tell "the write never happened" from "the write happened and a later step did not".
    """

    __slots__ = ()

    #: The docx write seams — hand-kept here, and pinned against the write client's real
    #: public surface by this surface's own guard (see :data:`WRITE_SEAMS`).
    DEFAULT_SEAMS = WRITE_SEAMS


#: This module's public path for the watch, the sheets/base spelling.
WriteWatch = DocxWriteWatch


# --------------------------------------------------------------------------- #
# The classification table — most-specific first, and every row SYSTEMIC        #
# --------------------------------------------------------------------------- #
#
# Ordering is load-bearing in two places, both for the same reason: `LarkRateLimitError` and
# `LarkPermissionError` are `LarkAPIError` subclasses that carry a `code`, so a base-class test
# placed first would swallow both. The coded / uncoded `LarkAPIError` split is the transport's
# own signal: `raise_for_lark_code` always attaches Lark's `code`, while the `URLError` wrap in
# `common.transport.RawHttpClient._send` cannot.
#
# Every row is SYSTEMIC. The argument is the module docstring's; it is not a shortcut.

#: The write RETURNED and something after it failed — the change IS in the document.
_UNVERIFIED = Disposition(SYSTEMIC, RefusalReason.UNVERIFIED_WRITE, "applied-unverified", "yes")
_RATE_LIMITED = Disposition(SYSTEMIC, RefusalReason.RATE_LIMITED, "refused", "no")
_PERMISSION_DENIED = Disposition(SYSTEMIC, RefusalReason.PERMISSION_DENIED, "refused", "no")
_PAGINATION = Disposition(SYSTEMIC, RefusalReason.PAGINATION_UNTERMINATED, "failed", "indeterminate")
_API_ERROR = Disposition(SYSTEMIC, RefusalReason.API_ERROR, "refused", "no")
_TRANSPORT = Disposition(SYSTEMIC, RefusalReason.TRANSPORT_FAILURE, "failed", "indeterminate")
_UNEXPECTED = Disposition(SYSTEMIC, RefusalReason.UNEXPECTED_ERROR, "failed", "indeterminate")


def classify_apply_exception(exc, *, wrote: bool) -> Disposition:
    """Classify ONE exception raised by a per-entry apply step into a :class:`Disposition`.

    ``wrote`` is :attr:`DocxWriteWatch.wrote` for that entry — whether a write seam
    **returned** before the exception. It is checked FIRST and overrides the exception's own
    class: once the change is in the document the only truthful record is
    ``applied-unverified``, whatever raised afterwards.

    Total by construction — the final ``return`` catches every exception type, including ones
    this library never raises — so there is no exception a caller can provoke that lacks a
    disposition.

    **Every row halts.** See the module docstring: continuing would issue writes this engine
    did not issue before the boundary existed, on the one surface whose stated position is
    whole-batch. The scope value is on every row rather than left implicit so that the day a
    ruling earns an entry-scoped arm, the row that gains it is the row that changed.
    """
    if wrote:
        return _UNVERIFIED
    if isinstance(exc, LarkRateLimitError):
        return _RATE_LIMITED
    if isinstance(exc, LarkPermissionError):
        # BEFORE the `LarkAPIError` arm, deliberately: this is a coded subclass of it.
        return _PERMISSION_DENIED
    if isinstance(exc, LarkPaginationError):
        return _PAGINATION
    if isinstance(exc, LarkAPIError):
        # A `code` means Lark itself answered. No `code` means the call never got an answer
        # (the URLError wrap) → INDETERMINATE, never reported as "nothing landed".
        return _API_ERROR if exc.code is not None else _TRANSPORT
    return _UNEXPECTED


# --------------------------------------------------------------------------- #
# The detail templates — this surface's own words                               #
# --------------------------------------------------------------------------- #
#
# Each states (a) what failed, (b) whether the document changed, and (c) what the batch did —
# the three questions a consumer reading an apply-log actually has. The mandatory-detail
# discipline of `larkdocio.write.model.refusal` binds here exactly as it binds a plan-time
# refusal: a typed reason with no WHY is a riddle.

_DETAIL_TEMPLATES = {
    RefusalReason.API_ERROR: (
        "Lark rejected this entry ({where}): {exc}. NOTHING landed for this entry. The batch "
        "HALTED and every remaining entry is logged not-attempted — the docx engine applies a "
        "batch whole, so it does not carry on past a rejected write. Entries BEFORE this one "
        "have applied and STAY applied; nothing was retried and nothing was rolled back. Read "
        "the log for what landed, then re-plan the remainder against the document as it now "
        "is. Lark code={code!r} msg={msg!r}."
    ),
    RefusalReason.PERMISSION_DENIED: (
        "Lark refused this entry because the app lacks a required SCOPE ({where}): {exc}. "
        "NOTHING landed for this entry. The batch HALTED and every remaining entry is logged "
        "not-attempted, because a missing grant is batch-wide by construction — it would "
        "refuse every later entry the same way. REPAIR: grant the permission(s) named below "
        "on the app in the Lark console — a grant is an administrator's console action, and "
        "this library never requests, widens or escalates a scope — then re-run dry_run and "
        "apply the remainder (the document may have moved meanwhile). Lark code={code!r} "
        "msg={msg!r}. {denial}"
    ),
    RefusalReason.RATE_LIMITED: (
        "Lark's rate limit (99991400) survived the write transport's backoff-and-retry "
        "({where}): {exc}. NOTHING landed for this entry. The batch HALTED — every remaining "
        "entry is logged not-attempted rather than hammering a throttled endpoint. Retry the "
        "remainder later, and re-run dry_run first: the document may have moved."
    ),
    RefusalReason.TRANSPORT_FAILURE: (
        "the call failed BELOW Lark ({where}): {exc}. Whether this entry's write landed is "
        "INDETERMINATE — the request may or may not have reached Lark, and the engine will "
        "not guess. The batch HALTED. RECONCILE THIS ENTRY BY READING THE DOCUMENT before "
        "re-applying it, then re-plan the remainder."
    ),
    RefusalReason.PAGINATION_UNTERMINATED: (
        "a paged read this entry depends on could not be run to exhaustion ({where}): {exc}. "
        "The server kept reporting more pages in a shape the walk cannot follow, so the list "
        "this entry derives its targets from may be SHORT — and writing from a short list "
        "would write to a subset without saying so. Whether anything landed for this entry is "
        "INDETERMINATE. The batch HALTED. READ THE DOCUMENT to see what is there before "
        "re-applying."
    ),
    RefusalReason.UNEXPECTED_ERROR: (
        "an unexpected {exc_type} escaped this entry's apply step ({where}): {exc}. It is "
        "recorded as an entry rather than thrown as a traceback — no Lark error, rate limit, "
        "transport failure or library bug escapes apply() untyped — but its blast radius is "
        "unknown, so whether the write landed is INDETERMINATE and the batch HALTED. "
        "RECONCILE THIS ENTRY BY READING THE DOCUMENT, and please report the traceback."
    ),
    RefusalReason.UNVERIFIED_WRITE: (
        "this entry's write ({wrote_seams}) RETURNED — the change IS in the document — but a "
        "step after it failed ({where}): {exc}. The write is therefore recorded as "
        "applied-unverified: applied, with an INCOMPLETE record of what it produced (the "
        "created block ids, the removed payload, or the cell fill that follows a created "
        "table, depending on the op). It is NOT called a refusal, because it landed. The "
        "batch HALTED; read the document and re-plan the remainder."
    ),
}

#: The last-resort wording, used only if a future :class:`Disposition` reason arrives without
#: its own template. Present because this code runs **inside** the boundary that must never
#: raise: a ``KeyError`` here would re-open the exact hole the boundary closes.
_DETAIL_FALLBACK = (
    "this entry's apply step failed ({where}) with {exc_type}: {exc}. Recorded as "
    "'{reason}' — it became a typed entry rather than a traceback out of apply(). Whether "
    "the write landed: {landed}."
)

#: What a ``not-attempted`` entry says. It is a template rather than a
#: :data:`_DETAIL_TEMPLATES` row because no exception is classified for these entries: they
#: are the remainder, and what they need to state is where the batch stopped and why.
NOT_ATTEMPTED_DETAIL = (
    "this entry was NEVER ATTEMPTED: the batch halted at entry {index} of {total} "
    "('{reason}') and the docx engine does not carry on past a halt. No call was made for "
    "this entry and NOTHING landed for it. The halting entry's own log entry carries the full "
    "reason; ApplyLog.halt carries it too. Re-run dry_run against the document as it now is "
    "before re-applying the remainder."
)


def disposition_refusal(disposition: Disposition, exc, *, where: str,
                        wrote_seams=()) -> Refusal:
    """The typed :class:`~larkdocio.write.model.Refusal` for a classified failure.

    ``where`` names the entry (its op + target) so the detail is actionable without
    cross-referencing the plan; ``wrote_seams`` names the write seam(s) that already returned
    (the ``applied-unverified`` case).

    The formatting skeleton is the shared
    :func:`~larkdocio.common.disposition.disposition_detail`; the TEMPLATES it formats are
    this surface's own, and this surface names no ``extra`` field.
    """
    detail = disposition_detail(
        disposition, exc, where=where, wrote_seams=wrote_seams,
        templates=_DETAIL_TEMPLATES, fallback=_DETAIL_FALLBACK,
    )
    return Refusal(reason=disposition.reason, detail=detail)


def not_attempted_refusal(halt: dict, *, total: int) -> Refusal:
    """The typed refusal every entry after a halt carries — one wording, built in one place."""
    return Refusal.not_attempted(NOT_ATTEMPTED_DETAIL.format(
        index=halt["index"], total=total, reason=halt["reason"].value))


__all__ = [
    "DocxWriteWatch",
    "FILE_LIFECYCLE_SEAMS",
    "NOT_ATTEMPTED_DETAIL",
    "READ_SEAMS",
    "WRITE_SEAMS",
    "WriteWatch",
    "classify_apply_exception",
    "disposition_refusal",
    "not_attempted_refusal",
    "safe_denial",
    "safe_text",
]
