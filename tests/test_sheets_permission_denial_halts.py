"""LD-206 — a sheets batch HALTS on an un-clearable SCOPE DENIAL (maintainer ruling 2026-08-01).

The bug LD-148's own module docstring anticipated and accepted: the entry-scoped/systemic
split was written against *"who judged the call"* — Lark answered with a ``code`` ⇒ this
entry — and a **scope denial answers with a code** (``99991672``). So a denial landed on
``_API_ERROR`` = entry-scoped, and a 20-entry batch spent **20** throttled write calls on a
condition that structurally cannot clear between entries, reporting twenty independent
per-entry refusals where one systemic statement would do.

That proxy is right for ``90204 id-not-found`` and wrong for ``99991672``: a missing grant is
**knowably** batch-wide. Until the typed :class:`~larkdocio.errors.LarkPermissionError`
shipped there was no way to tell the two apart without string-matching Lark's message; now
there is, and the maintainer ruled **HALT** — reversing the deliberate "N logged refusals beats one
crash" choice for this one failure class, and only for it.

The offline anchor is a **committed real denial body** — no credentials, no live call:
``tests/captures/permissions-preflight-probe/captures/Q12-group-bogus-READ.json``, a genuine
``99991672`` answer complete with ``permission_violations`` and Lark's own console link. A
real mid-batch ``99991672`` cannot be provoked without revoking a scope in the Lark console,
which this library never does, so the arm is proven from the capture.
"""
import json
import pathlib

import pytest

from log_reading_apply import reading_the_log
from larkdocio.common import transport
from larkdocio.errors import (
    LarkAPIError,
    LarkConfigError,
    LarkPermissionError,
    LarkRateLimitError,
)
from larkdocio.sheets import disposition as D
from larkdocio.sheets.disposition import (
    ENTRY_SCOPED,
    SYSTEMIC,
    classify_apply_exception,
    disposition_refusal,
)
from larkdocio.sheets.write_apply import Refusal, ValueWriteRequest, apply, dry_run
apply = reading_the_log(apply)

from test_apply_disposition_invariant import (
    SID,
    TOKEN,
    InjectingGateway,
    _api_90204,
    _fresh_gateway,
)

CAPTURE = (pathlib.Path(__file__).resolve().parent.parent
           / "tests" / "captures" / "permissions-preflight-probe" / "captures"
           / "Q12-group-bogus-READ.json")


def _captured_denial_body() -> dict:
    """The committed real ``99991672`` response body — the whole offline anchor."""
    return json.loads(CAPTURE.read_text(encoding="utf-8"))["response"]


def _denial_exc(*, credential_env=("LARK_WRITE_APP_ID", "LARK_WRITE_APP_SECRET")):
    """The exception a sheets write step raises on the captured denial, verbatim.

    Built the way the shipped write client builds it — through
    ``common.transport.raise_for_lark_code`` — so the test cannot drift from the real seam.
    """
    try:
        transport.raise_for_lark_code(_captured_denial_body(),
                                      context="sheets write step",
                                      credential_env=credential_env)
    except LarkPermissionError as exc:
        return exc
    raise AssertionError("the captured body must raise LarkPermissionError")


# =========================================================================== #
# AC1 — the classification arm, ORDERED most-specific-first.                    #
# =========================================================================== #

def test_ac1_the_captured_denial_classifies_systemic_and_halts():
    """The reproduction steps, verbatim: the committed capture through
    ``raise_for_lark_code`` → ``classify_apply_exception(exc, wrote=False)``.

    Before the fix this printed ``entry-scoped api-error False True``."""
    exc = _denial_exc()
    assert isinstance(exc, LarkAPIError), "the subclass must not break existing handling"
    assert exc.code == 99991672

    d = classify_apply_exception(exc, wrote=False)
    assert d.scope == SYSTEMIC
    assert d.reason == Refusal.PERMISSION_DENIED
    assert d.outcome == "refused"
    assert d.landed == "no"
    assert d.halts is True
    assert d.continues is False


def test_ac1_the_permission_arm_precedes_the_generic_api_error_arm():
    """A source-order guard: ``LarkPermissionError`` is a **coded** ``LarkAPIError``
    subclass, so a table that tests the base class first can never reach the specific arm —
    the same ordering discipline ``LarkRateLimitError`` already depends on. An arm reordered
    below the base class reddens here even if no classification test happens to notice."""
    import inspect

    src = inspect.getsource(classify_apply_exception)
    positions = {name: src.index(name) for name in
                 ("LarkRateLimitError", "LarkPermissionError", "LarkAPIError")}
    assert positions["LarkPermissionError"] < positions["LarkAPIError"], (
        "the LarkPermissionError arm must precede the LarkAPIError arm — it is a subclass")


# =========================================================================== #
# AC2 — the ``wrote=True`` precedence is UNCHANGED.                             #
# =========================================================================== #

@pytest.mark.parametrize("wrote,expected_reason,expected_outcome,expected_landed", [
    (False, Refusal.PERMISSION_DENIED, "refused", "no"),
    (True, Refusal.UNVERIFIED_WRITE, "applied-unverified", "yes"),
])
def test_ac2_a_completed_write_still_outranks_the_denial(
        wrote, expected_reason, expected_outcome, expected_landed):
    """"The change is on the spreadsheet" outranks "why the next call failed".

    A denial raised by a **post-write** step (the ``revision`` read-back, the geometry
    re-read) must stay ``unverified-write`` — reclassifying it ``permission-denied`` would
    report "nothing landed" about a write that landed."""
    d = classify_apply_exception(_denial_exc(), wrote=wrote)
    assert d.reason == expected_reason
    assert d.outcome == expected_outcome
    assert d.landed == expected_landed
    assert d.halts is True          # both arms halt, for different reasons


# =========================================================================== #
# AC3 — one new typed reason, nothing renamed.                                  #
# =========================================================================== #

def test_ac3_the_new_reason_is_its_own_name_distinct_from_every_older_one():
    assert Refusal.PERMISSION_DENIED == "permission-denied"
    older = {v for k, v in vars(Refusal).items()
             if k.isupper() and isinstance(v, str) and k != "PERMISSION_DENIED"}
    assert Refusal.PERMISSION_DENIED not in older
    # …and every older name still means what it meant (nothing renamed).
    assert Refusal.API_ERROR == "api-error"
    assert Refusal.RATE_LIMITED == "rate-limited"
    assert Refusal.TRANSPORT_FAILURE == "transport-failure"
    assert Refusal.UNEXPECTED_ERROR == "unexpected-error"
    assert Refusal.UNVERIFIED_WRITE == "unverified-write"
    assert Refusal.NOT_ATTEMPTED == "not-attempted"
    assert Refusal.INVALID_REQUEST == "invalid-request"
    assert Refusal.UNKNOWN_MENTION == "unknown-mention"


def test_ac3_the_reason_is_reachable_through_a_factory_that_demands_a_detail():
    refusal = Refusal.permission_denied("d")
    assert refusal.reason == Refusal.PERMISSION_DENIED and refusal.detail
    assert Refusal.from_dict(refusal.to_dict()) == refusal


# =========================================================================== #
# AC4 — the detail template, and it CANNOT raise.                               #
# =========================================================================== #

def test_ac4_the_detail_answers_all_four_questions_and_carries_larks_own_denial():
    refusal = disposition_refusal(D._PERMISSION_DENIED, _denial_exc(),
                                  where="value on s1!A1:A1")
    detail = refusal.detail
    assert refusal.reason == Refusal.PERMISSION_DENIED
    # (a) a scope is missing, and WHICH — relayed from Lark, never invented.
    assert "contact:group:readonly" in detail
    assert "99991672" in detail
    # (b) nothing landed for this entry; (c) the batch halted and the rest is not-attempted.
    assert "NOTHING landed" in detail
    assert "HALTED" in detail
    assert "not-attempted" in detail
    # (d) the repair: a Lark console grant, then re-plan and re-apply the remainder.
    assert "console" in detail
    assert "dry_run" in detail
    # the credential pair the call was made on, and Lark's own console link when it sent one.
    assert "LARK_WRITE_APP_ID" in detail
    assert "https://open.larksuite.com/app/" in detail


def test_ac4_a_permission_error_with_no_denial_body_still_yields_a_detail():
    """``denial`` is optional on the type — a ``LarkPermissionError`` built without a body
    has none. ``getattr(exc, "denial", None)`` can be ``None`` and this code runs INSIDE the
    boundary that must never raise, so the absence is a clause, not an ``AttributeError``."""
    exc = LarkPermissionError("denied: Code: 99991672", code=99991672, msg="Access denied")
    assert exc.denial is None
    refusal = disposition_refusal(D._PERMISSION_DENIED, exc, where="value on s1!A1:A1")
    assert refusal.reason == Refusal.PERMISSION_DENIED
    assert len(refusal.detail) > 60
    assert "HALTED" in refusal.detail
    # nothing is invented in place of the scope Lark did not name here.
    assert "None" not in refusal.detail.split("Lark code=")[0]


def test_ac4_a_denial_whose_detail_explodes_cannot_break_the_boundary():
    """Defense in depth, on the same reasoning as ``_safe_text``: ``denial.detail()`` is
    someone else's code, and an exception escaping here re-opens the exact hole the
    disposition boundary closes."""
    class Explodes:
        def detail(self):
            raise KeyError("scopes")

    exc = LarkPermissionError("denied", code=99991672, msg="Access denied")
    exc.denial = Explodes()
    refusal = disposition_refusal(D._PERMISSION_DENIED, exc, where="value on s1!A1:A1")
    assert refusal.reason == Refusal.PERMISSION_DENIED
    assert len(refusal.detail) > 60
    assert "HALTED" in refusal.detail


def test_ac4_a_denial_attribute_that_itself_raises_cannot_break_the_boundary():
    """The attribute access is guarded too — a property that raises is the same hazard."""
    class Hostile(LarkAPIError):
        code = 99991672
        msg = "Access denied"

        @property
        def denial(self):
            raise RuntimeError("no")

        @denial.setter
        def denial(self, value):
            # The BASE now assigns `self.denial` on every api error, so a read-only property
            # could not be constructed at all. The hazard being modelled is the READ, and it
            # is unchanged: the getter above still raises. The setter only lets the object
            # exist to be read from.
            pass

    exc = Hostile("denied")
    refusal = disposition_refusal(D._PERMISSION_DENIED, exc, where="value on s1!A1:A1")
    assert refusal.detail and "HALTED" in refusal.detail


# =========================================================================== #
# AC5 — observable halt semantics, end to end through apply().                  #
# =========================================================================== #

def _batch(n):
    return [ValueWriteRequest.for_a1(f"{SID}!A{r}:A{r}", [[f"v{r}"]])
            for r in range(1, n + 1)]


def _denied_run(n=5, at=1, exc=None):
    """An ``n``-entry plan whose write at index ``at`` is denied. Returns ``(log, gateway)``."""
    g = _fresh_gateway(inject={"put_values": [None] * at + [exc or _denial_exc()]},
                       user_ids=set())
    plan = dry_run(_batch(n), g, TOKEN)
    assert len(plan.entries) == n and all(e.is_resolved for e in plan.entries)
    log = apply(plan, g)
    assert not g.inject["put_values"], "ANTI-VACUITY: the injected denial never fired"
    return log, g


def test_ac5_the_denial_halts_the_batch_and_the_log_stays_complete():
    n, at = 5, 1
    log, _g = _denied_run(n, at)

    assert len(log.entries) == n                       # the completeness invariant holds
    assert [e.outcome for e in log.entries] == (
        ["applied"] * at + ["refused"] + ["not-attempted"] * (n - at - 1))

    hit = log.entries[at]
    assert hit.refusal.reason == Refusal.PERMISSION_DENIED
    assert "contact:group:readonly" in hit.refusal.detail

    assert log.halted
    assert log.halt == {
        "index": at,
        "reason": Refusal.PERMISSION_DENIED,
        "detail": hit.refusal.detail,
        "landed": "no",
        "not_attempted": n - at - 1,
    }
    assert log.halt["detail"]
    assert len(log.not_attempted) == n - at - 1
    assert log.not_attempted == log.entries[at + 1:]


def test_ac5_the_not_attempted_tail_names_what_stopped_the_batch():
    """Nothing is silently dropped: each tail entry carries the halt index AND the reason,
    so the log alone says why those entries never ran."""
    log, _g = _denied_run(5, 1)
    for entry in log.not_attempted:
        assert entry.refusal.reason == Refusal.NOT_ATTEMPTED
        assert Refusal.PERMISSION_DENIED in entry.refusal.detail
        assert "halted at entry #1" in entry.refusal.detail


def test_ac5_no_exception_escapes_apply_on_a_scope_denial():
    """The LD-148 invariant is not weakened by the new arm — the halt is a logged
    disposition, never a raise."""
    log, _g = _denied_run(3, 0)
    assert log.entries and log.entries[0].outcome == "refused"


# =========================================================================== #
# AC6 — the write-budget payoff, PROVEN by counting calls.                       #
# =========================================================================== #

def test_ac6_a_denied_first_write_costs_exactly_one_write_call():
    """**The whole point of the issue.** An N-entry plan whose first write is denied issues
    exactly ONE write call, not N."""
    n = 8
    log, g = _denied_run(n, 0)
    assert g.calls.count("put_values") == 1, g.calls
    assert log.halt["not_attempted"] == n - 1


def test_ac6_the_entry_scoped_control_still_spends_one_call_per_entry():
    """The contrast that makes the count above mean something: an ordinary entry-scoped
    ``90204`` still costs N calls, because the batch legitimately continues."""
    n = 8
    log, g = _denied_run(n, 0, exc=_api_90204())
    assert g.calls.count("put_values") == n, g.calls
    assert not log.halted
    assert [e.outcome for e in log.entries] == ["refused"] + ["applied"] * (n - 1)


# =========================================================================== #
# AC7 — the rest of the classification table is UNCHANGED.                      #
# =========================================================================== #

@pytest.mark.parametrize("exc,scope,reason", [
    (LarkAPIError("x", code=90204, msg="id not found"), ENTRY_SCOPED, Refusal.API_ERROR),
    (LarkAPIError("x", code=90202, msg="wrong range"), ENTRY_SCOPED, Refusal.API_ERROR),
    (LarkRateLimitError("x", code=99991400), SYSTEMIC, Refusal.RATE_LIMITED),
    (LarkAPIError("no code"), SYSTEMIC, Refusal.TRANSPORT_FAILURE),
    (LarkConfigError("x"), ENTRY_SCOPED, Refusal.INVALID_REQUEST),
    (RuntimeError("x"), SYSTEMIC, Refusal.UNEXPECTED_ERROR),
])
def test_ac7_no_other_arm_was_reclassified(exc, scope, reason):
    d = classify_apply_exception(exc, wrote=False)
    assert (d.scope, d.reason) == (scope, reason)


def test_ac7_a_90204_batch_still_continues_end_to_end():
    """The characterization the ruling deliberately leaves alone: ``90204`` stays
    entry-scoped, so its batch still applies every other entry."""
    g = InjectingGateway(
        revision=7,
        values={f"{SID}!A{r}:A{r}": [[f"slot-{r}"]] for r in range(1, 5)},
        inject={"put_values": [None, _api_90204()]},
        user_ids=set(),
    )
    log = apply(dry_run(_batch(4), g, TOKEN), g)
    assert not log.halted
    assert [e.outcome for e in log.entries] == ["applied", "refused", "applied", "applied"]
