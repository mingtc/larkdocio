"""Offline guards for THE ROUND-TRIP GATE arm 4 — no marker reaches Lark (LD-236 AC4).

NOT marked ``live_write``: always-on. Beyond the ring's shared discipline these pin what makes
the scan meaningful: it covers **both** representations (the raw stored payload and the
reader's re-rendered Markdown), it scans the **whole** document rather than the block that was
written, and it carries an **adversarial control** whose marker-shaped text must survive
unchanged — the control is what turns "no markers found" from a statement about Lark into a
statement about our strip.

The control's scoping is also pinned: a **non-emitted** id, **mid-line** — the shape a real
consumer's prose about markers has, and the one that can assert survival rather than absence.

Since LD-239 the arm also carries the **mid-line refusal leg**: the same position with
membership flipped (a marker for a block the projection DID emit) is refused, with zero writes
and a byte-identical document across the attempt. That leg is pinned here too, because "the
guard refuses" is only worth as much as the live document it is read off.
"""
import gate_shape

GATE = "test_live_write_round_trip_no_marker_gate.py"


def test_the_no_marker_arm_keeps_the_rings_discipline():
    gate_shape.assert_ring_discipline(GATE)


def test_the_arm_scans_BOTH_representations_of_the_whole_document():
    src = gate_shape.gate_source(GATE)
    assert "rt.raw_block_payload(" in src, (
        "AC4 requires the RAW block payload to be scanned as well: a marker could survive in "
        "stored text the Markdown never renders.")
    assert "rt.download(" in src, (
        "…and the reader's re-rendered Markdown, which is the representation a consumer "
        "actually sees.")
    assert "for block_id in emitted:" in src, (
        "the scan must cover EVERY emitted id over the WHOLE document, not just the block the "
        "reconciliation wrote.")


def test_the_arm_carries_an_adversarial_control_that_must_survive():
    src = gate_shape.gate_source(GATE)
    assert "CONTROL_ID" in src and "CONTROL_LINE in markdown" in src, (
        "the control's legitimate marker-shaped text must be asserted to survive the round "
        "trip verbatim — without it, a zero result could just mean Lark strips markers.")
    assert "CONTROL_ID not in emitted" in src, (
        "the control must name an id the projection NEVER emitted, or the arm is asserting a "
        "contradiction (that an emitted marker both must and must not be present).")


def test_the_arm_carries_the_ld_239_mid_line_refusal_leg():
    """The leg the guard's position-independence is read off: an EMITTED block's marker,
    mid-line, refused — with the proof taken from the live document (zero writes, byte-
    identical Markdown) rather than from the compiler that raised."""
    src = gate_shape.gate_source(GATE)
    assert "pytest.raises(RefusedError)" in src, (
        "the mid-line marker for an EMITTED block must be asserted to REFUSE — that is the "
        "shape LD-239 fixed, and an arm that only tests the non-emitted control cannot see "
        "it.")
    assert "rt.measured_writes(" in src and "assert attempted == []" in src, (
        "zero writes must be MEASURED on the refused attempt, not inferred from the raise.")
    assert "assert after == before" in src, (
        "the document must be byte-identical across the refused attempt — that is what "
        "'nothing reached Lark' means.")


def test_the_control_marker_is_mid_line_non_emitted_which_is_what_tests_ac4():
    """The control text must not begin with its marker: a line-leading marker for a non-emitted
    id is refused ``marker-invented`` by the reconciler, and a line-leading marker for an
    emitted one is a marker line. Mid-line, non-emitted is the one shape that tests AC4."""
    src = gate_shape.gate_source(GATE)
    control = next(line for line in src.splitlines() if line.startswith("CONTROL_LINE = ("))
    assert control, "the arm must define CONTROL_LINE"
    body = src.split("CONTROL_LINE = (", 1)[1].split("\n)", 1)[0]
    assert "Adversarial control" in body and body.index("Adversarial control") < body.index(
        "block_id_marker(CONTROL_ID)"), (
        "the marker-shaped text must sit MID-LINE, after real prose (LD-239 scoping).")


def test_the_arm_checks_the_compiled_requests_before_they_are_sent():
    src = gate_shape.gate_source(GATE)
    assert "compiled_marker_hits" in src, (
        "the pre-flight check (no compiled request body carries a marker) is cheap and it "
        "localizes a failure to the compiler rather than to the platform.")
