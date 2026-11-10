"""Offline guards for THE ANCHOR SOFT-RETURN GATE (LD-455 AC5).

NOT marked ``live_write``: these run in the default ``pytest -q`` with no creds and no network.
They pin the *shape* of the credential-gated arm so a later edit cannot quietly break the
discipline it depends on — and, the half this arm is the first to need, that it **proves its
own premise on the wire** before claiming anything built on it. The binding round trip itself
runs only under ``pytest -m live_write``.
"""
import gate_shape

GATE = "test_live_write_anchor_whitespace_gate.py"


def test_the_anchor_whitespace_arm_keeps_the_rings_discipline():
    gate_shape.assert_ring_discipline(GATE)


def test_the_arm_proves_the_soft_return_is_REALLY_STORED_before_claiming_anything():
    """The whole defect rests on one API fact — that Lark keeps a literal newline inside a
    single text run. An arm that assumed it would be asserting its own author's belief, and
    would pass green on a tenant where the newline had been split into two blocks."""
    src = gate_shape.gate_source(GATE)
    assert "stored == SOFT_RETURN_TEXT" in src, (
        "the arm must read the block back and assert the newline survived INSIDE one block "
        "before it tests either behaviour built on that fact.")
    assert "len(body.splitlines()) == 2" in src, (
        "and it must assert the projection really shows that block as TWO lines — a "
        "one-line subject cannot exhibit the line-splice garble.")


def test_the_arm_measures_ZERO_WRITES_for_the_refusal_leg():
    """Arm A's claim is that a near-miss refuses. "Refuses" means nothing was written, and
    that is measured at the client boundary rather than inferred from a later diff."""
    src = gate_shape.gate_source(GATE)
    assert "rt.measured_writes(" in src and "assert writes == []" in src


def test_the_arm_asserts_the_refusal_NAMES_the_block_and_drops_the_circular_remedy():
    src = gate_shape.gate_source(GATE)
    assert "differs only in whitespace" in src
    assert "repr(stored) in refusal.detail" in src, (
        "naming the block without showing its stored spelling leaves the consumer with "
        "'your whitespace is wrong' and no way to see which whitespace.")
    assert "re-read the document and copy the quote verbatim" in src, (
        "the arm must assert the superseded circular remedy is ABSENT — the sentence has to "
        "appear here to be asserted against.")


def test_the_arm_carries_a_FORCED_DEFECT_control_and_then_repairs_it():
    """A gate never shown failing on its own defect is not known to detect it, and reverting
    the fix by hand is not something a later run will do. So the arm re-creates the recipe's
    OLD line-splice idiom in place, applies it, and asserts the document really comes back
    garbled — then repairs the same block through the block-safe splice and reads it back."""
    src = gate_shape.gate_source(GATE)
    assert "splitlines(keepends=True)" in src, (
        "the forced defect IS the old line-splice idiom; it has to be re-created literally.")
    assert 'stored2.count("Q3.") == 2' in src, (
        "the control must assert the garble REALLY appeared — an unasserted control proves "
        "nothing.")
    assert "replace_block_markdown(" in src and "stored3 == CORRECT_EDIT" in src, (
        "and the repair must go through the shipped block-safe splice and be READ BACK, "
        "because the whole point is that plan.ok was already True for the garbled one.")


def test_the_arm_goes_through_the_shipped_chain():
    src = gate_shape.gate_source(GATE)
    assert "rt.project(" in src and "rt.apply_edited_projection(" in src, (
        "the arm must run the SHIPPED chain (project → reconcile → compile → dry_run → apply) "
        "— a gate that hand-rolls the good path is not testing the round trip.")
