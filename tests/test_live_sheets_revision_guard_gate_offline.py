"""Offline guards for the LD-132 REVISION-GUARD LIVE ARM (`tests/test_live_sheets_revision_guard_gate.py`).

NOT marked ``live_write`` — these run in the default ``pytest -q`` with no creds and no
network. They pin the *shape* of the credential-gated arm so a later edit cannot quietly
break the discipline it depends on, and — most importantly — they are the **offline proof of
the disposables-only invariant** (LD-132 AC7): the live file must self-provision through the
LD-112 harness, delete in ``finally``, run the zero-orphan close-out, and reference **no**
non-disposable target (never the standing read-only sheet, never the canary scratch sheet, never the
zoo, never a real document).

Mirrors ``tests/test_live_sheets_write_gate_offline.py`` (the family's precedent).
"""
from pathlib import Path

GATE_SRC = Path(__file__).resolve().parent / "test_live_sheets_revision_guard_gate.py"


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


def test_gate_file_exists():
    assert GATE_SRC.exists(), f"the LD-132 revision-guard live arm {GATE_SRC.name} must exist."


def test_gate_joins_the_single_live_write_ring():
    assert "pytestmark = pytest.mark.live_write" in _src(), (
        "the arm must set a module-level pytestmark = pytest.mark.live_write so one "
        "`pytest -m live_write` run selects it with every other family (AC6)."
    )


def test_gate_skips_loudly_when_write_creds_unset():
    src = _src()
    assert "live_write_missing_reason" in src and "pytest.skip" in src, (
        "with no write creds the arm must skip with the shared human-readable reason — "
        "never a silent pass."
    )


def test_gate_confirms_the_fresh_disposable_starts_at_revision_zero():
    src = _src()
    assert "read_revision" in src, "the arm must read the raw revision anchor"
    assert "== 0" in src, (
        "the arm must ASSERT the fresh disposable's pre-first-write anchor is 0 — the LD-107 "
        "premise the whole investigation rests on (a change must redden, not pass quietly)."
    )


def test_gate_plans_pre_first_write_and_asserts_the_unavailable_marker():
    src = _src()
    assert "REVISION_GUARD_UNAVAILABLE" in src, (
        "the arm must assert the PRE-first-write plan carries revision_guard 'unavailable' "
        "(AC1/AC3 — the marker must be visible on a genuinely-zero anchor)."
    )
    assert "revision_guard_detail" in src, "the arm must capture the marker's WHY as evidence"
    assert "value_precondition" in src, (
        "the arm must assert the entry still names its tier-2 value precondition (AC2)."
    )


def test_gate_records_the_zero_to_one_transition():
    src = _src()
    assert "revision_after_first_write" in src, (
        "the arm must record the post-first-write anchor — THE investigation's answer "
        "(does a write on a revision-0 sheet bump it?) belongs in the evidence line (AC3)."
    )


def test_gate_proves_the_self_healing_stale_refusal_and_the_self_activation():
    src = _src()
    assert "Refusal.STALE_SHEET" in src, (
        "the arm must prove that a plan cached at 0 STILL refuses STALE_SHEET once the "
        "anchor advances — 'unavailable' never means 'compare disabled'."
    )
    assert "REVISION_GUARD_ACTIVE" in src, (
        "the arm must prove the guard SELF-ACTIVATES on the next plan (nonzero anchor)."
    )
    assert "assert_surgical" in src, (
        "the arm's applied write must be proven surgical via the shared values-leg differ."
    )


def test_gate_self_provisions_and_deletes_via_the_harness():
    src = _src()
    assert "H.disposable(" in src, (
        "every write target must come from the LD-112 harness disposable() context manager "
        "(create → ... → delete-in-`finally`) — AC7."
    )
    assert "close_out(" in src and ("raise_if_orphans" in src or "all_clean" in src), (
        "the arm must run the zero-orphan close-out and assert it found no orphans (AC7)."
    )
    assert "is_disposable_title" in src, (
        "the arm must assert its write target carries the grep-able DISPOSABLE title (D7)."
    )


def test_gate_uses_write_credentials_only():
    src = _src()
    assert "from_write_credentials" in src
    assert "get_read_credentials" not in src, (
        "the WRITE app owns what it creates — the arm must not reach for read creds (D1)."
    )


def test_gate_never_references_a_non_disposable_target():
    """The AC7 invariant, statically: the arm's source must not name ANY non-disposable
    target — not the standing read-only sheet (whose write probe is WITHDRAWN), not the canary
    scratch sheet, not the zoo, not a real document URL."""
    src = _src()
    forbidden = [
        # the standing read-only spreadsheet — READ-ONLY probes only; its write probe is WITHDRAWN
        "SheetCommentZooExample00001",
        # never the docx read canary / the block zoo / the docx write sandbox
        "LARKDOCIO_CANARY_DOC",
        "CANARY_DOC_ENV",
        "canary_doc_url",
        "LARKDOCIO_BLOCKZOO_DOC",
        "BLOCKZOO_DOC_ENV",
        "blockzoo_doc_url",
        "LARKDOCIO_WRITE_SCRATCH_DOC",
        # never the sheets read canary / base scratch
        "LARKDOCIO_SCRATCH_SHEET",
        "SCRATCH_SHEET_ENV",
        "scratch_sheet_url",
        "LARKDOCIO_SCRATCH_BASE",
        # no hard-coded external doc/sheet URL literal
        "larksuite.com/sheets/",
        "feishu.cn/sheets/",
        "larksuite.com/docx/",
        "feishu.cn/docx/",
        "feishu.cn/wiki/",
        "larksuite.com/wiki/",
    ]
    for token in forbidden:
        assert token not in src, (
            f"the LD-132 live arm must not reference {token!r} — every live write goes to a "
            "self-provisioned disposable, created and deleted in the same run (AC7)."
        )
