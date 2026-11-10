"""Offline guards for THE ROUND-TRIP GATE arm 5 — escape identity on an untouched line (LD-454).

NOT marked ``live_write``: these run in the default ``pytest -q`` with no creds and no network.
They pin the *shape* of the credential-gated arm so a later edit cannot quietly break the
discipline it depends on, and — the half that matters most on this arm — that its **teeth are
real**. The binding round trip itself runs only under ``pytest -m live_write``.
"""
import gate_shape

GATE = "test_live_write_round_trip_escape_identity_gate.py"


def test_the_escape_identity_arm_keeps_the_rings_discipline():
    gate_shape.assert_ring_discipline(GATE)


def test_the_escape_identity_arm_goes_through_the_shipped_chain():
    src = gate_shape.gate_source(GATE)
    assert "rt.project(" in src and "rt.apply_edited_projection(" in src, (
        "the arm must run the SHIPPED chain (project → reconcile → compile → dry_run → apply) "
        "— a gate that hand-rolls the good path is not testing the round trip.")


def test_the_escape_identity_arm_proves_the_projection_really_escaped_the_line():
    """Without this the arm could pass on a document whose code block carried nothing the
    policy escapes — a green run over a subject that cannot exhibit the defect."""
    src = gate_shape.gate_source(GATE)
    assert "CORRUPTED_LINE in projection.markdown" in src, (
        "the arm must assert the projection DID escape the untouched line before it claims "
        "anything about decoding it again.")


def test_the_escape_identity_arm_reads_the_line_back_off_the_document():
    """The verdict is the re-read, in BOTH representations: the reader's Markdown and the raw
    block payload. A block could store the backslashes while the reader's own escaping hid
    them, which is exactly how this defect stayed invisible for a release."""
    src = gate_shape.gate_source(GATE)
    assert "CORRUPTED_LINE not in after" in src
    assert "rt.raw_block_payload(" in src and "CORRUPTED_LINE not in payload" in src


def test_the_escape_identity_arm_carries_a_forced_defect_control():
    """AC4's second half, automated: the arm re-creates the PRE-FIX compile in place (compose
    the same plan, ship the composed body without the verbatim decode), applies it, and asserts
    the corruption really appears. A gate never shown failing on its own defect is not known to
    detect it — and reverting the fix by hand is not something a later run will do."""
    src = gate_shape.gate_source(GATE)
    assert "compose(entry.after_markdown)" in src, (
        "the control must be the pre-fix compile itself, not a hand-typed escaped string.")
    assert "assert CORRUPTED_LINE in corrupted" in src, (
        "the control must assert the corruption REPRODUCED — a control whose failure mode is "
        "silence proves nothing.")
    assert "defect_reproduced" in src and "forced_defect_replacement" in src, (
        "both halves of the two-sided proof must be printed into the evidence line.")


def test_the_escape_identity_arm_repairs_what_its_control_broke():
    src = gate_shape.gate_source(GATE)
    assert "assert CORRUPTED_LINE not in final" in src and "UNTOUCHED_LINE in final" in src, (
        "the arm must repair the document through the shipped chain and verify the repair — "
        "leaving a deliberately corrupted block behind would be a defect the teardown hides.")
