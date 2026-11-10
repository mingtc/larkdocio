"""Offline guards for THE ROUND-TRIP GATE arm 3 — live ``STALE_DOCUMENT`` (LD-236 AC3).

NOT marked ``live_write``: always-on. Beyond the ring's shared discipline these pin the three
properties that make the arm a real concurrency proof rather than a document editing itself:
the drift comes from a **second client**, the refusal is measured as **zero writes at the
client boundary**, and the arm proves the **recovery** — a refusal with no recovery leg would
document a dead end.
"""
import gate_shape

GATE = "test_live_write_round_trip_stale_document_gate.py"


def test_the_stale_document_arm_keeps_the_rings_discipline():
    gate_shape.assert_ring_discipline(GATE)


def test_the_drift_comes_from_a_genuinely_second_client():
    src = gate_shape.gate_source(GATE)
    assert "other_client" in src and src.count("WriteClient(*get_write_credentials()") >= 2, (
        "the out-of-band edit must come from a SECOND client object with its own token fetch "
        "and its own transport — otherwise the arm is a document editing itself.")


def test_the_arm_arms_the_guard_and_measures_zero_writes():
    src = gate_shape.gate_source(GATE)
    assert "document_revision_id=revision" in src and 'revision_guard == "active"' in src, (
        "the whole-document guard must be ARMED with the revision the read handed back, and "
        "the arm must assert it is active — the guard is never silently off.")
    assert "rt.measured_writes(" in src and "writes == []" in src, (
        "zero writes must be MEASURED at the client boundary, not inferred from a diff.")
    assert "STALE_DOCUMENT" in src, "the refusal must be asserted by its typed reason"


def test_the_arm_proves_the_refusal_is_recoverable():
    src = gate_shape.gate_source(GATE)
    assert "RECOVERY" in src and "rt.apply_edited_projection(" in src, (
        "AC3 ends with 're-plan proceeds': the arm must re-download, re-project, re-plan and "
        "apply, or it documents a dead end instead of a recoverable refusal.")
    assert "byte_unchanged_after_refusal" in src, (
        "the refused batch must leave the document byte-unchanged, and the arm must say so.")
