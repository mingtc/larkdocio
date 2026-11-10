"""larkdocio.sheets.disposition — the apply-time DISPOSITION BOUNDARY (LD-148).

**The invariant this module exists to make structural: no exception escapes
:func:`~larkdocio.sheets.write_apply.apply`, and EVERY entry ends in a typed, logged
disposition.**

Dogfood round 2 (**T27**, the Blocker) found the hole. The engine typed every failure it
*modelled* — a rich-cell target, an unknown tab, staleness, a precondition mismatch — but the
client call itself sat **outside** any ``try``/``except``, so a raw
``LarkAPIError: Code 90204, Msg: id not found`` from a nonexistent @mention **escaped the
per-entry loop mid-batch**: the entries before it had landed, the ones after it never ran, and
**no disposition was recorded for any of them**. A partially-applied batch with no record of
what happened has no consumer-side recovery path, and it breaks the apply-log completeness
that ``removed_payload`` / undo and every disclosure claim rest on.

This module supplies the two things the boundary needs — the first **shared** with the Base
write engine since LD-533, the second emphatically its own:

* :class:`WriteWatch` — a per-entry proxy over the client that records whether a **write**
  seam actually ran and returned. Without it the boundary could only guess whether a failure
  left the spreadsheet untouched, and a log that guesses is a log that lies: a post-write
  ``revision`` read-back that fails must NOT be reported as "nothing landed". **The mechanism
  lives once**, in the leaf :mod:`larkdocio.common.disposition`; this module binds only its
  default seam set (:data:`WRITE_SEAMS`). Before LD-533 there were two copies of it, and they
  had drifted: the Base copy had grown the ``seams`` parameter this one lacked, and this one
  carried the fuller account of the hazards ``safe_denial`` handles.
* :func:`classify_apply_exception` — the ONE classification table mapping an exception (plus
  that write-watch answer) to a :class:`Disposition`: its **scope** (entry-scoped ⇒ the batch
  continues, systemic ⇒ the batch halts), its typed :class:`~larkdocio.sheets.plan.Refusal`
  reason, its apply-log ``outcome``, and whether the change **landed**. **NOT shared, and not
  a candidate:** these rows encode measured sheets semantics and the Base rows are ruled
  separately, so the two tables differ on purpose.

**The scope split, and why it falls where it does.** The seam is *who judged the call*:

* **Lark answered** (a :class:`~larkdocio.errors.LarkAPIError` carrying a ``code``) ⇒ the
  request reached Lark and Lark judged **this entry**. That is **entry-scoped**: the entry
  refuses ``api-error`` and the batch **CONTINUES** to the remaining entries, each judged
  afresh with its own compare-and-swap and its own disposition — the **maintainer-blessed sheets
  per-entry doctrine** (per-entry compare-and-swap, partial application possible on refusals,
  fully disclosed in the apply-log; docx keeps whole-batch-zero-writes). Continuing is also
  strictly *more* informative than halting **where the blast radius is not knowable**: an
  error that *might* be batch-wide produces N logged refusals instead of one crash, and each
  refusal is honest. That reasoning survives exactly there and no further — a failure whose
  batch-wideness IS knowable halts instead (the scope denial below is the one such case, and
  the only reason it can be told apart from an ordinary per-entry rejection is that it arrives
  typed rather than as a string to match).
* **The app lacks a SCOPE** (:class:`~larkdocio.errors.LarkPermissionError`, a *coded*
  ``LarkAPIError`` subclass — so this arm MUST precede the coded arm above) ⇒ **systemic**.
  Lark answered, but it answered about the **app**, not about this entry: a missing grant
  would refuse every remaining entry identically, so continuing would spend one throttled
  write call per entry on a condition that cannot clear between them and report N
  unrelated-looking refusals where one statement of one condition is the truth. The batch
  **HALTS**, the remainder is logged ``not-attempted``, and the halt detail relays **Lark's
  own** answer — the missing scope(s), its verbatim ``code``/``msg``, the console link when
  Lark supplied one, and which credential pair made the call. The repair is a console grant;
  this library never requests, widens or escalates a scope.
* **Lark said slow down** (:class:`~larkdocio.errors.LarkRateLimitError`, ``99991400``,
  surviving the write transport's own backoff-and-retry) or **the call never reached Lark**
  (a ``URLError``, which the transport surfaces as a ``LarkAPIError`` with **no ``code``**), or
  **something un-modelled raised at all** ⇒ **systemic**. The batch **HALTS** and every
  remaining entry is logged ``not-attempted``.
* **The write already returned** ⇒ systemic regardless of the exception's own class, because
  the compare-and-swap anchor is now *unknown*: continuing would judge every later entry
  against a ``revision`` the engine can no longer trust and manufacture bogus ``STALE_SHEET``
  refusals. The entry is logged ``applied-unverified`` (the change **is** on the spreadsheet).

**The deliberate ``BaseException`` carve-out.** The boundary catches :class:`Exception`, not
:class:`BaseException` — a ``KeyboardInterrupt`` / ``SystemExit`` / ``MemoryError`` is the
interpreter or the operator tearing the process down, and swallowing it into a log entry would
be a *worse* bug than the one this module fixes. That carve-out is pinned by a test, not left
to be rediscovered.
"""
# LD-533 — the ONE disposition-boundary core. Re-exported under this module's own historical
# names (`_safe_text`, `_safe_denial`, `_DENIAL_*`) because THIS is their public path: every
# call site and every test that imported them from here still resolves.
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
from larkdocio.sheets.plan import Refusal

# --------------------------------------------------------------------------- #
# Disposition scope                                                             #
# --------------------------------------------------------------------------- #
#
# `ENTRY_SCOPED` / `SYSTEMIC` are imported above rather than assigned here. The two values
# were already byte-identical to the Base copy (measured, LD-533), and the reason THIS module
# gave for them is kept: the failure is attributable to **this entry**, so it refuses and the
# batch keeps going — the sheets per-entry doctrine; a systemic failure is not entry-local, or
# its blast radius is unknown, so the batch halts and every remaining entry is logged
# ``not-attempted``. The vocabulary is shared; the table that sorts into it is not.


# --------------------------------------------------------------------------- #
# The client seam, split by whether a call MUTATES the spreadsheet               #
# --------------------------------------------------------------------------- #

#: Every duck-typed client method that **mutates** the spreadsheet. The write-watch keys on
#: this set, so a method missing from it would make the engine claim "nothing landed" about a
#: call that landed something — the reason
#: ``tests/test_apply_disposition_invariant.py`` pins it against
#: :class:`~larkdocio.sheets.write_client.SheetsWriteClient`'s real public surface (a new
#: write op that forgets to register here reddens the suite).
WRITE_SEAMS = frozenset({
    "put_values",
    "batch_update_values",
    "append_values",
    "prepend_values",
    "set_data_validation",
    "put_style",
    "batch_update_styles",
    "insert_dimension_range",
    "delete_dimension_range",
    "append_dimension",
    "set_dimension_properties",
    "merge_cells",
    "unmerge_cells",
    "batch_update_sheets",
    # LD-447 — the IN-CELL IMAGE write. Declared here because it MUTATES (it stores a
    # picture as a cell's value and mints a permanent media token doing it), even though
    # the apply engine never calls it: the op that does is a leg beside the engine, not a
    # plan entry. Declaring it keeps the read/write/lifecycle split over the client surface
    # exhaustive, which is what the invariant test actually checks.
    "put_values_image",
    # LD-448 — the FLOAT IMAGE bind and its delete. Declared for the same reason: both
    # MUTATE (one anchors a picture over a range, the other removes the anchor) while the
    # apply engine calls neither — the ops that do are legs beside it. `create_float_image`
    # additionally mints nothing itself: the permanent media token is the upload leg's, on
    # the media client, which is not a seam on this client at all.
    "create_float_image",
    "delete_float_image",
})

#: The client's **file-lifecycle** calls — create / trash the whole spreadsheet FILE. A third
#: category, not a widening of :data:`WRITE_SEAMS`, and the distinction is a claim about what
#: the engine does: the write-watch proxies a WRITE seam to decide whether **a plan entry's**
#: change landed, and a workbook create/delete is never a plan entry. The apply engine calls
#: neither (pinned in ``tests/test_apply_disposition_invariant.py``) — creating or trashing a
#: workbook is a caller's own explicit act, never a side effect of applying a plan. Declared
#: here so the read/write/lifecycle split over the client surface stays **exhaustive** and
#: provably so.
FILE_LIFECYCLE_SEAMS = frozenset({
    "create_spreadsheet",
    "delete_spreadsheet",
})

#: Every duck-typed client method the engine calls that **only reads** (the compare-and-swap
#: anchor, the before-snapshot / precondition, the mandatory geometry re-read, the tab
#: listing, the plan-time @mention id check). Declared so the write/read split over the
#: client surface is **exhaustive** and provably so.
READ_SEAMS = frozenset({
    "read_revision",
    "read_values",
    "read_sheet_geometry",
    "query_tabs",
    "validate_user_ids",
    # LD-186 — the `metainfo` frozen read: the freeze family's plan-time read AND its
    # post-write verification leg. A READ seam, deliberately: it mutates nothing, and freeze
    # itself adds NO write seam because it rides the already-declared `batch_update_sheets`.
    "read_frozen_panes",
    # LD-447 — the whole-`valueRange` read (range + revision + values). A READ seam: it is
    # the VERDICT read the in-cell image write rides, and `read_values` is now its matrix
    # half, so the two are one call with two shapes rather than two implementations.
    "read_value_range",
    # LD-448 — the tab's float images. A READ seam: it mutates nothing, and it is THE
    # VERDICT read of the float-image route (for the bind and for the removal alike), which
    # is the whole reason a call's own `code 0` is never believed on that route.
    "query_float_images",
})


class SheetsWriteWatch(_SharedWriteWatch):
    """The shared :class:`~larkdocio.common.disposition.WriteWatch`, defaulted to
    :data:`WRITE_SEAMS`.

    **Its only content is that default** — the watching mechanism (the forwarding
    ``__getattr__``, the issued/completed accounting, the ``wrote`` answer) is authored ONCE, in
    the shared core, and this class adds not one line of it. Wrapping the client rather than
    threading a journal through the op legs is still what keeps the legs untouched: the
    boundary is one seam, and the legs cannot forget to report.

    **The one mechanical change when the two copies became one class:** the seam set is now
    read from the *instance* (the core's ``seams``) rather than from this module's global
    :data:`WRITE_SEAMS`. For every construction in this tree the set is the same set, so the
    behaviour is the same; what changed is that a watch built with an explicit ``seams=``
    honours it here too.
    """

    __slots__ = ()

    #: The sheets write seams — hand-kept, and pinned against the write client's real public
    #: surface by the invariant suite (see :data:`WRITE_SEAMS`).
    DEFAULT_SEAMS = WRITE_SEAMS


# LD-533 — this module's public path for the watch. Unchanged for every caller and every
# test: `from larkdocio.sheets.disposition import WriteWatch` still resolves, and
# `WriteWatch(client)` still watches exactly the sheets write seams.
WriteWatch = SheetsWriteWatch


# --------------------------------------------------------------------------- #
# Disposition — one exception → one typed, logged outcome                       #
# --------------------------------------------------------------------------- #
#
# :class:`Disposition` is imported from the shared core above. Its fields and its
# halts/continues accessors were already byte-identical to the Base copy (measured, LD-533);
# what this module's own docstring added — that ``reason`` is a
# :class:`~larkdocio.sheets.plan.Refusal` constant, that ``outcome`` is one of
# ``refused`` / ``failed`` / ``applied-unverified``, and that ``landed``'s honest third value
# is why ``failed`` is not called a refusal — is preserved at the new address. The ROWS below
# are this surface's alone.


#: The classification table, most-specific first. ``LarkRateLimitError`` and
#: ``LarkPermissionError`` must both precede ``LarkAPIError`` (both are subclasses, and both
#: carry a ``code``, so a base-class test placed first would swallow them), and the
#: coded/uncoded ``LarkAPIError`` split is the transport's own signal:
#: ``raise_for_lark_code`` always attaches Lark's ``code``, while the ``URLError`` wrap in
#: ``common.transport.RawHttpClient._send`` cannot.
_UNVERIFIED = Disposition(SYSTEMIC, Refusal.UNVERIFIED_WRITE, "applied-unverified", "yes")
_RATE_LIMITED = Disposition(SYSTEMIC, Refusal.RATE_LIMITED, "refused", "no")
#: LD-206 — a scope denial is the one coded failure whose batch-wideness is KNOWABLE.
_PERMISSION_DENIED = Disposition(SYSTEMIC, Refusal.PERMISSION_DENIED, "refused", "no")
_API_ERROR = Disposition(ENTRY_SCOPED, Refusal.API_ERROR, "refused", "no")
_TRANSPORT = Disposition(SYSTEMIC, Refusal.TRANSPORT_FAILURE, "failed", "indeterminate")
_INVALID_REQUEST = Disposition(ENTRY_SCOPED, Refusal.INVALID_REQUEST, "refused", "no")
_UNEXPECTED = Disposition(SYSTEMIC, Refusal.UNEXPECTED_ERROR, "failed", "indeterminate")


def classify_apply_exception(exc, *, wrote: bool) -> Disposition:
    """Classify ONE exception raised by a per-entry apply step into a :class:`Disposition`.

    ``wrote`` is :attr:`WriteWatch.wrote` for that entry — whether a write seam **returned**
    before the exception. It is checked FIRST and overrides the exception's own class: once
    the change is on the spreadsheet the only truthful record is ``applied-unverified``, and
    the batch must halt because the compare-and-swap anchor is no longer known.

    Total by construction — the final ``else`` catches every exception type, including ones
    this library never raises — so there is no exception a caller can provoke that lacks a
    disposition.
    """
    if wrote:
        return _UNVERIFIED
    if isinstance(exc, LarkRateLimitError):
        return _RATE_LIMITED
    if isinstance(exc, LarkPermissionError):
        # BEFORE the `LarkAPIError` arm, deliberately: this is a coded subclass of it, so the
        # generic arm below would otherwise claim it and call a missing grant entry-scoped.
        return _PERMISSION_DENIED
    if isinstance(exc, LarkAPIError):
        # A `code` means Lark itself answered → the failure is about THIS entry.
        # No `code` means the call never got an answer (the URLError wrap) → systemic and
        # INDETERMINATE.
        return _API_ERROR if exc.code is not None else _TRANSPORT
    if isinstance(exc, LarkConfigError):
        return _INVALID_REQUEST
    return _UNEXPECTED


#: Human-readable, actionable per-reason wording for a disposition's ``detail``. Each states
#: (a) what failed, (b) whether the spreadsheet changed, and (c) what the batch did — the
#: three questions a consumer reading an apply-log actually has.
_DETAIL_TEMPLATES = {
    Refusal.API_ERROR: (
        "Lark rejected this entry ({where}): {exc}. NOTHING landed for this entry. The batch "
        "CONTINUED — an entry-scoped API error refuses only its own entry and every remaining "
        "entry is still processed with its own guards and its own disposition (the sheets "
        "per-entry doctrine). Lark code={code!r} msg={msg!r}."
    ),
    Refusal.INVALID_REQUEST: (
        "this entry could not be turned into a valid request ({where}): {exc}. No call was "
        "made and NOTHING landed. The batch CONTINUED with the remaining entries."
    ),
    Refusal.PERMISSION_DENIED: (
        "Lark refused this entry because the app lacks a required SCOPE ({where}): {exc}. "
        "NOTHING landed for this entry. The batch HALTED and every remaining entry is logged "
        "not-attempted, because a missing grant is batch-wide by construction — it would "
        "refuse every later entry the same way, so continuing would spend one throttled write "
        "call per entry on a condition that cannot clear between them and report N "
        "unrelated-looking refusals where there is one condition. REPAIR: grant the "
        "permission(s) named below on the app in the Lark console — a grant is an "
        "administrator's console action, and this library never requests, widens or escalates "
        "a scope — then re-run dry_run and apply the remainder (the sheet may have moved "
        "meanwhile). Lark code={code!r} msg={msg!r}. {denial}"
    ),
    Refusal.RATE_LIMITED: (
        "Lark's rate limit (99991400) survived the write transport's backoff-and-retry "
        "({where}): {exc}. NOTHING landed for this entry. The batch HALTED — every remaining "
        "entry is logged not-attempted rather than hammering a throttled endpoint. Retry the "
        "remainder later (re-run dry_run first: the sheet may have moved)."
    ),
    Refusal.TRANSPORT_FAILURE: (
        "the call failed BELOW Lark ({where}): {exc}. Whether this entry's write landed is "
        "INDETERMINATE — the request may or may not have reached Lark, and the engine will not "
        "guess. The batch HALTED. RECONCILE THIS ENTRY BY READING THE SHEET before re-applying "
        "it, then re-plan the remainder."
    ),
    Refusal.UNEXPECTED_ERROR: (
        "an unexpected {exc_type} escaped this entry's apply step ({where}): {exc}. It is "
        "recorded as an entry rather than thrown as a traceback — no Lark error, rate limit, "
        "transport failure or library bug escapes apply() untyped — but its blast radius is "
        "unknown, so whether the write landed is INDETERMINATE and the batch HALTED. "
        "RECONCILE THIS ENTRY BY READING THE SHEET, and please report the traceback."
    ),
    Refusal.UNVERIFIED_WRITE: (
        "this entry's write ({wrote_seams}) RETURNED — the change IS on the spreadsheet — but "
        "a post-write step then failed ({where}): {exc}. The write is therefore recorded as "
        "applied-unverified: applied, with an INCOMPLETE verification record (no post-write "
        "revision, and no geometry/merge re-read where the op has one). The batch HALTED "
        "because the compare-and-swap anchor is now unknown; re-read the sheet and re-plan the "
        "remainder."
    ),
}


#: The last-resort wording, used only if a future :class:`Disposition` reason arrives without
#: its own template. Present because this code runs **inside** the boundary that must never
#: raise: a ``KeyError`` here would re-open the exact hole LD-148 closes.
_DETAIL_FALLBACK = (
    "this entry's apply step failed ({where}) with {exc_type}: {exc}. Recorded as "
    "'{reason}' — it became a typed entry rather than a traceback out of apply(). Whether "
    "the write landed: {landed}."
)


#
# `_safe_text`, `_safe_denial`, `_DENIAL_ABSENT` and `_DENIAL_UNRENDERABLE` are imported from
# the shared core at the top of this module, under these same private names, because these are
# their addresses here. Measured at LD-533: the two paragraphs were already byte-identical to
# the Base copies (202 and 170 characters) and both helper BODIES were identical too — the
# only difference was that THIS module documented them more fully, and that fuller account is
# the one that travelled to the core (the three hazards `_safe_denial` handles, and the
# defense-in-depth reason `_safe_text` exists). So the words a consumer reads did not change
# on either surface: there was no hardening to adopt, only prose to keep.


def disposition_refusal(disposition: Disposition, exc, *, where: str,
                        wrote_seams=()) -> Refusal:
    """The typed :class:`~larkdocio.sheets.plan.Refusal` for a classified failure.

    ``where`` names the entry (its op family + target) so the detail is actionable without
    cross-referencing the plan; ``wrote_seams`` names the write seam(s) that already returned
    (the ``applied-unverified`` case). Every detail is non-empty — the LD-131
    mandatory-detail discipline: a typed reason with no WHY is a riddle.

    The formatting skeleton is the shared
    :func:`~larkdocio.common.disposition.disposition_detail` (LD-533); the TEMPLATES it formats
    are this surface's own, and this surface names no ``extra`` field.
    """
    detail = disposition_detail(
        disposition, exc, where=where, wrote_seams=wrote_seams,
        templates=_DETAIL_TEMPLATES, fallback=_DETAIL_FALLBACK,
    )
    return Refusal(reason=disposition.reason, detail=detail)
