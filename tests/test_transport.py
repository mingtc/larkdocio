"""Shared-core write transport tests (LD-061 + AC4).

The write-side transport is NEW infrastructure the writer (W0-S5) builds on; the
read path does not exercise it (reads are not throttle-governed). These pin, all
offline with a fake clock / stubbed opener:

* ``RateLimiter`` paces to ``≤ max_per_sec`` acquisitions per rolling 1s window;
* ``WriteTransport.execute`` **backs off** on Lark code ``99991400`` (both when a
  call *returns* the rate-limit code and when it *raises* the S1
  ``LarkRateLimitError``), retrying with exponential backoff and finally raising
  the typed ``LarkRateLimitError`` when the limit will not clear;
* ``fetch_tenant_access_token`` raises the S1 typed errors on its failure paths
  (AC4) and returns the token on success.
"""

import json

import pytest

from larkdocio.common.transport import (
    RateLimiter,
    WriteTransport,
    fetch_tenant_access_token,
)
from larkdocio.errors import (
    LarkAPIError,
    LarkConfigError,
    LarkRateLimitError,
)

from write_harness import FakeClock


# --------------------------------------------------------------------------- #
# AC2 — RateLimiter: ≤3 writes/sec (rolling window)                            #
# --------------------------------------------------------------------------- #

def test_rate_limiter_allows_burst_up_to_max_then_paces():
    """Three acquisitions in the same window are free; the fourth sleeps until
    the oldest event leaves the 1s window (so ≤3 per second)."""
    clock = FakeClock()
    rl = RateLimiter(max_per_sec=3, time_fn=clock.time, sleep_fn=clock.sleep)

    times = []
    for _ in range(3):
        rl.acquire()
        times.append(clock.now)

    assert times == [0.0, 0.0, 0.0]
    assert clock.sleeps == []          # first 3 within one window: no wait

    rl.acquire()                       # the 4th must pace
    assert clock.sleeps == [1.0]       # slept one full window
    assert clock.now == 1.0


def test_rate_limiter_never_exceeds_three_per_second():
    """Across 9 acquisitions the limiter never lets more than 3 land in any 1s
    window (each group of 3 costs one window of pacing)."""
    clock = FakeClock()
    rl = RateLimiter(max_per_sec=3, time_fn=clock.time, sleep_fn=clock.sleep)

    stamps = []
    for _ in range(9):
        rl.acquire()
        stamps.append(clock.now)

    for i, t in enumerate(stamps):
        in_window = [s for s in stamps if t - 1.0 < s <= t]
        assert len(in_window) <= 3, f"acquire #{i} had >3 in its trailing second"


def test_rate_limiter_rejects_bad_rate():
    with pytest.raises(LarkConfigError):
        RateLimiter(max_per_sec=0)


# --------------------------------------------------------------------------- #
# AC2 — WriteTransport: backoff on 99991400                                    #
# --------------------------------------------------------------------------- #

def _high_rate_transport(clock, **kw):
    """A transport whose throttle never fires (so sleeps are backoff-only)."""
    return WriteTransport(
        max_writes_per_sec=1000,
        base_backoff=0.5,
        time_fn=clock.time,
        sleep_fn=clock.sleep,
        **kw,
    )


def test_execute_backs_off_on_returned_rate_limit_code_then_succeeds():
    """A call that returns ``99991400`` twice then a ``code:0`` success is retried
    with exponential backoff and the success payload is returned."""
    clock = FakeClock()
    responses = [
        {"code": "99991400", "msg": "rate"},
        {"code": "99991400", "msg": "rate"},
        {"code": 0, "data": {"ok": True}},
    ]
    calls = []

    def call():
        r = responses[len(calls)]
        calls.append(r)
        return r

    t = _high_rate_transport(clock, max_retries=5)
    resp = t.execute(call)

    assert resp == {"code": 0, "data": {"ok": True}}
    assert len(calls) == 3
    assert clock.sleeps == [0.5, 1.0]   # 0.5*2^0, 0.5*2^1


def test_execute_backs_off_on_raised_rate_limit_then_succeeds():
    """A call that *raises* ``LarkRateLimitError`` (the S1 type) is retried too."""
    clock = FakeClock()
    outcomes = [
        LarkRateLimitError("rl", code="99991400", msg="rate"),
        {"code": 0, "data": {}},
    ]
    calls = []

    def call():
        o = outcomes[len(calls)]
        calls.append(o)
        if isinstance(o, Exception):
            raise o
        return o

    t = _high_rate_transport(clock, max_retries=5)
    resp = t.execute(call)

    assert resp == {"code": 0, "data": {}}
    assert len(calls) == 2
    assert clock.sleeps == [0.5]


def test_execute_raises_typed_rate_limit_when_backoff_exhausted():
    """When the limit never clears, the transport re-raises the S1
    ``LarkRateLimitError`` after ``max_retries`` retries."""
    clock = FakeClock()

    def call():
        return {"code": "99991400", "msg": "still limited"}

    t = _high_rate_transport(clock, max_retries=2)
    with pytest.raises(LarkRateLimitError) as ei:
        t.execute(call)

    assert ei.value.is_rate_limit is True
    assert clock.sleeps == [0.5, 1.0]   # two backoff waits then give up


def test_execute_returns_non_rate_limit_response_untouched():
    """A non-rate-limit response (incl. a benign error code) is returned as-is —
    the transport only retries on the rate-limit code, not on every error."""
    clock = FakeClock()

    def call():
        return {"code": "1061004", "msg": "not found"}

    t = _high_rate_transport(clock)
    resp = t.execute(call)

    assert resp == {"code": "1061004", "msg": "not found"}
    assert clock.sleeps == []


def test_execute_throttles_via_the_rate_limiter():
    """A transport with a real ≤3/sec throttle paces successful writes."""
    clock = FakeClock()
    t = WriteTransport(
        max_writes_per_sec=3, time_fn=clock.time, sleep_fn=clock.sleep
    )

    for _ in range(4):
        t.execute(lambda: {"code": 0})

    assert clock.sleeps == [1.0]        # 4th write paced by the throttle


# --------------------------------------------------------------------------- #
# AC4 — fetch_tenant_access_token raises S1 typed errors / returns the token   #
# --------------------------------------------------------------------------- #

class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b


def test_fetch_token_happy_path_returns_token():
    def urlopen(req, timeout=30):
        return _Resp({"code": 0, "tenant_access_token": "t-abc", "expire": 7200})

    tok = fetch_tenant_access_token(
        "app", "secret", "larksuite.com", urlopen=urlopen
    )
    assert tok == "t-abc"


def test_fetch_token_missing_credentials_raises_config_error():
    with pytest.raises(LarkConfigError):
        fetch_tenant_access_token("", "secret")
    with pytest.raises(LarkConfigError):
        fetch_tenant_access_token("app", "")


def test_fetch_token_nonzero_code_raises_api_error():
    def urlopen(req, timeout=30):
        return _Resp({"code": 10003, "msg": "bad app secret"})

    with pytest.raises(LarkAPIError) as ei:
        fetch_tenant_access_token("app", "secret", urlopen=urlopen)
    assert ei.value.code == 10003
    assert ei.value.msg == "bad app secret"


def test_fetch_token_rate_limit_code_raises_typed_rate_limit():
    def urlopen(req, timeout=30):
        return _Resp({"code": "99991400", "msg": "rate"})

    with pytest.raises(LarkRateLimitError):
        fetch_tenant_access_token("app", "secret", urlopen=urlopen)


def test_fetch_token_missing_token_field_raises_api_error():
    def urlopen(req, timeout=30):
        return _Resp({"code": 0})       # success code but no token

    with pytest.raises(LarkAPIError):
        fetch_tenant_access_token("app", "secret", urlopen=urlopen)
