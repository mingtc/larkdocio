"""larkdocio.base.schema_settle — the BOUNDED SETTLE CONTRACT for the one async Base op.

**Copy is the only non-synchronous Base operation found anywhere in three probe packs.**
``POST …/apps/{a}/copy`` answers ``code:0`` with a new ``app_token`` and an **empty**
``default_table_id``; an immediate ``GET /apps/{new}`` answers ``1254036 "Bitable is copying,
please try again later."``; ~1.2 s later the app reads cleanly, both tables present with the
right names and all four fields — the ``type:19`` Lookup among them
(``tests/captures/base-study/captures/p1-q4-02-copy.json``, in the source repository).

**But SETTLED IS NOT MATERIALISED.** Reading cleanly means the copied **app is readable**; it
does *not* mean a mirrored or computed column has recomputed. Whether a Lookup's values are
there the instant the settle returns is a **race** LD-284 measured over five copies — the
window, its replication counts and the capture live in ``BASE.md`` register row **40**, cited
here and never restated — and a caller who needs those values must **re-read**.

**That is a new error CLASS, not a new error.** ``1254036`` is not something the caller retries
by hand and it is not a failure: it is the server saying *"ask again"*. So this module gives it
its own vocabulary — an **async-settle** class — and the op **settles** rather than sleeping.

**A fixed sleep is a defect.** It fails on a Base large enough to take longer and wastes time on
every Base that is already there. The loop here is therefore driven by **the response**:

* it probes, and **returns the moment the probe answers** — a copy that is already readable
  costs one call and no wait at all, which a fixed sleep could not do;
* it waits **between** attempts only, at the gentle spacing the three packs sustained (≥1.2 s
  across 483 live calls with no limit met), never before the first and never after the last;
* the budget is **bounded** and refuses to be unbounded — a poll with no ceiling is a hang
  wearing a loop's clothes;
* a code that is **not** ``1254036`` is a real failure and propagates typed. Waiting for a
  ``NOTEXIST`` to become a Base would be waiting for something that is not going to happen.

The wait itself is an **injected callable**, so the loop's shape is observable in a test without
a test ever waiting.
"""
import time as _time
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from larkdocio.base.errors import BASE_ERROR_CODES, note_for
from larkdocio.errors import LarkAPIError

#: Lark's own code for *"this Base is still being copied"*. Observed exactly once, on exactly
#: one operation, in three probe packs.
SETTLING_CODE = 1254036

#: The async-settle class. A tuple because it is a **class** — if Lark ever answers a second
#: code the same way, it joins this set rather than growing a second branch.
ASYNC_SETTLE_CODES: Tuple[int, ...] = (SETTLING_CODE,)

#: The spacing between probes. The pace the three probe packs actually sustained; not a number
#: read off a doc page, and deliberately not tuned downwards, because rate limits were
#: **deliberately not probed** (the LD-100 posture).
DEFAULT_SETTLE_SPACING_SECONDS = 1.2

#: The attempt ceiling. Ten probes at 1.2 s is a ~11 s budget — an order of magnitude more than
#: the ~1.2 s the one captured copy actually needed, and still bounded. A copy that has not
#: settled by then is **reported**, not waited on forever.
DEFAULT_SETTLE_ATTEMPTS = 10

#: The op settled: the probe answered.
SETTLED = "settled"
#: The budget was exhausted while the server was still copying. **Not a failure** — the copy
#: exists and is very likely fine; what is unknown is whether it is readable *yet*.
NOT_SETTLED = "not-settled"

#: **The contract, authored once.** Quoted by the plan, the apply-log and, in the source repository,
#: ``BASE.md``, so the three cannot drift — and worded so nobody reads it as a guarantee about
#: duration.
ASYNC_SETTLE_CONTRACT = (
    "Copying a Base is ASYNCHRONOUS — the only non-synchronous Base operation this library "
    "has found. The copy answers with a new app_token before the Base exists: an immediate "
    "read of it answers `1254036 \"Bitable is copying, please try again later.\"`, which is an "
    "ASYNC-SETTLE class rather than an error the caller retries by hand, and rather than a "
    "failure. larkdocio settles it with a BOUNDED, RESPONSE-DRIVEN poll: it reads the new "
    "Base, waits the gentle spacing only BETWEEN attempts, and stops the moment the read "
    "answers — a copy that is already readable costs one call and no wait. A FIXED SLEEP "
    "WOULD BE A DEFECT: it would fail on a Base large enough to take longer and waste time on "
    "every Base that is already there. The budget has a ceiling, so a copy that has not "
    "settled is REPORTED with how many times it was asked and what it answered; the copy is "
    "not abandoned and not deleted, it is simply not yet readable, and the same settle can be "
    "asked again."
)


def settle_note():
    """The landed taxonomy row for :data:`SETTLING_CODE`.

    The meaning of ``1254036`` is authored by the error taxonomy; this module ships the
    **operation**, not a second definition of the code, so it reads the row rather than
    restating it.
    """
    return BASE_ERROR_CODES[SETTLING_CODE]


@dataclass(frozen=True)
class SettleOutcome:
    """How an asynchronous op settled — and what it cost to find out.

    ``value`` is the probe's own answer on a settle (and ``None`` otherwise). It is deliberately
    **not** in :meth:`to_dict`: the disclosure is about *how it settled*, and a whole app or
    table listing pasted into a plan entry would bury it.
    """

    status: str
    attempts: int
    codes: Tuple[int, ...] = ()
    value: Any = None
    detail: str = ""

    @property
    def settled(self) -> bool:
        return self.status == SETTLED

    def to_dict(self) -> dict:
        return {
            "asynchronous": True,
            "status": self.status,
            "attempts": self.attempts,
            "codes": list(self.codes),
            "detail": self.detail,
            "contract": ASYNC_SETTLE_CONTRACT,
        }


def is_settling(exc: BaseException) -> bool:
    """``True`` when this exception is the server saying *"ask again"*, not *"no"*."""
    return isinstance(exc, LarkAPIError) and exc.code in ASYNC_SETTLE_CODES


def settle(probe,
           *,
           attempts: Optional[int] = DEFAULT_SETTLE_ATTEMPTS,
           spacing: float = DEFAULT_SETTLE_SPACING_SECONDS,
           sleep=None) -> SettleOutcome:
    """Poll ``probe`` until it answers, or until the bounded budget is spent.

    ``probe`` is a zero-argument callable that either **returns** (the op has settled) or
    **raises** the typed ``1254036`` (still settling). Any other exception is a real failure and
    propagates — this loop waits for a copy to finish, not for a wrong token to become right.

    ``sleep`` is the wait, injected. The default is the real one; a test supplies a recorder and
    observes the loop's shape without waiting.
    """
    if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1:
        raise ValueError(
            "settle() needs a bounded attempt budget of at least 1: a poll with no ceiling is "
            f"a hang wearing a loop's clothes; got {attempts!r}.")
    waiter = sleep if sleep is not None else _time.sleep

    codes = []
    for attempt in range(1, attempts + 1):
        try:
            value = probe()
        except LarkAPIError as exc:
            if not is_settling(exc):
                raise
            codes.append(exc.code)
            if attempt < attempts:
                waiter(spacing)
            continue
        return SettleOutcome(
            status=SETTLED, attempts=attempt, codes=tuple(codes), value=value,
            detail=(
                f"the operation settled on attempt {attempt} of {attempts}, after "
                f"{len(codes)} `{SETTLING_CODE}` answer(s) at {spacing}s spacing. "
                f"{ASYNC_SETTLE_CONTRACT}"))

    note = note_for(SETTLING_CODE)
    return SettleOutcome(
        status=NOT_SETTLED, attempts=attempts, codes=tuple(codes), value=None,
        detail=(
            f"the operation had NOT settled after {attempts} attempt(s) at {spacing}s "
            f"spacing — every one answered `{SETTLING_CODE}`"
            + (f" ({note.label})" if note is not None else "")
            + ". This is NOT a failure and NOT a refusal: the copy exists, it is simply not "
              "readable yet, and asking again is the whole cure. Nothing was deleted and "
              "nothing was retried blindly. " + ASYNC_SETTLE_CONTRACT))


__all__ = [
    "ASYNC_SETTLE_CODES",
    "ASYNC_SETTLE_CONTRACT",
    "DEFAULT_SETTLE_ATTEMPTS",
    "DEFAULT_SETTLE_SPACING_SECONDS",
    "NOT_SETTLED",
    "SETTLED",
    "SETTLING_CODE",
    "SettleOutcome",
    "is_settling",
    "settle",
    "settle_note",
]
