"""Offline guards for THE ROUND-TRIP GATE arm 1 — the surgical round trip (LD-236 AC1).

NOT marked ``live_write``: these run in the default ``pytest -q`` with no creds and no network.
They pin the *shape* of the credential-gated arm so a later edit cannot quietly break the
discipline it depends on. The binding round trip itself runs only under ``pytest -m live_write``.
"""
import gate_shape

GATE = "test_live_write_round_trip_surgical_gate.py"


def test_the_surgical_arm_keeps_the_rings_discipline():
    gate_shape.assert_ring_discipline(GATE)


def test_the_surgical_arm_goes_through_the_shipped_chain_and_nothing_else():
    src = gate_shape.gate_source(GATE)
    assert "rt.project(" in src and "rt.apply_edited_projection(" in src, (
        "the arm must run the SHIPPED chain (project → reconcile → compile → dry_run → apply) "
        "— a gate that hand-rolls a request is not testing the round trip.")
    assert "_patch_block" in src, (
        "the arm must measure the writes at the client boundary: a one-block text edit is ONE "
        "patch, and 'surgical' is not a claim you can make without counting.")


def test_the_surgical_arm_proves_the_diff_AND_the_restore():
    """AC1 has two halves and the second is the one an arm is tempted to skip: it is not enough
    that the intended line changed — the round trip must be reversible to a byte-identical
    baseline, or 'surgical' only means 'the edit landed'."""
    src = gate_shape.gate_source(GATE)
    assert "rt.changed_lines(" in src, "the arm must diff the re-download against the baseline"
    assert "restored == baseline" in src, (
        "the arm must restore the document and assert BYTE-identity with the baseline (AC1).")
