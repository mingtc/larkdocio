"""LD-363 — the safety net for decomposing ``reconcile()``: its refusal STRINGS and their
EVALUATION ORDER, pinned before the first extract-function move.

Why this file exists, in the audit's own words: *"an extract-function that looks
behavior-preserving changes the ORDER in which two refusals are evaluated, so a plan that
used to refuse for reason A now refuses for reason B — a consumer-visible string change
that the golden tests may not pin."* The reconciliation suites next door pin **which
reason** fires for a shaped input; what they do not pin is (a) the refusal's **exact
text**, byte for byte, and (b) **which refusal wins when two conditions are true at once**.
Both are consumer-visible, so both are behavior. This module pins them on the
**pre-refactor** body.

It is a CHARACTERIZATION suite: every literal below is the behavior as it stood at
``refactor-baseline-2026-08-09-LD-363``, captured by running the code, not by deciding what
it ought to say. A failure here after a move means the move was not behavior-preserving —
the move is wrong, never this file.

The pairs in § 2 were enumerated by **reading the pre-refactor body of ``reconcile()``**
(``src/larkdocio/write/reconcile.py``) top to bottom and asking, at every ``return`` and
every ``refusals.append``, which other refusal could have been reachable for the same
input. The stage boundaries (each stage returns before the next runs) are the coarse
ladder; the within-``_diff_segment`` sequence is the fine one. Pairs that are provably
unreachable are named in ``UNREACHABLE_PAIRS`` with the argument for each.
"""
import pytest

from larkdocio.write.model import RefusalReason
from larkdocio.write.reconcile import (
    RECONCILIATION_REFUSAL_REASONS,
    AbsentBlockDisposition,
    reconcile,
)

from larkdocio.write.compiler import compile_reconciliation
from larkdocio.write.intrabatch import COMMIT_THEN_ANCHOR_RULE
from larkdocio.write.model import RefusedError
from larkdocio.write.reconcile import ReconciliationPlan

# The hand-built projection helpers are the reconciliation suite's own — a second copy of
# them here would be a second definition of what a projection looks like.
from test_reconciliation_refusal_set import (
    TABLE,
    details,
    edited,
    marker_eaten,
    opaque_projection,
    projection,
    reasons,
)


def _compiled_refusal(before: str, after: str) -> ReconciliationPlan:
    """The COMPILE-time refusal for a one-block projection, as a refusing plan.

    LD-574's ``change-not-expressible`` is decided by ``compile_reconciliation`` rather than
    by ``reconcile``, so its text cannot be reached by calling the reconciler alone. Wrapping
    it here keeps this file's single mechanism intact instead of growing a second case shape:
    the plan a compile-time refusal WOULD have been, had the reconciler been able to see it.
    """
    source = projection(("b1", before))
    plan = reconcile(source, edited(("b1", after)))
    assert plan.ok, "the reconciler counts this as a change — that is the whole premise"
    try:
        compile_reconciliation(plan, source)
    except RefusedError as refused:
        return ReconciliationPlan(refusals=(refused.refusal,))
    raise AssertionError("the compiler did not refuse")


# LD-370 — CONFORMANCE-tier: a refusal STRING and its evaluation order are consumer-visible; LD-363 pinned them precisely because a rewrite must not change them.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

DELETE = AbsentBlockDisposition.DELETE

#: The two-block document most single-reason cases are shaped against.
TWO = projection(("p1", "one"), ("p2", "two"))
#: A three-block one, for the cases that need a third marker to stay put.
THREE = projection(("p1", "one"), ("p2", "two"), ("p3", "three"))
#: One with unmarked content ahead of the first marker — the head segment's own cases.
HEAD = projection((None, "title"), ("p1", "one"), ("p2", "two"))


# --------------------------------------------------------------------------- #
# 1. THE STRINGS — every reason reconcile() can emit, byte for byte.           #
# --------------------------------------------------------------------------- #

#: ``name -> (a call producing exactly one refusal, its reason, its EXACT detail)``.
#: The detail is the whole string: a test that greps for a substring would let a rewrite
#: of the sentence around it through, and the sentence is what the consumer reads.
REFUSAL_TEXT_CASES = {
    "marker-invented": (
        lambda: reconcile(TWO, edited(("p1", "one"), ("p2", "two"), ("zz9", "smuggled"))),
        RefusalReason.MARKER_INVENTED,
        "the edited Markdown carries a marker for block 'zz9', which this document's "
        "projection never emitted. Identity comes only from the identifiers the "
        "projection returned, so this marker names no block: it was either invented by "
        "the editor or is text that happens to be marker-shaped. Remove it, or re-project "
        "the document and edit that.",
    ),
    "marker-duplicated": (
        lambda: reconcile(TWO, edited(("p1", "one"), ("p2", "two"), ("p1", "again"))),
        RefusalReason.MARKER_DUPLICATED,
        "the marker for block 'p1' appears more than once in the edited Markdown "
        "(line 1, line 7). One identifier names one block, so there is no honest way to "
        "choose which occurrence the block's new content is; nothing was planned. Keep "
        "the one occurrence that holds the block's text, delete the other, and re-run.",
    ),
    "marker-mangled": (
        lambda: reconcile(
            TWO, edited(("p1", "one"), ("p2", "two")) + "\n<!--lark:block:p1-->\n"
        ),
        RefusalReason.MARKER_MANGLED,
        "line 7 of the edited Markdown is marker-shaped but is not a marker: "
        "'<!--lark:block:p1-->'. A marker is matched byte for byte, and the canonical "
        "form is exactly '<!-- lark:block:<block id> -->' on a line of its own. A "
        "marker-shaped line that is not byte-exact is not repaired into the marker it "
        "resembles, because it may be content that merely looks like one and repairing it "
        "would guess which. Nothing was planned. Restore the line to the exact form the "
        "projection emitted for that block, or — if it is your own content rather "
        "than a marker — remove that line and re-run.",
    ),
    "marker-order-changed": (
        lambda: reconcile(TWO, edited(("p2", "two"), ("p1", "one"))),
        RefusalReason.MARKER_ORDER_CHANGED,
        "the surviving markers come back in a different order than the document has them "
        "(first difference at 'p2', 'p1'). Moving a block is not expressible: the only "
        "way to express it would be to delete the block and insert a copy, which destroys "
        "its identifier and everything anchored to it. Nothing was planned. Restore the "
        "original order and make the content changes on their own.",
    ),
    "marker-absent": (
        lambda: reconcile(TWO, edited(("p1", "one"))),
        RefusalReason.MARKER_ABSENT,
        "block 'p2' has no marker in the edited Markdown, and it is still in the document "
        "reading: 'two'. An absent marker is not a deletion — a marker dropped "
        "together with its content cannot be told apart from a rewrite that dropped the "
        "marker, and the two readings differ by destroying content. Nothing was planned. "
        "Put the marker back together with the block's text to keep it, or re-run with "
        "the deletion disposition to mean the deletion.",
    ),
    "marker-dropped": (
        lambda: reconcile(TWO, edited(("p1", "one")) + "\ntwo\n"),
        RefusalReason.MARKER_DROPPED,
        "block 'p2' has no marker in the edited Markdown, but the block's own text came "
        "back with it, reading: 'two'. That is a dropped marker, not a deletion and not a "
        "rewrite — and the block is never re-attached to text by resemblance, "
        "because an identifier cannot be recovered from what a block happens to say and a "
        "wrong re-attachment rewrites the wrong block. Nothing was planned. Put the "
        "block's own marker line back immediately above that text and re-run.",
    ),
    "marker-orphaned": (
        lambda: reconcile(TWO, edited(("p1", ""), ("p2", "two"))),
        RefusalReason.MARKER_ORPHANED,
        "block 'p1': its marker came back with no content under it, where the document "
        "has 'one'. An emptied block is a deletion expressed ambiguously — it may "
        "mean the block should go, or it may be content lost while editing — and the "
        "two readings differ by destroying content. Nothing was planned. Put the block's "
        "text back under its marker to keep it; to delete it, remove its marker together "
        "with its text and re-run under the explicit deletion disposition.",
    ),
    "marker-relocated": (
        lambda: reconcile(TWO, edited(("p1", "two"), ("p2", "two"))),
        RefusalReason.MARKER_RELOCATED,
        "block 'p1': its segment came back holding block 'p2''s text, and this block's "
        "own text is not in it. A marker sitting on another block's content is not an "
        "edit — applying it would rewrite both blocks with each other's text, which "
        "is the one corruption that reading either block afterwards would not reveal. "
        "Nothing was planned. Put each block's text back under its own marker; to move "
        "text between blocks, edit each block's own content in place rather than moving "
        "the markers.",
    ),
    "segment-ambiguous": (
        lambda: reconcile(TWO, edited(("p1", "changed\n\nand added"), ("p2", "two"))),
        RefusalReason.SEGMENT_AMBIGUOUS,
        "block 'p1': its segment came back as 2 piece(s) of content and none of them is "
        "the block's own text, so there is no way to tell which piece is the edited block "
        "and which was added beside it. Choosing would rewrite the block with content "
        "that was never meant for it. Nothing was planned. Make the edit and the addition "
        "in two separate rounds.",
    ),
    "block-type-mutation": (
        lambda: reconcile(TWO, edited(("p1", "# one heading"), ("p2", "two"))),
        RefusalReason.BLOCK_TYPE_MUTATION,
        "block p1: the edited Markdown is a heading (level 1) where the block is a "
        "paragraph. A reconciliation never changes a block's type — the block would "
        "have to be destroyed and re-created, losing its identifier and everything "
        "anchored to it (comment anchors most pointedly). To make this change, delete the "
        "block and insert the replacement as two separate commits.",
    ),
    "unmarked-content-changed": (
        lambda: reconcile(HEAD, edited((None, "different title"), ("p1", "one"), ("p2", "two"))),
        RefusalReason.UNMARKED_CONTENT_CHANGED,
        "the content before the first marker came back changed. It carries no identifier "
        "— the document's title block is projected without one — so no request "
        "can be attributed to it and nothing was planned. Restore it, and make the change "
        "through a block that carries a marker.",
    ),
    "undecodable-text": (
        lambda: reconcile(TWO, edited(("p1", r"one \q"), ("p2", "two"))),
        RefusalReason.UNDECODABLE_TEXT,
        "block 'p1': the Markdown cannot be decoded out of the projection's escaping, so "
        "it cannot be compared with the block's own text without guessing — a "
        "backslash at position 4 introduces 'q', which the escape policy never escapes, "
        "so this text was not produced by it; decoding would have to guess whether the "
        "backslash is literal or a truncated escape. The projection escapes literal text; "
        "a backslash it never emits means the text did not come from it.",
    ),
    "conserved-block-re-created": (
        lambda: reconcile(
            opaque_projection(TABLE, "table"), marker_eaten(TABLE), absent=DELETE
        ),
        RefusalReason.CONSERVED_BLOCK_RE_CREATED,
        "block 'tb' is conserved — a block of this kind is never edited, never "
        "deleted and never re-created — but its marker is not in the edited Markdown "
        "and its own content came back unmarked, reading: '| head | count |\\n| --- | "
        "--- |\\n| alpha | 1 |'. Planning that content as an addition would leave the "
        "document holding the block twice, once conserved and once created, so nothing "
        "was planned. The content is not discarded either: text beside a conserved block "
        "may be a real addition, and dropping it would destroy an edit. Put the block's "
        "own marker line back immediately above that content and re-run; to keep the "
        "block and add a second copy of it, restore that marker and leave the extra copy "
        "under the block's own text.",
    ),
    # The last two are the authoring compiler's own refusals, propagated unchanged. They
    # are pinned as PROPAGATED (the compiler owns the sentence) rather than re-quoted: a
    # copy of compose()'s text here would be a second definition of it.
    "not-in-dialect": (
        lambda: reconcile(TWO, edited(("p1", "***"), ("p2", "two"))),
        RefusalReason.NOT_IN_DIALECT,
        "thematic-break at line 1: not expressible as creatable Lark docx content — "
        "a divider (docx block type 22) is not creatable in this rung — drop the "
        "rule, or escape it (\\-\\-\\-) to author it as literal text.",
    ),
    "merge-not-expressible": (
        lambda: reconcile(
            TWO, edited(("p1", "| a | b |\n| --- | --- |\n| only |"), ("p2", "two"))
        ),
        RefusalReason.MERGE_NOT_EXPRESSIBLE,
        "merged-table at line 3: not expressible as creatable Lark docx content — a "
        "merged (colspan/rowspan) table is not expressible — Markdown has no span "
        "syntax, so an authored table is always a plain rectangular grid (give every row "
        "the header's cell count; use an empty string for a blank cell). The grid is "
        "never padded or truncated to fit. (row has 1 cell(s) but the header row has 2; "
        "GFM would silently pad or truncate it)",
    ),
    # LD-574's compile-time refusal. Its ``call`` reaches one step further than the others
    # because the refusal is decided where the REQUEST is built rather than where the plan
    # is: the reconciler counts a change (the raw Markdown differs), and the compiler is
    # what knows the compiled request would write the block's own bytes back. Wrapped into
    # a refusing plan so this file's one mechanism — reason + byte-for-byte detail, with no
    # entries beside it — covers it exactly as it covers the other fourteen.
    "change-not-expressible": (
        lambda: _compiled_refusal("- alpha", "* alpha"),
        RefusalReason.CHANGE_NOT_EXPRESSIBLE,
        "block 'b1': the two spellings compose to the same block, so the edited Markdown "
        "differs only in a way the authoring dialect does not carry. The request this "
        "would compile to writes bytes identical to what is already in the block, so "
        "applying it would report SUCCESS for a change that never happened — and a green "
        "apply log is a receipt. Nothing was compiled and no call was made. To make this "
        "change, delete the block and insert the replacement as two separate commits (its "
        "identifier changes, and anything anchored to it — comment anchors most pointedly "
        "— goes with it). " + COMMIT_THEN_ANCHOR_RULE,
    ),
}


@pytest.mark.parametrize("name", sorted(REFUSAL_TEXT_CASES))
def test_the_refusal_text_is_byte_for_byte_what_it_was(name):
    """The whole detail string, pinned. A decomposition may not reword one clause."""
    call, reason, text = REFUSAL_TEXT_CASES[name]
    plan = call()
    assert reasons(plan) == [reason], name
    assert details(plan) == [text], name
    assert plan.entries == ()


def test_every_registered_reconciliation_reason_has_its_text_pinned_here():
    """Mechanical completeness: a reason added to the registry without a text case here
    reddens, rather than being discovered missing after a move rewrote it."""
    pinned = {reason for _, reason, _ in REFUSAL_TEXT_CASES.values()}
    assert pinned == set(RECONCILIATION_REFUSAL_REASONS)


def test_the_two_type_guards_keep_their_messages_and_the_projection_is_checked_first():
    """Both guards, and their ORDER: a call that is wrong in both ways names the
    projection, because that check runs first."""
    with pytest.raises(TypeError) as both:
        reconcile("not a projection", 42)
    assert str(both.value) == (
        "reconcile() takes the BlockIdProjection the document was projected to (its "
        "emitted identifiers are the only identity source there is), got str"
    )
    with pytest.raises(TypeError) as markdown:
        reconcile(TWO, 42)
    assert str(markdown.value) == (
        "reconcile() takes the edited Markdown as a str, got int"
    )


# --------------------------------------------------------------------------- #
# 2. THE EVALUATION ORDER — which refusal wins when two are true at once.      #
# --------------------------------------------------------------------------- #

#: ``name -> (call, the EXACT reason list the plan comes back with)``. Each entry is an
#: input for which **more than one** refusal condition holds; the pinned list is the
#: pre-refactor answer, in the pre-refactor order. The list is exact — an extra refusal
#: appearing is as much a behavior change as the wrong one winning.
PRECEDENCE_CASES = {
    # --- the coarse ladder: a stage returns before the next stage runs ---------
    "identity beats order": (
        lambda: reconcile(
            THREE, edited(("p2", "two"), ("p1", "one"), ("p3", "three"), ("zz9", "x"))
        ),
        [RefusalReason.MARKER_INVENTED],
    ),
    "identity beats absence": (
        lambda: reconcile(THREE, edited(("p1", "one"), ("p2", "two"), ("zz9", "x"))),
        [RefusalReason.MARKER_INVENTED],
    ),
    "order beats absence": (
        lambda: reconcile(THREE, edited(("p2", "two"), ("p1", "one"))),
        [RefusalReason.MARKER_ORDER_CHANGED],
    ),
    "order beats the per-segment diff": (
        lambda: reconcile(
            THREE,
            edited(("p2", "two"), ("p1", "changed\n\nadded"), ("p3", "three")),
        ),
        [RefusalReason.MARKER_ORDER_CHANGED],
    ),
    "absence beats the per-segment diff": (
        lambda: reconcile(THREE, edited(("p1", "changed\n\nadded"), ("p2", "two"))),
        [RefusalReason.MARKER_ABSENT],
    ),
    # --- within the identity stage: invented, then duplicated, then mangled ----
    "the identity stage reports invented, duplicated, mangled in that order": (
        lambda: reconcile(
            THREE,
            edited(
                ("p1", "one"), ("p2", "two"), ("p3", "three"), ("p1", "again"), ("zz9", "x"),
            )
            + "\n<!--lark:block:p2-->\n",
        ),
        [
            RefusalReason.MARKER_INVENTED,
            RefusalReason.MARKER_DUPLICATED,
            RefusalReason.MARKER_MANGLED,
        ],
    ),
    # --- within the absence stage: dropped and absent, in the DOCUMENT's order -
    "dropped and absent both report, in source order": (
        lambda: reconcile(THREE, edited(("p1", "one")) + "\ntwo\n"),
        [RefusalReason.MARKER_DROPPED, RefusalReason.MARKER_ABSENT],
    ),
    # --- the fine ladder, inside one segment's diff ----------------------------
    "orphaned beats segment-ambiguous": (
        # 0 pieces came back where the document has 1, so the piece-count check would
        # also fire — the emptied-block reading is the one that is reported.
        lambda: reconcile(THREE, edited(("p1", ""), ("p2", "two"), ("p3", "three"))),
        [RefusalReason.MARKER_ORPHANED],
    ),
    "relocated beats segment-ambiguous": (
        lambda: reconcile(
            THREE, edited(("p1", "two\n\nextra"), ("p2", "two"), ("p3", "three"))
        ),
        [RefusalReason.MARKER_RELOCATED],
    ),
    "relocated beats block-type-mutation": (
        lambda: reconcile(
            projection(("p1", "one"), ("p2", "# two")), edited(("p1", "# two"), ("p2", "# two"))
        ),
        [RefusalReason.MARKER_RELOCATED],
    ),
    "segment-ambiguous beats block-type-mutation": (
        lambda: reconcile(
            THREE, edited(("p1", "# heading\n\nextra"), ("p2", "two"), ("p3", "three"))
        ),
        [RefusalReason.SEGMENT_AMBIGUOUS],
    ),
    # --- across segments: the head first, then the document's own order --------
    "the head's undecodable text is reported before a later segment's refusal": (
        lambda: reconcile(
            HEAD,
            edited((None, r"title \q"), ("p1", "changed\n\nadded"), ("p2", "two")),
        ),
        [RefusalReason.UNDECODABLE_TEXT, RefusalReason.SEGMENT_AMBIGUOUS],
    ),
    "the head's changed content is reported before a later segment's refusal": (
        lambda: reconcile(
            HEAD,
            edited((None, "other title"), ("p1", "changed\n\nadded"), ("p2", "two")),
        ),
        [RefusalReason.UNMARKED_CONTENT_CHANGED, RefusalReason.SEGMENT_AMBIGUOUS],
    ),
    "two segment refusals come back in the document's block order": (
        lambda: reconcile(
            THREE, edited(("p1", "changed\n\nadded"), ("p2", "two"), ("p3", ""))
        ),
        [RefusalReason.SEGMENT_AMBIGUOUS, RefusalReason.MARKER_ORPHANED],
    ),
    # --- the conservation check runs LAST, over the assembled plan -------------
    "the conserved-block check is appended after the per-segment refusals": (
        lambda: reconcile(
            opaque_projection(TABLE, "table"),
            edited(("p0", "one"), (None, TABLE), ("p1", "changed\n\nadded")),
            absent=DELETE,
        ),
        [RefusalReason.SEGMENT_AMBIGUOUS, RefusalReason.CONSERVED_BLOCK_RE_CREATED],
    ),
    # --- the disposition switches the absence stage off entirely ---------------
    "the deletion disposition skips absence and lets the diff's refusal through": (
        lambda: reconcile(
            THREE, edited(("p1", "changed\n\nadded"), ("p2", "two")), absent=DELETE
        ),
        [RefusalReason.SEGMENT_AMBIGUOUS],
    ),
}

#: The pairs enumerated from the body that are **not** testable because they cannot both
#: hold — recorded so the enumeration is complete and reviewable, rather than silently
#: short. Each value is the argument for the impossibility.
UNREACHABLE_PAIRS = {
    ("marker-orphaned", "marker-relocated"): (
        "orphaned needs the segment to come back with NO content; relocated needs that "
        "same content to be another block's text, and a block with no units cannot hold "
        "one. The relocation scan also skips a candidate whose own units are empty."
    ),
    ("marker-orphaned", "block-type-mutation"): (
        "the type comparison classifies the edited Markdown, and orphaned means there is "
        "none to classify."
    ),
    ("marker-dropped", "marker-absent"): (
        "per block they are the two readings of one absence and are decided by a single "
        "if/else — they co-occur only across DIFFERENT blocks, which is pinned above."
    ),
    ("undecodable-text", "any other refusal for the SAME segment"): (
        "the decode happens first and returns, so the segment never reaches a comparison "
        "— it co-occurs only across different segments, pinned above."
    ),
    ("not-in-dialect", "block-type-mutation"): (
        "the type comparison needs both sides classified, and a side the dialect cannot "
        "express raises out of the classifier before the comparison exists."
    ),
    ("conserved-block-re-created", "marker-absent"): (
        "the conservation check needs the absence stage to have passed, which under the "
        "default disposition it does not when a marker is absent; the reachable pairing "
        "is with the deletion disposition, pinned above."
    ),
}


@pytest.mark.parametrize("name", sorted(PRECEDENCE_CASES))
def test_which_refusal_wins_is_what_it_was(name):
    call, expected = PRECEDENCE_CASES[name]
    plan = call()
    assert reasons(plan) == expected, name
    assert plan.entries == (), name


def test_the_unreachable_pairs_are_named_with_their_argument():
    """The enumeration's other half: a pair left out of the precedence table must be here
    with a reason, so 'not tested' is never indistinguishable from 'not thought about'."""
    assert len(UNREACHABLE_PAIRS) == 6
    for pair, why in UNREACHABLE_PAIRS.items():
        assert len(pair) == 2 and all(pair)
        assert len(why) > 40, pair
