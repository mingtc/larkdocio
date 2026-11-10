"""Offline guards for THE LD-574 GATE — the todo checkbox arm.

NOT marked ``live_write``: always-on. Beyond the ring's shared discipline these pin the four
properties that make the arm a proof of the shipped op rather than a restatement of the
citation it was built from: the read-back is of the **RAW payload** (the properties the mask
must leave alone are not all projected into Markdown), it compares the **untouched**
properties by name and not merely the moved one, it asserts the flip costs **one** call (a
second would mean the text was rewritten and a styled item flattened), and it **restores**.
"""
import gate_shape

GATE = "test_live_write_todo_done_edit_gate.py"


def test_the_todo_done_arm_keeps_the_rings_discipline():
    gate_shape.assert_ring_discipline(GATE)


def test_the_read_back_is_of_the_RAW_PAYLOAD_not_of_the_markdown():
    src = gate_shape.gate_source(GATE)
    assert "rt.raw_block_payload(" in src, (
        "``align`` and ``folded`` are not projected into Markdown at all, so a Markdown-only "
        "read-back cannot see the properties the field mask is claimed to leave alone.")
    for prop in ('"align"', '"folded"', '"children"'):
        assert prop in src, f"{prop} is not compared, so its blast radius is unmeasured"


def test_the_arm_asserts_the_UNTOUCHED_properties_and_not_only_the_moved_one():
    src = gate_shape.gate_source(GATE)
    assert "before[target_id][prop]" in src, (
        "the arm must compare each named property against its own pre-image — asserting "
        "only that `done` moved would prove nothing about what else did.")
    assert "after[child_id] == before[child_id]" in src, (
        "the nested child is the half of the measurement a flat todo cannot test.")


def test_the_arm_measures_ONE_write_and_asserts_the_preview_and_the_log_carry_the_bit():
    src = gate_shape.gate_source(GATE)
    assert 'result["writes"] == ["_patch_block"]' in src, (
        "a pure flip must cost exactly one call: a second means the block's own text was "
        "rewritten, which flattens a styled item's runs for the sake of a boolean.")
    assert "for e in result[\"preview\"].entries] == [True]" in src, (
        "a preview that shows a text edit while the apply moves a bit is the same "
        "silent-success defect one layer over.")
    assert "for e in log.entries] == [True]" in src, (
        "on a pure flip before == after, so the receipt has to say what moved.")


def test_the_arm_restores_and_re_reads_the_payload():
    src = gate_shape.gate_source(GATE)
    assert "restored == baseline" in src and "todo_done is False" in src, (
        "the reverse flip is the other half of the op; an arm that only ticks has not "
        "shown the mask writes False as well as True.")
