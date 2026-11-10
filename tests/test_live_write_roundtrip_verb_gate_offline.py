"""Offline guards for THE LD-492 GATE — the round-trip verb's live arm (AC9).

NOT marked ``live_write``: these run in the default ``pytest`` with no credentials and no
network. They pin the *shape* of the credential-gated arm — and, because AC9's live half is
parked in this session for a missing precondition, they are also **the proof that the arm's
skip path fires**, loudly and by name, rather than the arm quietly passing while doing nothing.

A source-text check is a weak proof of behaviour and a strong proof of **discipline**: it
cannot tell you the round trip works, but it reddens on an ordinary run the moment somebody
deletes the teardown, drops the skip, points the arm at a document it did not create, or lets
it create one with no caller-supplied destination.
"""
import gate_shape
import pytest

import canary_support

GATE = "test_live_write_roundtrip_verb_gate.py"


def test_the_roundtrip_arm_keeps_the_rings_discipline():
    gate_shape.assert_ring_discipline(GATE)


def test_the_roundtrip_arm_runs_the_SHIPPED_VERB_and_not_a_re_implementation():
    """The point of the arm is that the thing a consumer runs is the thing under test. An arm
    that called ``reconcile``/``dry_run``/``apply`` itself would prove the engine works and say
    nothing about the verb that orders them."""
    src = gate_shape.gate_source(GATE)
    assert "from larkdocio import roundtrip" in src, (
        "the arm does not import the shipped verb at all")
    for call in ("roundtrip.pull(", "roundtrip.push(workdir)",
                 "roundtrip.push(workdir, apply_changes=True)"):
        assert call in src, f"the arm does not exercise {call}"
    for hand_rolled in ("compile_reconciliation(", "dry_run(", "apply("):
        assert f"\n                {hand_rolled}" not in src, (
            f"the arm calls {hand_rolled} itself — it must go through the verb")


def test_the_roundtrip_arm_proves_the_REHEARSAL_writes_nothing():
    """The gate the verb exists for. A push without ``--apply`` must build the plan and write
    nothing, and 'nothing' is measured at the client boundary AND re-read from the document —
    a claim of zero writes that only inspects a return value proves nothing."""
    src = gate_shape.gate_source(GATE)
    assert "rt.measured_writes(" in src, (
        "the arm does not count writes at the client boundary during the rehearsal")
    assert "rehearsal.applied is False" in src
    assert "unchanged == baseline" in src, (
        "the arm never re-reads the document after the rehearsal — a preview that silently "
        "wrote would pass")


def test_the_roundtrip_arm_proves_the_SURGICAL_diff_and_the_VERBS_OWN_verification():
    """Two different claims, and the arm owes both: the document changed only where it was
    meant to (measured independently, by diffing a re-download against the baseline), and the
    verb's own compose-equivalence read-back agreed — with a non-empty verified list, because
    a verification that verified nothing is not clean."""
    src = gate_shape.gate_source(GATE)
    assert "rt.changed_lines(" in src and "after.replace(EDITED_LINE, TARGET_LINE) == baseline" in src
    assert "pushed.verification.ok" in src
    assert "pushed.verification.verified" in src, (
        "the arm accepts an empty verified list as a clean read-back")
    assert 'revision_guard == "active"' in src, (
        "the arm never asserts the staleness guard was armed from the snapshot")


def test_the_roundtrip_arm_is_BORN_CONFORMING_to_the_caller_supplied_destination_rule():
    """LD-493's house half, and the reason LD-492 was sequenced after it. The arm names the
    destination it creates its disposable in, explicitly, and takes it from the one env var the
    rule designates — never from a default, and never from the application's own space."""
    src = gate_shape.gate_source(GATE)
    assert "canary_support.require_disposables_folder()" in src, (
        "the arm does not obtain the caller-supplied disposables folder")
    assert "folder_token=folder_token" in src, (
        "the arm does not PASS the destination to the create — obtaining it and not using it "
        "is the same silent default the rule removes")


def test_the_arms_SKIP_PATH_fires_loudly_when_the_disposables_folder_is_unset(monkeypatch):
    """**The proof that a parked live half is parked and not silently green.**

    With ``LARKDOCIO_DISPOSABLES_FOLDER`` unset, a harness that creates objects must skip with
    a message that NAMES the variable. This drives the real helper the arm calls, so the arm's
    behaviour is what is being demonstrated — not a paraphrase of it.
    """
    monkeypatch.delenv(canary_support.DISPOSABLES_FOLDER_ENV, raising=False)
    assert canary_support.disposables_folder() is None
    reason = canary_support.disposables_folder_missing_reason()
    assert reason and canary_support.DISPOSABLES_FOLDER_ENV in reason, reason
    # `pytest.skip` raises `Skipped`, which derives from BaseException — so `raises(Exception)`
    # here would NOT catch it and this test would itself be reported as skipped, which is the
    # very failure mode it exists to rule out. Named explicitly for that reason.
    from _pytest.outcomes import Skipped

    with pytest.raises(Skipped) as skipped:
        canary_support.require_disposables_folder()
    assert canary_support.DISPOSABLES_FOLDER_ENV in str(skipped.value), (
        "the skip message does not name the variable, so a skipped run reads as a pass")


def test_the_arm_UPLOADS_NOTHING_so_its_media_residue_budget_is_zero_by_construction():
    """The verb has no media leg, and an arm that grew one would be a scope escape: a Drive
    media token cannot be purged by any route this library has measured, so an upload here
    would be permanent residue. Held on the source text because the cheapest place to catch it
    is before it runs."""
    src = gate_shape.gate_source(GATE)
    for uploading in ("put_image_in_document", "put_file_in_document", "upload_media",
                      "put_file_in_folder"):
        assert uploading not in src, (
            f"the arm reaches {uploading} — this verb uploads nothing, and a permanent Drive "
            f"media token is residue no route can purge")
