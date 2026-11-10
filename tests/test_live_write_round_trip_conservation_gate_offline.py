"""Offline guards for THE ROUND-TRIP GATE arm 2 — conservation (LD-236 AC2, maintainer-widened).

NOT marked ``live_write``: always-on. Beyond the ring's shared discipline these pin the two
things the **maintainer ruling of 2026-08-03** made non-negotiable, because getting either wrong is how
this arm reports GREEN over a document-duplicating defect:

1. the subject is an opaque kind ``compose()`` **can create** (a table or a mermaid block), not
   an image — an image refuses ``not-in-dialect`` later, at compile, for unrelated reasons, so
   an image-only arm never reaches the conservation decision at all;
2. **both** omission shapes are covered — marker *and* content omitted, and marker omitted with
   content kept (LD-238's shape).
"""
import gate_shape

GATE = "test_live_write_round_trip_conservation_gate.py"


def test_the_conservation_arm_keeps_the_rings_discipline():
    gate_shape.assert_ring_discipline(GATE)


def test_the_conservation_arms_subject_is_an_opaque_kind_compose_can_create():
    src = gate_shape.gate_source(GATE)
    assert "opaque=table" in src or "opaque=mermaid" in src, (
        "AC2 (widened): the subject must be an opaque kind compose() CAN create — a table or a "
        "mermaid block. An image arm cannot detect the LD-238 shape and would go green over it.")
    assert "rt.seed_markdown(" in src, (
        "the opaque block must be authored FROM MARKDOWN through the plan gate — that is what "
        "makes it a block the dialect can create, and therefore one a re-creation could "
        "duplicate.")


def test_the_conservation_arm_covers_BOTH_omission_shapes():
    src = gate_shape.gate_source(GATE)
    assert "SHAPE (a)" in src and "SHAPE (b)" in src, (
        "AC2 requires two omission shapes, not one: marker+content omitted, and marker omitted "
        "with the content kept (LD-238).")
    assert "CONSERVED_BLOCK_RE_CREATED" in src, (
        "shape (b) must assert the typed conserved-block-re-created refusal — the live "
        "counterpart of LD-235 AC9.")
    assert "ReconciliationState.INSERTED not in" in src, (
        "shape (a) must assert that NOTHING was planned as an insert: a conserved block "
        "re-created beside itself is the document-duplicating defect this arm exists to catch.")


def test_the_conservation_arm_proves_the_block_is_still_there_afterwards():
    src = gate_shape.gate_source(GATE)
    assert "byte-identical" in src and "rt.download(" in src, (
        "conservation is a claim about the LIVE document after the apply, so the arm must "
        "re-download and prove the block came back byte-identical.")
    assert 'result_b["writes"] == []' in src, (
        "shape (b) refuses the whole batch, so its zero-write claim must be asserted, not "
        "assumed.")
