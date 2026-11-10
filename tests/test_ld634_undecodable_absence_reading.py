"""LD-634 / D-116 — an undecodable unit elsewhere in a segment must not change WHICH
absence reading stage 3 reports.

``_decoded_units`` answers ``None`` for text it cannot decode and a list otherwise, and its
own docstring states the rule: undecodable text *"is not comparable, which is a different
fact and one the caller must not read as evidence either way."* ``_all_units`` read it as
evidence — ``if decoded:`` treated ``None`` (undecodable) identically to ``[]`` (decodable,
empty) and dropped the WHOLE segment from the corpus stage 3 uses to tell a **dropped
marker** from an **absent** block. Because stage 3 runs before stage 4, where
``undecodable-text`` is raised, the consumer was told their block had *vanished* and was
never told the thing actually blocking them.

**It is a diagnosability defect, not a write-safety one** (`D-116`): both readings refuse
and nothing is written. What was lost is the narrower, ACTIONABLE reason.

The controlled pair below is the audit's own reproduction (`arm-B-reconcile.md` R2),
differing by one line, and it is the permanent regression. The third case is the other half
of honesty and is the reason an undecodable unit is held as an INCOMPARABLE PLACEHOLDER
rather than skipped: text that came back split by something unreadable did not "plainly come
back", so the units either side of it may not close over the gap and manufacture a
``marker-dropped``. `D-116` bounds the fix — the stage order stands, and hoisting
undecodability to a stage 0 is a parked product decision.

**The bound as `D-116` and AC1 first wrote it — *every* existing refusal verdict is
preserved — was the wrong bound, and QA's measurement is why** (2026-09-03; see the AC
correction on `LD-634`). A fix that corrects a false verdict necessarily moves that
verdict, and there turned out to be a second document shape where it moves in the
opposite direction: a block whose text comes back **split by a whole undecodable
segment** read ``marker-dropped`` before the fix and reads ``marker-absent`` after it.
That is the last test in this file, and it is pinned here rather than argued about. The
two shapes named in this file are the ones measured to move against the pre-fix code; no
claim is made here about document shapes nobody ran.
"""
import pytest

from larkdocio.model.projection import BlockIdProjection
from larkdocio.write.reconcile import _decoded_units, reconcile

# The one line that makes a unit undecodable: a backslash escape the projection's own
# inverse refuses rather than guesses at. Not a hand-picked string — the premise is
# asserted below, so this pair cannot pass by being two identical documents.
UNDECODABLE_UNIT = "\\q undecodable"

PROJECTION = BlockIdProjection(
    markdown="<!-- lark:block:b1 -->\nAlpha.\n\n<!-- lark:block:b2 -->\nBeta.\n",
    block_ids=("b1", "b2"),
    opaque_block_ids=(),
)

# b2's marker dropped; its text plainly came back under b1's marker.
CONTROL = "<!-- lark:block:b1 -->\nAlpha.\n\nBeta.\n"
# The identical situation, plus ONE undecodable unit elsewhere in the same segment.
VARIANT = f"<!-- lark:block:b1 -->\nAlpha.\n\nBeta.\n\n{UNDECODABLE_UNIT}\n"


def _reasons(plan):
    return [r.reason.value for r in plan.refusals]


def test_the_premise_the_added_unit_really_is_undecodable_and_the_control_really_is_not():
    """The positive binding: the pair differs in the way the test claims it does.

    Without this the two documents could differ in nothing that matters and every
    assertion below would pass vacuously.
    """
    assert _decoded_units(UNDECODABLE_UNIT) is None
    assert _decoded_units("Beta.") == ["Beta."]
    assert CONTROL != VARIANT


def test_the_control_reports_the_narrower_actionable_dropped_marker_reading():
    plan = reconcile(PROJECTION, CONTROL)
    assert not plan.ok
    assert _reasons(plan) == ["marker-dropped"]
    assert "the block's own text came back with it" in plan.refusals[0].detail


def test_an_undecodable_unit_elsewhere_does_not_downgrade_the_reading_to_marker_absent():
    """The defect, as the regression. Watched red before the fix: ``['marker-absent']``."""
    plan = reconcile(PROJECTION, VARIANT)
    assert not plan.ok
    assert _reasons(plan) == ["marker-dropped"]
    assert "the block's own text came back with it" in plan.refusals[0].detail


def test_the_pair_agrees_reason_for_reason_which_is_the_property_under_test():
    control = reconcile(PROJECTION, CONTROL)
    variant = reconcile(PROJECTION, VARIANT)
    assert _reasons(control) == _reasons(variant)
    assert control.refusals[0].detail == variant.refusals[0].detail


def test_undecodable_text_is_not_evidence_of_presence_either_a_split_run_stays_absent():
    """The other direction of *"not evidence either way"*, and the verdict it preserves.

    b2's two units come back with something unreadable BETWEEN them. Its text did not
    plainly come back — part of what sits in the middle cannot be read at all — so the
    reading stays ``marker-absent``, exactly as it did before this fix. Skipping the
    undecodable unit instead of standing a placeholder in its place would let the two
    halves close the gap and report a ``marker-dropped`` that is not true.
    """
    projection = BlockIdProjection(
        markdown=("<!-- lark:block:b1 -->\nAlpha.\n\n"
                  "<!-- lark:block:b2 -->\nBeta.\n\nGamma.\n"),
        block_ids=("b1", "b2"),
        opaque_block_ids=(),
    )
    edited = (f"<!-- lark:block:b1 -->\nAlpha.\n\nBeta.\n\n{UNDECODABLE_UNIT}\n\nGamma.\n")
    plan = reconcile(projection, edited)
    assert not plan.ok
    assert _reasons(plan) == ["marker-absent"]

    # Positive binding: the same two units, contiguous, ARE found — so the assertion above
    # is about the gap and not about b2 being unfindable in principle.
    contiguous = "<!-- lark:block:b1 -->\nAlpha.\n\nBeta.\n\nGamma.\n"
    assert _reasons(reconcile(projection, contiguous)) == ["marker-dropped"]


@pytest.mark.parametrize("edited", [
    # A block that really is gone, with an undecodable unit in the document: the alarming
    # reading is the correct one here and it must survive the fix.
    f"<!-- lark:block:b1 -->\nAlpha.\n\n{UNDECODABLE_UNIT}\n",
])
def test_a_genuinely_absent_block_still_reads_marker_absent(edited):
    plan = reconcile(PROJECTION, edited)
    assert not plan.ok
    assert _reasons(plan) == ["marker-absent"]


def test_a_run_split_by_a_whole_undecodable_segment_moves_from_dropped_to_absent():
    """The verdict this fix DOES move, named: ``marker-dropped`` -> ``marker-absent``.

    Found by QA (2026-09-03) by measurement against ``develop`` at the time, not by
    argument, and unpinned by anything until this test. It is the same defect as the one
    above, seen from the other side: the undecodable text is a WHOLE segment of its own,
    so the pre-fix per-segment skip removed only that segment — and b2's two units, which
    the edit left on either side of it, closed the gap and read as a contiguous run. The
    consumer was told ``marker-dropped``, *"the block's own text came back with it"*, on the
    strength of a stretch of Markdown nobody could decode.

    Per unit, that gap is an incomparable placeholder that holds its position, so the run
    is not contiguous and the reading is ``marker-absent``. **That is the honest reading**
    — undecodable text is not evidence a block's text came back whole any more than it is
    evidence the text is gone (``_decoded_units``' own docstring). Both readings refuse and
    nothing is written on either; what moves is which reason the consumer is given.

    Watched red before the fix (`_all_units` restored to ``if decoded:`` over whole
    segments): this test reports ``['marker-dropped']``.
    """
    projection = BlockIdProjection(
        markdown=("<!-- lark:block:b1 -->\nAlpha.\n\n"
                  "<!-- lark:block:b2 -->\nBeta.\n\nGamma.\n\n"
                  "<!-- lark:block:b3 -->\nDelta.\n\n"
                  "<!-- lark:block:b4 -->\nEpsilon.\n"),
        block_ids=("b1", "b2", "b3", "b4"),
        opaque_block_ids=(),
    )
    # b2's marker is gone and its two units are split apart by b3's segment, which is
    # undecodable in its entirety.
    edited = ("<!-- lark:block:b1 -->\nAlpha.\n\nBeta.\n\n"
              f"<!-- lark:block:b3 -->\n{UNDECODABLE_UNIT}\n\n"
              "<!-- lark:block:b4 -->\nGamma.\n\nEpsilon.\n")
    plan = reconcile(projection, edited)
    assert not plan.ok
    assert _reasons(plan) == ["marker-absent"]

    # Positive binding, and it is the whole ``None`` vs ``[]`` distinction in two lines:
    # make that middle segment decodable-but-EMPTY instead of undecodable and the two
    # units really are adjacent in the corpus, so the same document reads
    # ``marker-dropped``. So the assertion above is about the segment being UNDECODABLE,
    # not about b2 being unfindable across a marker in principle.
    assert _decoded_units(UNDECODABLE_UNIT) is None
    assert _decoded_units("\n") == []
    empty_middle = ("<!-- lark:block:b1 -->\nAlpha.\n\nBeta.\n\n"
                    "<!-- lark:block:b3 -->\n\n"
                    "<!-- lark:block:b4 -->\nGamma.\n\nEpsilon.\n")
    assert _reasons(reconcile(projection, empty_middle)) == ["marker-dropped"]
