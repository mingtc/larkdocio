"""LD-458 — the one opt-in shim for suites that assert an apply-LOG rather than the raise.

Since LD-458 a plan-gated ``apply()`` **raises** :class:`~larkdocio.errors.LarkApplyRefusedError`
when its log carries refusals, unless the caller passes ``allow_partial=True`` (the maintainer ruling,
2026-08-14: *"go with a"*). Most of this repo's write suites exist to assert **what the log
says** — which entry refused, with which typed reason, having issued which calls — so their
subject is the log, not the return-vs-raise policy. Rather than sprinkle the opt-in over several
hundred call sites (which would bury the policy in noise and make it un-greppable), each such
suite opts in **once**, at its import::

    from log_reading_apply import reading_the_log
    from larkdocio.sheets.write_apply import apply

    apply = reading_the_log(apply)

The shim only supplies a **default**: a test that passes ``allow_partial`` itself still wins, so
a suite can still drive the un-opted-in path in the same file. The policy itself — the raise, the
typed error, the one spelling on every surface — is pinned in
``tests/test_apply_refusal_policy.py``, and the live proof in
``tests/test_live_write_refusal_policy_gate.py``.

``functools.wraps`` is load-bearing here, not decoration: several suites read the engine's
**signature** and its **source** through the name they imported (the AST guards that prove the
per-entry loop wraps its step in ``except Exception``), and ``__wrapped__`` keeps
``inspect.signature`` / ``inspect.getsource`` pointed at the real engine.
"""
import functools


def reading_the_log(apply_fn):
    """Wrap a plan-gated ``apply`` so it **defaults** to ``allow_partial=True``.

    Returns a function that is signature- and source-transparent to ``inspect`` (via
    ``functools.wraps``), so a guard introspecting the engine still sees the engine.
    """
    @functools.wraps(apply_fn)
    def apply_reading_the_log(*args, **kwargs):
        kwargs.setdefault("allow_partial", True)
        return apply_fn(*args, **kwargs)

    return apply_reading_the_log
