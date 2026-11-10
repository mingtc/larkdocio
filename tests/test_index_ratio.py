"""LD-640 AC5 — one spelling of "an index is at least 20× smaller than what it indexes".

**Why this module exists.** Four guards asserted that invariant in three different ways::

    tests/test_capabilities_summary.py    assert small * 20 < whole
    tests/test_guide_sections.py          assert len(serialized) < len(text) // 20
    tests/test_front_door_guide_swap.py   assert len(index) < len(document) / 20
    tests/test_cli_front_door_truth.py    assert 0 < len(api.stdout) < len(api_full.stdout) / 20

The three spellings are **not** equivalent. For integer ``small`` and ``whole``,
``small * 20 < whole`` is exactly ``small < whole / 20``; ``small < whole // 20`` is
**strictly stronger**, because ``//`` floors — it rejects a ``small`` that the other two accept
whenever ``whole % 20 != 0`` and ``small == floor(whole / 20)``. So the spellings disagree only
when the smaller value sits within one unit of ``whole / 20``, and **unifying on ``//`` is a
real tightening of any guard sitting inside that window** — not a refactor.

MEASURED BEFORE UNIFYING (LD-640, 2026-09-03), because that is the only thing that made this
change legitimate. Re-derive with the commands rather than trusting the figures::

    # sites 1-3, and site 4's values modulo the wheel build:
    python - <<'EOF'
    import json, importlib.resources as r
    from larkdocio import capabilities, guide
    from larkdocio.capabilities._summary import summary, summary_bytes
    p = capabilities(full=True); print(summary_bytes(p) / summary_bytes(summary(p)))
    t = guide(full=True)
    print(len(t) / len(json.dumps(p["docs"]["guide()"])))   # site 2
    print(len(t) / len(guide()))                            # site 3
    print(len(t.encode()) / len(guide().encode()))          # site 4, same accessor
    EOF

Recorded ratios on that date, against a 20× threshold: capabilities summary **21.75×**
(15,285 / 332,424 bytes — the tightest of the four, and still 1,335 bytes clear of the
boundary), the guide's ``docs`` row **46.94×** (18,702 / 877,875 chars), the guide index
**50.05×** (17,540 / 877,875 chars), and the same index in bytes **49.46×**
(17,879 / 884,289). Every one of them clears the disagreement window by more than three
orders of magnitude of the one-unit window width, so no site is tightened by the move to
``//`` and the unification is behaviour-preserving in fact as well as in intent.

Note site 4 asserts over the stdout of a console script from a **clean-venv installed wheel**,
which this measurement approximates with the same accessor in this tree — the shipped
``GUIDE.md`` resource is the same file, and that test's own ``> 100_000`` floor independently
pins the scale. Its margin is stated as measured-by-proxy, not as read off the wheel.
"""
import json

from larkdocio import capabilities, guide
from larkdocio.capabilities._summary import summary, summary_bytes

#: The ratio every "this is an index, not a slightly shorter dump" guard asserts.
INDEX_RATIO = 20


def is_index_sized(small, whole, factor=INDEX_RATIO):
    """True when ``small`` is at least ``factor`` times smaller than ``whole``.

    The **strictest** of the three spellings the four call sites used, on purpose: a guard
    should not care which side of a rounding boundary it landed on, and the floor is the
    reading a human means by "twenty times smaller". Each call site keeps its own failure
    message — the numbers in those messages are what makes a red actionable, and they are
    that site's business, not this predicate's.
    """
    return small < whole // factor


def test_the_predicate_is_the_STRICTEST_of_the_three_spellings():
    """The claim the unification rests on, proved rather than argued: ``//`` accepts a strict
    subset of what ``* 20 <`` and ``/ 20`` accept, and the three differ only inside a
    one-unit window.
    """
    boundary = 20 * 500 + 7          # whole % 20 == 7, so floor(whole/20) == 500
    assert boundary // INDEX_RATIO == 500

    # Inside the window: the loose spellings accept 500, the strict one refuses it.
    assert 500 * 20 < boundary
    assert 500 < boundary / 20
    assert not is_index_sized(500, boundary)

    # Outside the window in both directions: all three agree.
    assert is_index_sized(499, boundary) and 499 * 20 < boundary
    assert not is_index_sized(501, boundary) and not 501 * 20 < boundary

    # And no spelling ever accepts something bigger than its whole.
    assert not is_index_sized(boundary, boundary)


def test_every_live_index_clears_the_DISAGREEMENT_WINDOW_not_merely_the_ratio():
    """The measurement that licensed the unification, re-derived on every run.

    A site that merely *passed* under ``//`` would not be enough to know the move was
    behaviour-preserving — it has to be clear of the window where the spellings differ at all,
    which is what this asserts. If a future change drags one of these toward 20×, this reddens
    HERE, next to the reasoning, instead of turning a refactor into a silent tightening.
    """
    payload = capabilities(full=True)
    text = guide(full=True)
    sites = {
        "capabilities summary vs payload": (summary_bytes(summary(payload)),
                                            summary_bytes(payload)),
        "guide docs row vs document": (len(json.dumps(payload["docs"]["guide()"])), len(text)),
        "guide index vs document": (len(guide()), len(text)),
        "guide index vs document, in bytes": (len(guide().encode("utf-8")),
                                              len(text.encode("utf-8"))),
    }
    for label, (small, whole) in sites.items():
        floor, exact = whole // INDEX_RATIO, whole / INDEX_RATIO
        assert is_index_sized(small, whole), (
            f"{label}: {small} against {whole} is not {INDEX_RATIO}x smaller")
        assert small < floor and small < exact and small * INDEX_RATIO < whole, (
            f"{label}: {small} sits INSIDE the spelling-disagreement window "
            f"[{floor}, {exact}] for a {whole}-unit whole — the three spellings no longer "
            "agree here, so unifying them would tighten this guard. Do not 'fix' the "
            "spelling; report the number (LD-640 AC5).")
