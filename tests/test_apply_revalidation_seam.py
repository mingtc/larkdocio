"""LD-142 (refactor T2) — the ONE shared pre-write re-validation seam in ``write/apply.py``.

The identical six-line guard opening (``_live_or_stale`` → early-return → unpack →
``_stale_if_drifted`` → early-return) stood **verbatim three times** — narrative / insert /
delete — at the one place in the engine where a missed edit means *a write that should have
refused*. LD-137 had to thread ``precondition_text`` through all three copies; the next change
would have been three coordinated edits again. This refactor extracts
:func:`~larkdocio.write.apply._revalidated_or_stale`, which composes the two existing helpers,
so the three callers collapse to one call each.

What this file pins (nothing here is new behavior — every assertion holds byte-identically
before and after the extraction, except the *existence* of the seam):

* **the seam is singular** — the three single-re-validation paths open with the extracted
  guard and nothing else, and it has exactly three call sites (structural, AST-level, so a
  fourth policy or a path that re-inlines the preamble reddens);
* **the composed order** — the read-failure arm (the block was deleted under us) refuses
  *before* the drift check can look at a text that does not exist;
* **all three refusal arms** the one guard now owns: the by-id compare-and-swap, the
  quote-drift check, and the failed-read/deleted-block arm — the three the mutation
  verification (B3) breaks the guard once to redden;
* **the deliberate divergence (B4)** — sub-span and table-cell run their **own**, different
  re-validation and are deliberately **NOT** routed through the shared guard. The
  characterization test here is the one that would catch a future "unify them all" edit: a
  sub-span whose *anchor quote* has drifted out of the live text but whose *span* survives
  still applies, because the sub-span path never runs the narrative quote check.

Offline throughout (the shared ``write_harness`` fake transport, no network, no creds).
"""
import ast
from pathlib import Path

import pytest

from larkdocio.write.apply import _revalidated_or_stale, apply
from larkdocio.write.model import AnchorById, RefusalReason, TableLocator
from larkdocio.write.preview import PlanEntry, dry_run

from write_harness import (
    StubOpener,
    _block_payload,
    _client,
    _methods,
    _page,
    _para,
    _patch_ok,
    _run,
)

_APPLY_PY = (
    Path(__file__).resolve().parents[1] / "src" / "larkdocio" / "write" / "apply.py"
)

#: The three paths whose preamble was copy-pasted, and which the extraction collapses.
_SINGLE_REVALIDATION_PATHS = ("_apply_narrative", "_apply_insert", "_apply_delete")

#: The two paths whose re-validation is deliberately different (B4) — see the module
#: docstring. ``_apply_table_cell`` runs a DOUBLE read (row identity + cell content);
#: ``_apply_subspan`` re-validates the SPAN, not the anchor.
_OWN_REVALIDATION_PATHS = ("_apply_subspan", "_apply_table_cell")


def _not_found(block_id):
    """A ``get_block`` reply for a block that is GONE — the stale-race payload.

    Lark answers a read of a deleted block with a non-zero ``code``, which the shared
    transport turns into a :class:`~larkdocio.errors.LarkAPIError` — what the guard must
    convert into a ``stale-anchor`` refusal instead of letting it abort the batch.
    """
    return {"code": 1770002, "msg": f"block {block_id} not found"}


def _called_names(function_node):
    """Every plain-function name called inside one ``FunctionDef`` (nested defs included)."""
    return [
        node.func.id
        for node in ast.walk(function_node)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]


def _function(name):
    tree = ast.parse(_APPLY_PY.read_text(encoding="utf-8"))
    return next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _entry(anchor, *, block_id="p1", precondition_text=None):
    """One resolved narrative plan entry — the guard's input shape."""
    return PlanEntry.resolved(
        anchor=anchor,
        replacement="NEW",
        block_id=block_id,
        before="whatever the plan saw",
        after="NEW",
        precondition_text=precondition_text,
    )


# =========================================================================== #
# The seam is singular — structural (AST), so a re-inlined preamble reddens.    #
# =========================================================================== #

@pytest.mark.parametrize("path", _SINGLE_REVALIDATION_PATHS)
def test_each_single_revalidation_path_opens_with_the_one_extracted_guard(path):
    """Narrative / insert / delete each call the extracted guard **once** and neither of
    the two helpers it composes — that is what "the preamble is not copied" means at the
    code level, and it is why the next threading change is one edit, not three."""
    called = _called_names(_function(path))
    assert called.count("_revalidated_or_stale") == 1, (
        f"{path} must open with exactly one _revalidated_or_stale(...) call; called {called}")
    for inlined in ("_live_or_stale", "_stale_if_drifted"):
        assert inlined not in called, (
            f"{path} re-inlines {inlined} — the pre-write re-validation preamble is copied "
            f"again, which is exactly the shape LD-142 removed")


def test_the_extracted_guard_has_exactly_three_call_sites():
    """One guard, three callers. A fourth call site would mean a fourth write path grew a
    re-validation — a policy decision that must be seen, not inherited."""
    source = _APPLY_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "_revalidated_or_stale"
    ]
    assert len(calls) == 3, f"_revalidated_or_stale is called {len(calls)} times, expected 3"


def test_the_guard_composes_both_halves_and_nothing_else():
    """The extraction is a *composition*, not a re-implementation: the guard body calls
    both existing helpers and does not re-derive either check inline."""
    called = _called_names(_function("_revalidated_or_stale"))
    assert called.count("_live_or_stale") == 1, called
    assert called.count("_stale_if_drifted") == 1, called


# =========================================================================== #
# B4 — sub-span + table-cell keep their own, deliberately different check.      #
# =========================================================================== #

@pytest.mark.parametrize("path", _OWN_REVALIDATION_PATHS)
def test_the_own_revalidation_paths_are_not_routed_through_the_shared_guard(path):
    """Scope discipline, pinned. Sub-span re-validates the **span** (an offset-bearing,
    stricter precondition) and table-cell runs a **double** read (row identity + cell
    content, the table-row-patch spec § Decision f). Neither is the narrative single check, so neither may
    inherit it: they share the *read* helper and keep their own check body."""
    called = _called_names(_function(path))
    assert "_revalidated_or_stale" not in called, (
        f"{path} was routed through the narrative guard — its re-validation is "
        f"deliberately different (LD-142 B4 / out of scope)")
    assert "_stale_if_drifted" not in called, (
        f"{path} gained the narrative quote/CAS check; it must keep its own")
    assert called.count("_live_or_stale") == (2 if path == "_apply_table_cell" else 1), (
        f"{path} changed how many live reads it opens with: {called}")


def test_a_table_locator_carries_no_quote_at_all():
    """*Why* a table-cell edit cannot be routed through the narrative guard, in one line:
    a :class:`TableLocator` has no ``quote`` attribute, so the quote arm of
    ``_stale_if_drifted`` is not even expressible for it (it would raise, not refuse)."""
    locator = TableLocator(row_key="Q3", column_index=1)
    assert not hasattr(locator, "quote")


def test_a_subspan_whose_anchor_quote_drifted_but_whose_span_survives_still_applies():
    """The characterization that catches a future "unify them all" edit (B4).

    The anchor quote is **gone** from the live text, but the span is still there exactly
    once — so the sub-span path applies, because it never runs the narrative quote check.
    Route sub-span through the shared guard and this write turns into a ``stale-anchor``
    refusal: a real behavior change, hidden inside a "cleanup".
    """
    from larkdocio.write.model import SubSpanEditRequest, Anchor

    tree = _page(_para("p1", "the value 67 stands"))
    plan = dry_run([SubSpanEditRequest(
        anchor=Anchor(quote="the value 67 stands"), span="67", replacement="72")], tree)
    # Live drifted: the ANCHOR QUOTE is no longer a substring, but the SPAN survives.
    opener = StubOpener([_block_payload("p1", [_run("67 alone")]), _patch_ok()])
    log = apply(plan, _client(opener), "doc123")

    (entry,) = log.entries
    assert entry.outcome == "applied", entry.refusal
    assert _methods(opener) == ["GET", "PATCH"]
    elements = opener.requests[1]["body"]["update_text_elements"]["elements"]
    assert [el["text_run"]["content"] for el in elements] == ["72", " alone"]


# =========================================================================== #
# The guard's composed behavior — the three arms it now owns (B2 / B3 / B5).    #
# =========================================================================== #

def test_the_guard_returns_the_live_read_triple_when_nothing_drifted():
    """Fresh block → ``(read, None)``: the caller gets the raw block (delete needs it for
    its parent + removed-payload capture), the live elements (narrative needs them for the
    style-preserving rebuild) and the plain text (every caller reports it)."""
    opener = StubOpener([_block_payload("p1", [_run("first line")])])
    entry = _entry(AnchorById(block_id="p1"), precondition_text="first line")

    read, stale = _revalidated_or_stale(_client(opener), "doc123", entry)

    assert stale is None
    block, live_elements, live_text = read
    assert block["block_id"] == "p1"
    assert live_elements == [_run("first line")]
    assert live_text == "first line"
    assert _methods(opener) == ["GET"]           # one read, no write


def test_the_guard_refuses_the_read_failure_before_it_ever_checks_drift():
    """Arm 3 — the deleted-block/stale-race arm, and the **order** of the composition: a
    block that cannot be re-read refuses on the read, so the drift check never runs against
    a text that does not exist."""
    opener = StubOpener([_not_found("p1")])
    entry = _entry(AnchorById(block_id="p1"), precondition_text="first line")

    read, stale = _revalidated_or_stale(_client(opener), "doc123", entry)

    assert read is None
    assert stale.outcome == "refused"
    assert stale.refusal.reason is RefusalReason.STALE_ANCHOR
    assert "could not be re-read" in stale.refusal.detail
    assert "1770002" in stale.refusal.detail       # Lark's own code, verbatim (LD-131)


def test_the_guard_refuses_the_by_id_compare_and_swap_on_content_drift():
    """Arm 1 — an id-anchored entry whose block changed since the plan: the live text must
    still **equal** what the plan captured (LD-137), and the refusal names both."""
    opener = StubOpener([_block_payload("p1", [_run("SOMEBODY ELSE EDITED THIS")])])
    entry = _entry(AnchorById(block_id="p1"), precondition_text="first line")

    read, stale = _revalidated_or_stale(_client(opener), "doc123", entry)

    assert read is None
    assert stale.refusal.reason is RefusalReason.STALE_ANCHOR
    assert "'first line'" in stale.refusal.detail
    assert "'SOMEBODY ELSE EDITED THIS'" in stale.refusal.detail


def test_the_guard_refuses_a_quote_anchor_whose_quote_left_the_live_text():
    """Arm 2 — the W1 quote-drift check, byte-unchanged: the quote must still be a
    substring of the live text."""
    from larkdocio.write.model import Anchor

    opener = StubOpener([_block_payload("p1", [_run("a completely different line")])])
    entry = _entry(Anchor(quote="first line"))

    read, stale = _revalidated_or_stale(_client(opener), "doc123", entry)

    assert read is None
    assert stale.refusal.reason is RefusalReason.STALE_ANCHOR
    assert "'first line'" in stale.refusal.detail
    assert "no longer present" in stale.refusal.detail


def test_the_guard_threads_the_entrys_own_precondition_text():
    """B5 — the LD-137 threading survives the extraction, including its ``None`` arm: an
    entry rebuilt from a wire form that predates the field carries no precondition, so the
    block's mere existence IS the whole precondition and a changed text does not refuse."""
    opener = StubOpener([_block_payload("p1", [_run("changed under us")])])
    entry = _entry(AnchorById(block_id="p1"), precondition_text=None)

    read, stale = _revalidated_or_stale(_client(opener), "doc123", entry)

    assert stale is None, "no captured precondition ⇒ existence is the whole check"
    assert read[2] == "changed under us"
