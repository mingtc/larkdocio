"""LD-263 AC2 / AC3 — COPY IS ASYNC AND THE CONTRACT IS A POLL, NOT A SLEEP.

``POST …/apps/{a}/copy`` is the **only** non-synchronous Base operation found in three probe
packs: the new ``app_token`` comes back before the Base exists, an immediate ``GET /apps/{new}``
answers ``1254036 "Bitable is copying, please try again later."``, and ~1.2 s later everything
reads cleanly (``tests/captures/base-study/captures/p1-q4-02-copy.json``).

A fixed ``sleep`` is a **defect**: it fails on a large Base and wastes time on a small one. So
the contract is a **bounded, response-driven poll**, and these tests hold both halves — it does
not return early, and it does not spin unbounded.
"""
import pytest

from larkdocio.base import schema_settle
from larkdocio.base.errors import raise_for_base_code
from larkdocio.errors import LarkAPIError


class _Clock:
    """A sleep that records instead of sleeping — so the loop's shape is observable."""

    def __init__(self):
        self.sleeps = []

    def __call__(self, seconds):
        self.sleeps.append(seconds)


def _copying():
    """The real refusal, raised the way the shipped client raises it."""
    return raise_for_base_code(
        {"code": schema_settle.SETTLING_CODE,
         "msg": "Bitable is copying, please try again later."},
        context="read the copied Base")


def _probe(script):
    """A probe driven by a script of ``'copying'`` / a value to return."""
    calls = []

    def probe():
        calls.append(len(calls))
        step = script[len(calls) - 1] if len(calls) <= len(script) else script[-1]
        if step == "copying":
            _copying()
        return step

    probe.calls = calls
    return probe


# --------------------------------------------------------------------------- #
# The vocabulary                                                               #
# --------------------------------------------------------------------------- #

def test_1254036_is_an_ASYNC_SETTLE_class_not_an_error_and_not_a_failure():
    assert schema_settle.SETTLING_CODE == 1254036
    assert schema_settle.SETTLING_CODE in schema_settle.ASYNC_SETTLE_CODES
    text = schema_settle.ASYNC_SETTLE_CONTRACT.lower()
    assert "1254036" in schema_settle.ASYNC_SETTLE_CONTRACT
    assert "sleep" in text and "bounded" in text


def test_the_code_is_ALREADY_in_the_landed_taxonomy_and_this_module_does_not_re_author_it():
    """LD-255's AC4 shipped ``1254036`` as vocabulary; this story ships the OP. The meaning
    stays authored once."""
    from larkdocio.base.errors import BASE_ERROR_CODES

    assert schema_settle.SETTLING_CODE in BASE_ERROR_CODES
    assert schema_settle.settle_note().code == schema_settle.SETTLING_CODE


def test_the_gentle_spacing_is_the_measured_one_and_the_budget_is_BOUNDED():
    assert schema_settle.DEFAULT_SETTLE_SPACING_SECONDS >= 1.2
    assert 1 < schema_settle.DEFAULT_SETTLE_ATTEMPTS < 100


# --------------------------------------------------------------------------- #
# The loop — driven by the RESPONSE                                            #
# --------------------------------------------------------------------------- #

def test_the_amplifier_case_TWO_1254036s_THEN_code_0_neither_returns_early_nor_spins():
    """The spec's own test-rigor amplifier, verbatim."""
    clock = _Clock()
    probe = _probe(["copying", "copying", "the copy"])

    outcome = schema_settle.settle(probe, sleep=clock)

    assert outcome.settled is True
    assert outcome.value == "the copy"
    assert outcome.attempts == 3, "it did not return early and it did not overshoot"
    assert outcome.codes == (schema_settle.SETTLING_CODE, schema_settle.SETTLING_CODE)
    assert len(probe.calls) == 3
    # One wait BETWEEN attempts, never one before the first and never one after the last.
    assert clock.sleeps == [schema_settle.DEFAULT_SETTLE_SPACING_SECONDS] * 2


def test_A_SETTLED_COPY_COSTS_ONE_PROBE_AND_ZERO_SLEEPS_which_a_fixed_sleep_could_not_do():
    """The falsification of "it is really just a sleep": a Base that is already there is read
    once and waited on not at all."""
    clock = _Clock()
    probe = _probe(["the copy"])

    outcome = schema_settle.settle(probe, sleep=clock)

    assert outcome.settled and outcome.attempts == 1
    assert clock.sleeps == [], "a fixed sleep would show up here as a wait nobody needed"


def test_the_LOOP_LENGTH_TRACKS_THE_RESPONSES_not_the_clock():
    """Three scripts, three lengths, one unchanged budget: the number of calls is a function
    of what the server said, and of nothing else."""
    for copying, expected in ((0, 1), (1, 2), (5, 6)):
        probe = _probe(["copying"] * copying + ["ok"])
        outcome = schema_settle.settle(probe, sleep=_Clock())
        assert outcome.attempts == expected, copying


def test_THE_BUDGET_IS_BOUNDED_a_copy_that_never_settles_STOPS():
    clock = _Clock()
    probe = _probe(["copying"])

    outcome = schema_settle.settle(probe, attempts=4, sleep=clock)

    assert outcome.settled is False
    assert outcome.status == schema_settle.NOT_SETTLED
    assert outcome.attempts == 4 and len(probe.calls) == 4
    assert len(clock.sleeps) == 3, "no wait is spent after the last attempt"
    assert "4" in outcome.detail and "1254036" in outcome.detail


def test_an_UNBOUNDED_budget_is_REFUSED_rather_than_accepted():
    for bad in (0, -1, None):
        with pytest.raises(ValueError):
            schema_settle.settle(_probe(["ok"]), attempts=bad)


def test_a_REAL_FAILURE_IS_NOT_A_SETTLE_and_propagates_typed():
    def probe():
        raise_for_base_code({"code": 91402, "msg": "NOTEXIST"}, context="read the copy")

    with pytest.raises(LarkAPIError) as caught:
        schema_settle.settle(probe, sleep=_Clock())
    assert caught.value.code == 91402


def test_the_outcome_is_JSON_SERIALISABLE_and_says_HOW_it_settled():
    import json

    outcome = schema_settle.settle(_probe(["copying", "ok"]), sleep=_Clock())
    blob = json.loads(json.dumps(outcome.to_dict()))
    assert blob["status"] == schema_settle.SETTLED
    assert blob["attempts"] == 2
    assert blob["codes"] == [schema_settle.SETTLING_CODE]
    assert blob["asynchronous"] is True
    assert blob["detail"] and blob["contract"] == schema_settle.ASYNC_SETTLE_CONTRACT
    assert "value" not in blob, "the settle outcome discloses HOW it settled, not the payload"


def test_NO_BARE_SLEEP_AND_NO_FIXED_WAIT_IS_WRITTEN_INTO_THE_SHIPPED_MODULE():
    """The defect this AC exists to forbid, checked in the source rather than described."""
    import inspect

    source = inspect.getsource(schema_settle)
    body = "\n".join(line for line in source.splitlines()
                     if not line.strip().startswith("#"))
    assert "time.sleep(" not in body, (
        "the settle loop takes its wait as an injected callable; importing time.sleep "
        "directly is how a poll becomes a sleep")
