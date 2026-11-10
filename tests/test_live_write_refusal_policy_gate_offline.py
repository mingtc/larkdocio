"""Offline guards for THE REFUSAL-POLICY GATE (LD-458 AC7).

NOT marked ``live_write``: these run in the default ``pytest -q`` with no creds and no network.
They pin the *shape* of the credential-gated arm so a later edit cannot quietly break the
discipline it depends on. The policy's own behavior is pinned offline in
``tests/test_apply_refusal_policy.py``; what only a round trip can prove — and what this
companion therefore guards the shape of — is that the raise did not move **which entries
land**.
"""
import gate_shape

GATE = "test_live_write_refusal_policy_gate.py"


def test_the_refusal_policy_arm_keeps_the_rings_discipline():
    gate_shape.assert_ring_discipline(GATE)


def test_the_arm_drives_BOTH_shapes_the_raise_and_the_opt_in():
    """One arm proving only the raise would leave the ruling's other half — that
    ``allow_partial=True`` returns exactly what ``apply()`` always returned — unproved live."""
    src = gate_shape.gate_source(GATE)
    assert "pytest.raises(LarkApplyRefusedError)" in src, "the DEFAULT arm must be the raise"
    assert "allow_partial=True" in src, "the OPT-IN arm must be driven too"


def test_the_arm_COMPARES_the_two_read_backs_rather_than_asserting_each_alone():
    """The claim is *nothing about the writes changed*. Two independent per-document
    assertions cannot say that; comparing the two read-backs can."""
    src = gate_shape.gate_source(GATE)
    assert 'evidence["raise_body"] == evidence["opt_in_body"]' in src, (
        "the arm must compare the two documents' read-back bodies — that comparison IS the "
        "claim the ruling rests on.")
    assert "rt.download(" in src, "and both bodies must come from a real read-back"


def test_the_arm_proves_the_APPLIED_entry_was_not_rolled_back_by_the_raise():
    """A raise that undid the applied entry would be a rollback, which this library never
    does — so the raising arm reads its document back and asserts the edit is still there."""
    src = gate_shape.gate_source(GATE)
    assert "EDITED in raised_markdown" in src
    assert '"NEVER APPLIED" not in raised_markdown' in src, (
        "and the refused entry must be proved to have written nothing")


def test_the_arm_asserts_the_error_CARRIES_the_record_it_replaces():
    """The whole justification for raising instead of returning is that nothing is lost: the
    log, what applied, and each refusal's reason + detail all travel on the exception."""
    src = gate_shape.gate_source(GATE)
    for probe in ("error.applied", "error.refused", "error.refusals[0][\"reason\"]",
                  "len(error.log)"):
        assert probe in src, probe
    assert "1 of 2 entries applied; 1 refused" in src, (
        "the message must be asserted to name the count both ways")


def test_the_refusable_entry_is_the_MEASURED_shape_not_an_invented_one():
    """The ruling was written from an ambiguous-quote refusal that a consumer discarded. The
    arm reproduces that shape rather than inventing a cheaper one."""
    src = gate_shape.gate_source(GATE)
    assert "RefusalReason.AMBIGUOUS" in src
    assert 'error.refusals[0]["reason"] == "ambiguous-N-candidates"' in src


def test_the_arm_provisions_its_own_disposables_and_empties_them_in_a_finally():
    src = gate_shape.gate_source(GATE)
    assert src.count("docx_ledger.disposable(") == 2, (
        "two documents, both created by this arm — the comparison needs two, and neither may "
        "be a document anyone owns")
    assert src.count("rt.empty_document(") == 2 and src.count("finally:") >= 3
    assert "docx_ledger.close_out(" in src and "raise_if_orphans()" in src
