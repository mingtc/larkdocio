"""larkdocio.base.disposition — the apply-time DISPOSITION BOUNDARY for Base writes (LD-259).

**The invariant this module exists to make structural: no exception escapes
:func:`larkdocio.base.apply.apply`, and EVERY entry ends in a typed, logged disposition.** The
shape is :mod:`larkdocio.sheets.disposition`'s — the module that closed the same hole on the
sheets engine when a raw ``LarkAPIError`` escaped its per-entry loop mid-batch. **It is no
longer merely the same shape — it is the same code** (LD-533): the mechanism both modules had
copied lives once, in the leaf :mod:`larkdocio.common.disposition`, and is imported here.
The two pieces are still the same two:

* :class:`WriteWatch` — a proxy over the write client that records whether a **write seam**
  actually ran and returned. Without it the boundary could only guess whether a failure left
  the Base untouched, and a log that guesses is a log that lies: a post-write anchor read that
  fails must NOT be reported as "nothing landed". **SHARED** — this module binds only its own
  default seam set (:data:`WRITE_SEAMS`); the schema engine passes its own.
* :func:`classify_apply_exception` — the ONE classification table mapping an exception (plus
  that write-watch answer) to a :class:`Disposition`: its **scope** (entry-scoped ⇒ the batch
  continues, systemic ⇒ it halts), its typed :class:`~larkdocio.base.plan.Refusal` reason, its
  apply-log ``outcome``, and whether the change **landed**. **NOT shared, deliberately**: the
  rows below are ruled (D4′) and sheets' rows are its own measured semantics.

**The Base classification table is RULED (D4′), not proposed.** The ruling is *"LD-206
transfers plus the per-table ``STALE_BASE`` refinement"*, and it falls out row by row:

* ``1254043 RecordIdNotFound`` — **entry-scoped, continue.** Lark answered about the records in
  that call; a stale record id says nothing about the next call's records.
* ``1254041 TableIdNotFound`` / ``1254004 WrongTableId`` / ``1002`` (the app is trashed) —
  **systemic, HALT.** These are answers about the *table* or the *app*, not about a record, and
  their blast radius **is** knowable: every remaining call would be refused identically.
* a **scope denial** (:class:`~larkdocio.errors.LarkPermissionError`, the ``99991672`` class) —
  **systemic, HALT**, inherited verbatim from LD-206: a missing grant would refuse every
  remaining call the same way, so continuing spends one throttled write call per call on a
  condition that cannot clear between them.
* ``1254069`` / ``1254060`` / ``1255002`` / ``99992402`` — the **value-conversion** codes.
  **Entry-scoped, continue:** they are Lark's answer about the values in that call, and the
  next call's values are its own question.

Everything else follows the sheets doctrine, for the reason stated there: a coded error means
Lark judged the call, so it is entry-scoped; an **uncoded** ``LarkAPIError`` is the transport's
``URLError`` wrap, so whether the write landed is **indeterminate** and the batch halts.

**``STALE_BASE`` is not in this table**, deliberately: it is not an exception. It is the
client-side compare-and-swap's own verdict, and per D4′ it halts **that table's** entries while
every other table is judged against its own anchor — see :func:`larkdocio.base.apply.apply`.

**The deliberate ``BaseException`` carve-out.** The boundary catches :class:`Exception`, not
:class:`BaseException`: a ``KeyboardInterrupt`` / ``SystemExit`` / ``MemoryError`` is the
interpreter or the operator tearing the process down, and swallowing it into a log entry would
be a worse bug than the one this module prevents.
"""
from dataclasses import dataclass

from larkdocio.base.errors import TableCreatedViewNotNamed
from larkdocio.base.media import BaseMediaError
from larkdocio.base.plan import Refusal
from larkdocio.base.write_ops import WRITE_OPS
# LD-533 — the ONE disposition-boundary core. Re-exported under this module's own historical
# names (`_safe_text`, `_safe_denial`, `_DENIAL_*`) because THIS is their public path: every
# call site and every test that imported them from here still resolves, and the module's own
# prose still cites them at these addresses.
from larkdocio.common.disposition import (      # noqa: F401 — re-exported: this IS the path
    DENIAL_ABSENT as _DENIAL_ABSENT,
    DENIAL_UNRENDERABLE as _DENIAL_UNRENDERABLE,
    ENTRY_SCOPED,
    SYSTEMIC,
    Disposition,
    disposition_detail,
    safe_denial as _safe_denial,
    safe_text as _safe_text,
)
from larkdocio.common.disposition import WriteWatch as _SharedWriteWatch
from larkdocio.errors import (
    LarkAPIError,
    LarkConfigError,
    LarkPermissionError,
    LarkRateLimitError,
)

# --------------------------------------------------------------------------- #
# Disposition scope                                                             #
# --------------------------------------------------------------------------- #
#
# `ENTRY_SCOPED` / `SYSTEMIC` are imported above rather than assigned here. The two values
# were already byte-identical to the sheets copy (measured, LD-533), and the reason THIS
# module gave for them is kept: the failure is attributable to **this call** (a Base call
# rides many records), so its entries refuse and the batch keeps going; a systemic failure is
# not call-local, or its blast radius is unknown, so the batch halts and every remaining
# entry is logged ``not-attempted``. The vocabulary is shared; which exception lands in which
# arm is this module's ruled table and no one else's.


# --------------------------------------------------------------------------- #
# The client seam, split by whether a call MUTATES the Base                     #
# --------------------------------------------------------------------------- #

#: Every client method that **mutates** the Base — **projected off the write-op registry**
#: rather than hand-listed, so a write op added to
#: :data:`larkdocio.base.write_ops.WRITE_OPS` cannot be forgotten here (which would make the
#: engine claim "nothing landed" about a call that landed something).
WRITE_SEAMS = frozenset(descriptor.name for descriptor in WRITE_OPS)

#: Every client method the engine calls that **only reads**: the compare-and-swap anchor (the
#: table list), and the tier-2 precondition re-read (the same two calls L1 makes). Declared so
#: the read/write split over the seam is **exhaustive** and provably so.
READ_SEAMS = frozenset({"list_tables", "list_fields", "search_records"})


class BaseWriteWatch(_SharedWriteWatch):
    """The shared :class:`~larkdocio.common.disposition.WriteWatch`, defaulted to
    :data:`WRITE_SEAMS`.

    **Its only content is that default** — the watching mechanism (the forwarding
    ``__getattr__``, the issued/completed accounting, the ``wrote`` answer) is authored ONCE, in
    the shared core, and this class adds not one line of it. The binding has to live on a
    surface because the core is a leaf: it cannot import a seam registry without becoming a
    surface itself, and a watch that defaulted to *no* seams would report "nothing landed"
    about a call that landed something.

    Why a bound default at all, rather than every caller naming its seams: the record engine's
    own construction is ``WriteWatch(client)`` and the schema engine's is
    ``WriteWatch(client, seams=SCHEMA_WRITE_SEAMS)`` — the ``seams`` parameter exists for the
    second, and keeping the default keeps every landed caller, and :data:`WRITE_SEAMS` itself,
    exactly as it was.
    """

    __slots__ = ()

    #: The record engine's seams — projected off the write-op registry (see
    #: :data:`WRITE_SEAMS`), so a new write op cannot be forgotten here.
    DEFAULT_SEAMS = WRITE_SEAMS


# LD-533 — this module's public path for the watch. Unchanged for every caller and every
# test: `from larkdocio.base.disposition import WriteWatch` still resolves, and still takes
# `seams=` for the schema engine.
WriteWatch = BaseWriteWatch


# --------------------------------------------------------------------------- #
# Disposition — one exception → one typed, logged outcome                       #
# --------------------------------------------------------------------------- #
#
# :class:`Disposition` is imported from the shared core above. Its fields and its
# halts/continues accessors were already byte-identical to the sheets copy (measured, LD-533);
# what this module's own docstring added — that ``reason`` is a
# :class:`~larkdocio.base.plan.Refusal`, and that ``landed``'s honest third value is why
# ``failed`` is not called a refusal — is preserved at the new address. The ROWS that build
# one are below, and they are this surface's alone.


#: Lark codes whose blast radius **is** knowable: they are answers about the TABLE or the APP,
#: so every remaining call would be refused identically (D4′).
SYSTEMIC_CODES = (
    1254041,   # TableIdNotFound — no such table in this Base
    1254004,   # WrongTableId — the id is malformed
    1002,      # the Base itself has been trashed
)

#: Lark codes that are answers about the RECORDS or the VALUES in one call (D4′). The batch
#: continues: the next call's records and values are its own question.
ENTRY_SCOPED_CODES = (
    1254043,   # RecordIdNotFound — a stale record id
    1254069,   # AttachFieldConvFail
    1254060,   # TextFieldConvFail — the read shape is not the write shape
    1255002,   # internal error — observed for a semantically impossible value
    99992402,  # field validation failed, with the accepted enum in the body
    # ---- the PROTECTED-LAST floors (LD-265) ---- #
    # Entry-scoped for exactly the reason the ruled table gives: Lark's answer is about THIS
    # object's protection, and it says nothing whatever about the other entries. A batch that
    # halted on one would refuse deletes the server would have accepted.
    1254034,   # the Base's last table cannot be deleted
    1254023,   # a table's last view cannot be deleted (LD-264's code, reused not redefined)
)

#: What a caller can DO about a protected-last refusal, per code. Appended to the refusal's own
#: detail so the answer arrives with its repair rather than as a number to look up. Each
#: sentence is authored by the family that owns the object and **quoted** here — the last-view
#: one is LD-264's, unchanged.
_PROTECTED_LAST_ADVICE = {
    1254034: "larkdocio.base.schema_ops_destructive.LAST_TABLE_IS_PROTECTED",
    1254023: "larkdocio.base.schema_ops_views.LAST_VIEW_IS_PROTECTED",
}


def protected_last_advice(code):
    """The repair sentence for a protected-last code, or ``None``.

    Resolved lazily by name so this module — which the families import through the engine —
    does not import them back at module level.
    """
    import importlib

    anchor = _PROTECTED_LAST_ADVICE.get(code)
    if anchor is None:
        return None
    module_name, attribute = anchor.rsplit(".", 1)
    try:
        return getattr(importlib.import_module(module_name), attribute)
    except Exception:      # noqa: BLE001 — advice is worth less than the boundary's invariant
        return None

_UNVERIFIED = Disposition(SYSTEMIC, Refusal.UNVERIFIED_WRITE, "applied-unverified", "yes")
_RATE_LIMITED = Disposition(SYSTEMIC, Refusal.RATE_LIMITED, "refused", "no")
#: LD-206, inherited verbatim: a scope denial is the one coded failure that is knowably
#: batch-wide.
_PERMISSION_DENIED = Disposition(SYSTEMIC, Refusal.PERMISSION_DENIED, "refused", "no")
_SYSTEMIC_API_ERROR = Disposition(SYSTEMIC, Refusal.API_ERROR, "refused", "no")
_API_ERROR = Disposition(ENTRY_SCOPED, Refusal.API_ERROR, "refused", "no")
_TRANSPORT = Disposition(SYSTEMIC, Refusal.TRANSPORT_FAILURE, "failed", "indeterminate")
_INVALID_REQUEST = Disposition(ENTRY_SCOPED, Refusal.INVALID_REQUEST, "refused", "no")
#: LD-268 — the attachment out-of-band leg, kept OUT of the bitable taxonomy on purpose. An
#: upload that failed attached nothing; a download that failed mints nothing either way, since
#: the token was minted by the upload. So ``landed`` is ``"no"`` and the batch continues.
_MEDIA_LEG_FAILURE = Disposition(ENTRY_SCOPED, Refusal.MEDIA_LEG_FAILURE, "refused", "no")
_UNEXPECTED = Disposition(SYSTEMIC, Refusal.UNEXPECTED_ERROR, "failed", "indeterminate")


def _code_of(exc):
    code = getattr(exc, "code", None)
    if code is None:
        return None
    try:
        return int(str(code))
    except (TypeError, ValueError):
        return code


def classify_apply_exception(exc, *, wrote: bool) -> Disposition:
    """Classify ONE exception raised by an apply step into a :class:`Disposition`.

    ``wrote`` is :attr:`WriteWatch.wrote` for that call — whether a write seam **returned**
    before the exception. It is checked FIRST and overrides the exception's own class: once the
    change is on the Base the only truthful record is ``applied-unverified``, and the batch must
    halt because the compare-and-swap anchor is no longer known.

    Total by construction — the final ``return`` catches every exception type, including ones
    this library never raises — so there is no exception a caller can provoke that lacks a
    disposition.
    """
    if wrote:
        return _UNVERIFIED
    if isinstance(exc, TableCreatedViewNotNamed):
        # BEFORE the LarkAPIError arm, deliberately (the BaseMediaError precedent): this IS a
        # coded API error, and the generic arm would render *"NOTHING landed"* about a call
        # whose TABLE is on the Base right now. The write seam did not return — the composite's
        # second leg raised inside it — so `wrote` is False and cannot speak for it; the
        # exception itself says the create landed, and this is the arm that believes it.
        return _UNVERIFIED
    if isinstance(exc, LarkRateLimitError):
        return _RATE_LIMITED
    if isinstance(exc, LarkPermissionError):
        # BEFORE the LarkAPIError arm, deliberately: it is a coded subclass, so the generic
        # arm would otherwise claim it and call a missing grant entry-scoped.
        return _PERMISSION_DENIED
    if isinstance(exc, BaseMediaError):
        # BEFORE the LarkAPIError arm, deliberately: it is a subclass of it, so the generic
        # arm would otherwise claim a DRIVE MEDIA failure and log it as though the bitable API
        # had judged the record. Entry-scoped for the ruled reason — Lark's answer is about
        # THIS entry's file, and the next entry's file is its own question.
        #
        # A KNOWN, DELIBERATE ASYMMETRY, recorded here because it is the arm that produces it.
        # A media leg failure can now carry a SCOPE DENIAL (`exc.denial is not None`) — the
        # media legs classify through `errors.api_error_as` and keep their own class. This arm
        # is reached BEFORE the `LarkPermissionError` arm can see it, because that arm matches
        # on the class and this exception is not of that class. So a missing media grant is
        # logged ENTRY-SCOPED and the batch CONTINUES, where every other surface treats a
        # denial as batch-wide and HALTS. That is preserved on purpose and is not an
        # oversight: the arm ordering, the reason above, and the refusal wording a consumer
        # reads are all unchanged by the classification work, and changing what a batch DOES
        # is a behaviour change with its own consequences (every remaining entry's outcome
        # flips from attempted to not-attempted) that no acceptance criterion asked for.
        # What is now true and was not before is that the denial RECORD is on the exception
        # and in the log detail, so the caller can see the missing scope even while the batch
        # runs on. Whether the halt should follow the record is a separate ruling.
        return _MEDIA_LEG_FAILURE
    if isinstance(exc, LarkAPIError):
        code = _code_of(exc)
        if code is None:
            # No code means the call never got an answer (the URLError wrap) → systemic and
            # INDETERMINATE.
            return _TRANSPORT
        if code in SYSTEMIC_CODES:
            return _SYSTEMIC_API_ERROR
        return _API_ERROR
    if isinstance(exc, LarkConfigError):
        return _INVALID_REQUEST
    return _UNEXPECTED


#: Human-readable, actionable per-reason wording. Each states (a) what failed, (b) whether the
#: Base changed, and (c) what the batch did — the three questions a consumer reading an
#: apply-log actually has.
_DETAIL_TEMPLATES = {
    Refusal.API_ERROR: (
        "Lark rejected this call ({where}): {exc}. NOTHING landed for its entries. {aftermath} "
        "Lark code={code!r} msg={msg!r}."
    ),
    Refusal.INVALID_REQUEST: (
        "this entry could not be turned into a valid request ({where}): {exc}. No call was "
        "made and NOTHING landed. The batch CONTINUED with the remaining calls."
    ),
    Refusal.PERMISSION_DENIED: (
        "Lark refused this call because the app lacks a required SCOPE ({where}): {exc}. "
        "NOTHING landed. The batch HALTED and every remaining entry is logged not-attempted, "
        "because a missing grant is batch-wide by construction — it would refuse every "
        "remaining call identically. REPAIR: grant the permission(s) named below on the app in "
        "the Lark console — a grant is an administrator's console action, and this library "
        "never requests, widens or escalates a scope — then re-run dry_run and apply the "
        "remainder (the table may have moved meanwhile). Lark code={code!r} msg={msg!r}. "
        "{denial}"
    ),
    Refusal.MEDIA_LEG_FAILURE: (
        "the ATTACHMENT MEDIA leg failed ({where}): {exc}. This is the drive media family, "
        "NOT the bitable API — Lark judged the FILE, not the record — so nothing was written "
        "to the table for this entry and the batch CONTINUED. Note that an upload which "
        "already returned a file_token has left PERMANENT residue: no route in Lark's open "
        "API purges drive media, measured, not assumed — the enumeration and its scope are "
        "in larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA. A failed "
        "download leaves none. Lark code={code!r} msg={msg!r}."
    ),
    Refusal.RATE_LIMITED: (
        "Lark's rate limit survived the write client's own pacing ({where}): {exc}. NOTHING "
        "landed. The batch HALTED — every remaining entry is logged not-attempted rather than "
        "hammering a throttled endpoint. Retry the remainder later, re-running dry_run first: "
        "the table may have moved."
    ),
    Refusal.TRANSPORT_FAILURE: (
        "the call failed BELOW Lark ({where}): {exc}. Whether it landed is INDETERMINATE — the "
        "request may or may not have reached Lark, and the engine will not guess. The batch "
        "HALTED. RECONCILE THESE RECORDS BY READING THE TABLE before re-applying them, then "
        "re-plan the remainder."
    ),
    Refusal.UNEXPECTED_ERROR: (
        "an unexpected {exc_type} escaped this apply step ({where}): {exc}. It is recorded "
        "rather than raised — no exception escapes apply() — but its blast radius is unknown, "
        "so whether the write landed is INDETERMINATE and the batch HALTED. RECONCILE THESE "
        "RECORDS BY READING THE TABLE, and please report the traceback."
    ),
    Refusal.UNVERIFIED_WRITE: (
        "this call's write ({wrote_seams}) RETURNED — the change IS on the Base — but a "
        "post-write step then failed ({where}): {exc}. It is therefore recorded as "
        "applied-unverified: applied, with an INCOMPLETE verification record (no post-write "
        "`table.revision`, so the write-effect oracle could not run). The batch HALTED because "
        "the compare-and-swap anchor is now unknown; re-read the table and re-plan the "
        "remainder."
    ),
}

#: The last-resort wording, used only if a future :class:`Disposition` reason arrives without
#: its own template. Present because this code runs **inside** the boundary that must never
#: raise: a ``KeyError`` here would re-open the exact hole the boundary closes.
_DETAIL_FALLBACK = (
    "this apply step failed ({where}) with {exc_type}: {exc}. Recorded as '{reason}' — no "
    "exception escapes apply(). Whether the write landed: {landed}."
)

#: What the entry-scoped / systemic split MEANS, in the two sentences a reader of one refusal
#: needs. Written once here so the two arms of the ruled table cannot drift apart in prose.
_CONTINUED = (
    "The batch CONTINUED — Lark answered about the records or the values in this call, so the "
    "remaining calls are still made, each with its own guards and its own dispositions."
)
_HALTED = (
    "The batch HALTED and every remaining entry is logged not-attempted: this answer is about "
    "the TABLE or the APP, so every remaining call would be refused identically and continuing "
    "would spend a throttled write call per call on a condition that cannot clear between them."
)

#
# `_DENIAL_ABSENT`, `_DENIAL_UNRENDERABLE`, `_safe_text` and `_safe_denial` are imported from
# the shared core at the top of this module, under these same private names, because these are
# their addresses here. Measured at LD-533: the two paragraphs were already byte-identical to
# the sheets copies (202 and 170 characters) and both helper BODIES were identical too — the
# only thing that differed was how fully they were documented, and the fuller account won and
# travelled to the core. So no text a consumer reads changed. The reason `_DENIAL_ABSENT`
# states an ABSENCE rather than filling it — no scope string is invented, ever — is kept
# verbatim at the new address, and `PLATFORM_ANOMALY_NOT_YOUR_PLAN` below still cites it as
# the standard it follows one surface over.


# --------------------------------------------------------------------------- #
# The PLAN-WIDE platform-anomaly disclosure (LD-337)                            #
# --------------------------------------------------------------------------- #

#: **The plan-wide PLATFORM-ANOMALY disclosure — the invariant half.** Held as ONE text so the
#: two places it is published (the apply log's ``platform_anomaly`` slot and each matching
#: entry's ``refusal.detail``) cannot drift into two opinions, and public because it is a
#: consumer-facing promise: a promise held privately is one nothing can name.
#:
#: **Why it exists.** ``9499`` is in neither ruled table, so it falls through to ``_API_ERROR``
#: and renders :data:`_CONTINUED` — *"Lark answered about the records or the values in this
#: call"* — which is exactly what the 2026-08-07 ``/fields`` incident disproved: Lark answered
#: about the **TableId**, on an id the read client had vouched for on the same path one second
#: earlier. This text is **appended** to that one; it replaces nothing and re-rules nothing.
#:
#: It states its EVIDENCE and stops. No cause, no diagnosis, no scope and no endpoint status is
#: named — the :data:`_DENIAL_ABSENT` standard, one surface over.
PLATFORM_ANOMALY_NOT_YOUR_PLAN = (
    "What that pattern MEANS: the condition is on the PLATFORM side of this call, and it is "
    "not in your plan. Entries carrying different arguments do not all draw one identical "
    "refusal on table ids this run's own read client listed a moment earlier — a plan error "
    "refuses per entry, about that entry. WHAT IS NOT CLAIMED: this note names no cause and no "
    "diagnosis. Nothing about the far side is visible from a refusal, so nothing about it is "
    "invented here; Lark's own code and message above are its whole answer. WHAT TO DO: change "
    "NOTHING in your plan on this evidence. Re-run it when this route answers again, re-running "
    "the dry run first — the Base may have moved meanwhile. For a report to Lark, quote the "
    "code and message above together with the response body's log_id when Lark sent one; that "
    "identifier is the handle for the call. This library did NOT retry and will not: every "
    "entry already refused identically, so a backoff would trade a fast, legible failure for a "
    "slow one."
)

#: The OBSERVED half — this run's own evidence, formatted per run. **Code-agnostic on purpose:**
#: the rule is "a code the ruled tables do not know", never a list of codes, because a list is
#: whack-a-mole against a platform that can answer anything.
_PLATFORM_ANOMALY_OBSERVED = (
    "PLATFORM ANOMALY, NOT YOUR PLAN. OBSERVED: all {n} of the {n} calls this plan attempted "
    "refused, every one of them with the SAME Lark code {code} — a code this library's "
    "classification table does not know — on table id(s) {table_ids} that THIS RUN's read "
    "client itself listed."
)


# --------------------------------------------------------------------------- #
# The platform-anomaly HALT — the CONSEQUENCE of the detection above (LD-338)    #
# --------------------------------------------------------------------------- #
#
# The detection above is PLAN-WIDE and post-hoc. The halt needs the same verdict while entries
# REMAIN, so the engine evaluates the very same predicate over the PREFIX of attempts it has in
# hand (see ``schema_apply``). Nothing here relaxes, widens or re-tunes the predicate, and the
# ruled tables (:data:`SYSTEMIC_CODES` / :data:`ENTRY_SCOPED_CODES`) and
# :attr:`Disposition.halts` are untouched: the halt is set by an engine-level PLAN rule ABOVE
# the classifier, so D4′'s per-exception ruling stands exactly as written.

#: **The floor: how many identical alien refusals make a PATTERN.** ONE is not a pattern —
#: halting on a single unmodelled code would turn every one-off into a batch-stopper and re-rule
#: the entry-scoped/systemic split by the back door, for every code outside the ruled tables. So
#: the same floor governs the plan-wide disclosure (condition 1 of
#: :func:`plan_wide_platform_anomaly`) and the halt: **one reader, one number, no second
#: threshold to drift.** It is a module constant and deliberately **NOT a public knob** — no
#: parameter on ``schema_apply`` takes it, because a caller-tunable halt threshold is its own
#: decision to make and its own surface to keep.
PLATFORM_ANOMALY_MIN_ATTEMPTS = 2

#: The aftermath sentence for a refusal whose batch **halted** on the plan-wide anomaly. It
#: replaces :data:`_CONTINUED` in an already-formatted detail (never the code, never Lark's
#: ``msg``) because that sentence would otherwise claim the batch went on — the one thing a
#: halted batch demonstrably did not do. Reasoned exactly like :data:`_HALTED`, whose
#: ``permission-denied`` case is this library's shipped precedent for stopping on a condition
#: that cannot clear between entries.
PLATFORM_ANOMALY_HALTED = (
    "The batch HALTED and every remaining entry is logged not-attempted: every call this plan "
    "had attempted refused identically, so the remaining calls would be refused the same way "
    "and continuing would spend one throttled write per entry on a condition that cannot clear "
    "between them. NOTHING was retried and nothing was waited for."
)

#: What a **skipped** entry's own detail says when the halt was the plan-wide anomaly. Names the
#: anomaly as the cause (not merely "the batch halted at …"), states that nothing was sent, and
#: says what a re-run does — the house log-completeness invariant
#: (:data:`~larkdocio.capabilities._contracts.APPLY_LOG_COMPLETE`) is that a skipped entry is
#: enumerated **and explained**, never silently dropped.
PLATFORM_ANOMALY_NOT_ATTEMPTED = (
    "NOTHING was sent for this entry: the batch halted at {where} on a PLATFORM ANOMALY, NOT "
    "YOUR PLAN. Every call this plan attempted refused with the same Lark code {code} — a code "
    "this library's classification table does not know — on table id(s) this run's own read "
    "client had listed, so the remaining entries were not attempted rather than spending one "
    "throttled write each on a condition that cannot clear between them. This entry's own "
    "arguments were never judged by Lark and nothing here says they are wrong. A RE-RUN applies "
    "it normally once that route answers again: re-run the dry run first, because the Base may "
    "have moved and this rung has no revision guard that would notice."
)


def platform_anomaly_halted(detail: str) -> str:
    """``detail`` with its ``CONTINUED`` aftermath re-stated as :data:`PLATFORM_ANOMALY_HALTED`.

    An **after-the-fact rewrite of one sentence**, for the reason the append seam exists: the
    per-entry detail is formatted before the pattern is knowable, so the correction can only
    arrive later. A plain :meth:`str.replace` on a fixed sentence — no formatting, no template —
    so a Lark message full of braces can never break the one path that must not raise. A detail
    that carries no such sentence is returned unchanged.
    """
    return detail.replace(_CONTINUED, PLATFORM_ANOMALY_HALTED)


def platform_anomaly_not_attempted(where, code) -> str:
    """The skipped entry's detail for an anomaly halt. Substitution only — it cannot raise."""
    return PLATFORM_ANOMALY_NOT_ATTEMPTED.format(where=where, code=code)


class ReadVouch:
    """A proxy over the READ client that records the table ids its listings VOUCHED for.

    :class:`WriteWatch`'s shape on the other side of the seam, and for the same reason: the
    engine's legs stay untouched, and a leg cannot forget to report. It **adds no call** — it
    observes the listings the engine already makes (the compare-and-swap anchor read, the
    read-backs, a family's own ``table_revision``) and remembers which table ids came back.

    That set is the evidence behind the plan-wide platform-anomaly claim: *"on ids this run's
    read client itself listed"*. Empty means no listing happened, which is why an anomaly is
    never claimed from an empty set — see :func:`plan_wide_platform_anomaly`.
    """

    __slots__ = ("_client", "_table_ids")

    def __init__(self, client):
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_table_ids", set())

    @property
    def vouched_table_ids(self) -> frozenset:
        return frozenset(self._table_ids)

    def list_tables(self, *args, **kwargs):
        tables = self._client.list_tables(*args, **kwargs)
        for table in (tables or ()):
            table_id = getattr(table, "table_id", None)
            if table_id:
                self._table_ids.add(table_id)
        return tables

    def __getattr__(self, name):
        return getattr(self._client, name)


@dataclass(frozen=True)
class AttemptedWrite:
    """ONE schema write call the engine **issued**, and how it ended.

    ``reason`` is ``None`` when the call **returned** — which is what makes "every attempted
    entry refused" checkable at all. Recorded per attempt rather than derived from the log
    afterwards, because the log entry keeps the refusal's prose and not Lark's ``code``.
    """

    position: int
    table_id: object = None
    reason: object = None
    code: object = None


def attempted_write(position, table_id, *, disposition=None, exc=None) -> AttemptedWrite:
    """Record one issued write call. No ``disposition`` ⇒ the call RETURNED."""
    if disposition is None:
        return AttemptedWrite(position=position, table_id=table_id)
    return AttemptedWrite(position=position, table_id=table_id,
                          reason=disposition.reason, code=_code_of(exc))


@dataclass(frozen=True)
class PlatformAnomaly:
    """The plan-wide verdict: this run's refusals are one platform-side condition."""

    code: object
    entries: int
    table_ids: tuple
    positions: tuple
    disclosure: str

    def to_dict(self) -> dict:
        return {
            "reason": Refusal.API_ERROR,
            "code": self.code,
            "entries": self.entries,
            "table_ids": list(self.table_ids),
            "detail": self.disclosure,
        }


def plan_wide_platform_anomaly(attempts, *, vouched_table_ids):
    """The :class:`PlatformAnomaly` for one finished run, or ``None``.

    **Only knowable POST-HOC**, which is why it lives here and is called from the END of
    :func:`larkdocio.base.schema_apply.schema_apply`: :func:`disposition_refusal` sees one
    exception and cannot see "every entry".

    **The same predicate is ALSO the engine's PREFIX rule (LD-338).** ``schema_apply`` evaluates
    it over the attempts it has in hand while entries remain, and halts the tail when it fires:
    conditions 1 and 2 are exactly what makes that safe — the floor is
    :data:`PLATFORM_ANOMALY_MIN_ATTEMPTS`, and an entry that **applied** anywhere in the prefix
    disarms the rule permanently, because a plan that is landing writes is not meeting a
    platform-wide condition. One predicate, one threshold, evaluated at two moments.

    Six conjunctive conditions, **all** required — any one absent and the log keeps today's
    shape byte for byte. The bias is deliberately toward the FALSE NEGATIVE: a missed anomaly
    costs a consumer what today already costs them, while a false one would teach them to
    distrust every refusal this library writes.

    1. **at least :data:`PLATFORM_ANOMALY_MIN_ATTEMPTS` attempted entries** — "every entry" over
       a set of one is evidence of nothing.
    2. **every attempted entry refused** — a call that returned may have landed, and a plan that
       landed anything is not a platform-wide condition.
    3. **one and the same Lark code** — a mixed-code plan is Lark judging each call.
    4. **a code NEITHER ruled table knows** — the consumer's *"non-bitable-family"* clause. The
       ruled codes are in the table precisely because Lark judged the records or the values.
    5. **the reason is** :data:`~larkdocio.base.plan.Refusal.API_ERROR` — every other reason
       (a scope denial, a rate limit, a transport failure, …) already carries its own TRUE
       disclosure, and overwriting one with this would be a downgrade.
    6. **every entry's table id was VOUCHED FOR** by this run's read side — the strongest clause
       and the one that makes the claim defensible. No vouch set ⇒ **no claim**.
    """
    attempts = tuple(attempts)
    if len(attempts) < PLATFORM_ANOMALY_MIN_ATTEMPTS:                 # (1)
        return None
    if any(attempt.reason is None for attempt in attempts):          # (2)
        return None
    if any(attempt.reason != Refusal.API_ERROR for attempt in attempts):   # (5)
        return None
    codes = {attempt.code for attempt in attempts}                   # (3)
    if len(codes) != 1:
        return None
    (code,) = codes
    if code is None:
        return None
    if code in SYSTEMIC_CODES or code in ENTRY_SCOPED_CODES:         # (4)
        return None
    vouched = frozenset(vouched_table_ids or ())                     # (6)
    if not vouched:
        return None
    if any(attempt.table_id is None or attempt.table_id not in vouched
           for attempt in attempts):
        return None

    table_ids = tuple(sorted({attempt.table_id for attempt in attempts}, key=str))
    observed = _PLATFORM_ANOMALY_OBSERVED.format(
        n=len(attempts), code=code, table_ids=", ".join(str(t) for t in table_ids))
    return PlatformAnomaly(
        code=code, entries=len(attempts), table_ids=table_ids,
        positions=tuple(attempt.position for attempt in attempts),
        disclosure=f"{observed} {PLATFORM_ANOMALY_NOT_YOUR_PLAN}")


def disposition_refusal(disposition: Disposition, exc, *, where: str,
                        wrote_seams=()) -> Refusal:
    """The typed :class:`~larkdocio.base.plan.Refusal` for a classified failure.

    ``where`` names the call (its kind + its table + the records riding in it) so the detail is
    actionable without cross-referencing the plan. Every detail is non-empty — a typed reason
    with no WHY is a riddle.

    The formatting skeleton is the shared
    :func:`~larkdocio.common.disposition.disposition_detail` (LD-533); the TEMPLATES it formats
    are this surface's own, and so is the ``aftermath`` sentence they name — which is why it is
    passed as ``extra`` rather than known to the core.
    """
    detail = disposition_detail(
        disposition, exc, where=where, wrote_seams=wrote_seams,
        templates=_DETAIL_TEMPLATES, fallback=_DETAIL_FALLBACK,
        extra={"aftermath": _HALTED if disposition.halts else _CONTINUED},
    )
    # The protected-last floors carry their repair, appended AFTER the formatting so a
    # sentence with a brace in it can never break the one path that must not raise.
    advice = protected_last_advice(_code_of(exc))
    if advice:
        detail = f"{detail} {advice}"
    return Refusal(reason=disposition.reason, detail=detail)
