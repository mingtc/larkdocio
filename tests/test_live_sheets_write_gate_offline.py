"""Offline guards for THE SHEETS VALUE-WRITE GATE — the Sheets value-write round-trip
(LD-113).

NOT marked ``live_write`` — these run in the default ``pytest -q`` with no creds and no
network. They pin the *shape* of the credential-gated gate
(``tests/test_live_sheets_write_gate.py``) so a future edit cannot quietly break the
discipline the gate depends on. The binding round-trip itself (AC2–AC4) only runs under
``pytest -m live_write`` at QA with write creds; these guards prove the *scaffolding*
offline (the pure values-leg differ's own red-then-green proof is
``tests/test_sheets_values_diff.py``).

Mirrors the docx W-gate offline guards (``tests/test_live_write_w{1,2,3}_gate_offline.py``),
adapted to the Sheets value-write family: the gate drives the LD-111 plan-gated apply
engine, provisions via the LD-112 harness, proves surgical-ness with the LD-113 values-leg
differ, and writes ONLY against a self-provisioned disposable (never the scratch SHEET, the
read canary, the zoo, or a real document — AC5, D7).
"""
from pathlib import Path

GATE_SRC = Path(__file__).resolve().parent / "test_live_sheets_write_gate.py"


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# AC1 — same marker, deselected by default, skips LOUDLY without write creds    #
# --------------------------------------------------------------------------- #

def test_gate_file_exists():
    assert GATE_SRC.exists(), (
        f"the Sheets value-write gate file {GATE_SRC.name} must exist (LD-113 AC1/AC2)."
    )


def test_gate_marked_live_write():
    src = _src()
    assert "pytest.mark.live_write" in src, (
        "the Sheets value-write gate must carry the `live_write` marker so it stays "
        "deselected by the default addopts and joins the SAME ring as the docx W0..W3 "
        "gates + the LD-112 harness — one `pytest -m live_write` run exercises all "
        "families together (AC1/AC4)."
    )


def test_gate_skips_loudly_when_write_creds_unset():
    src = _src()
    assert "live_write_missing_reason" in src, (
        "the gate must gate on canary_support.live_write_missing_reason() so it skips "
        "loudly when LARK_WRITE_APP_* is unset (AC1)."
    )
    assert "pytest.skip" in src, (
        "the gate must pytest.skip(...) with the missing-creds reason, never run "
        "silently past absent creds (AC1)."
    )


# --------------------------------------------------------------------------- #
# AC2 — the gate drives the LD-111 plan-gated apply engine end-to-end            #
# --------------------------------------------------------------------------- #

def test_gate_builds_a_value_write_request():
    src = _src()
    assert "ValueWriteRequest" in src, (
        "the gate must express the write as a ValueWriteRequest (target + values) — the "
        "LD-111 findings-agnostic value-write request (AC2)."
    )


def test_gate_runs_dry_run_then_apply():
    src = _src()
    assert "dry_run(" in src, (
        "the gate must produce a dry-run Plan via sheets.write_apply.dry_run (S3) — the "
        "only input the apply engine accepts (AC2)."
    )
    assert "apply(" in src, (
        "the gate must execute the plan via sheets.write_apply.apply (S4) — the real "
        "gated apply engine, not a raw put_values (AC2)."
    )


def test_gate_asserts_one_applied_log_entry_with_revision():
    src = _src()
    assert "is_applied" in src, (
        "the gate must assert the apply-log records an `applied` outcome for the target "
        "(AC2)."
    )
    assert "revision" in src, (
        "the gate must assert the applied entry carries the post-write `revision` (the "
        "compare-and-swap anchor) — AC2."
    )


# --------------------------------------------------------------------------- #
# AC2 (D6) — the surgical proof is a used-range VALUES-LEG diff via the shared   #
#            LD-113 differ (only the target changed; every other cell identical) #
# --------------------------------------------------------------------------- #

def test_gate_uses_the_shared_values_leg_differ():
    src = _src()
    assert "from sheets_values_diff import" in src, (
        "the gate must import the shared LD-113 values-leg differ (sheets_values_diff) — "
        "the same pure differ proven red-then-green offline in test_sheets_values_diff.py "
        "(no inline re-implementation)."
    )
    assert "assert_surgical(" in src, (
        "the gate must assert the write is surgical with assert_surgical(before, after, "
        "target) — ONLY the target range changed; every other cell of the used range "
        "byte-identical (D6, the full-used-range matrix compare that catches an oversized "
        "write) — AC2."
    )


def test_gate_reads_the_whole_used_range_not_just_the_target():
    src = _src()
    # The surgical claim is only meaningful against the WHOLE used range (a 3×3 baseline
    # with guard neighbours), not a read of the single target cell — otherwise "every
    # other cell identical" is vacuous.
    assert "USED_RANGE" in src or "A1:C3" in src, (
        "the gate must read the whole used-range matrix (a multi-cell baseline) so the "
        "surgical diff can prove the non-target cells stayed byte-identical (D6, AC2)."
    )
    assert "guard" in src, (
        "the baseline must author guard-neighbour cells around the target so the "
        "used-range diff has something to protect (AC2)."
    )


def test_gate_uses_a_determinism_control_double_read():
    src = _src()
    # Two same-run reads of the unedited used range must be byte-identical, so any
    # post-edit diff is attributable to the edit (the docx gate's determinism control).
    assert "baseline_2" in src or "byte-identical" in src or "non-deterministic" in src, (
        "the gate must read the baseline used range twice and assert same-run byte-"
        "identity — the determinism control that makes the post-edit diff attributable "
        "to the edit (AC2)."
    )


# --------------------------------------------------------------------------- #
# AC3 — restore byte-identical, then delete-in-finally (harness lifecycle)       #
# --------------------------------------------------------------------------- #

def test_gate_restores_the_baseline_byte_identical():
    src = _src()
    assert "assert_identical(" in src, (
        "the gate must restore the baseline and re-diff to byte-identity with "
        "assert_identical(before, restored) — the restore-verify re-diff (AC3)."
    )
    # The restore must go through the SAME gated engine (a second dry_run/apply), not a
    # raw put_values — the whole point is the engine is exercised for both legs.
    assert "restore_plan" in src or "restore" in src, (
        "the gate must restore the baseline value through a second gated plan (AC3)."
    )


def test_gate_self_provisions_and_deletes_via_the_harness():
    src = _src()
    assert "H.disposable(" in src or "disposable(" in src, (
        "the gate must self-provision its disposable via the LD-112 harness "
        "disposable() context manager (create → ... → delete-in-`finally`) — AC3/AC5."
    )
    assert "close_out(" in src, (
        "the gate must run the LD-112 zero-orphan close-out re-querying every ledger "
        "token — the independent proof nothing leaked (AC4)."
    )
    assert "raise_if_orphans" in src or "all_clean" in src, (
        "the gate must assert the close-out found ZERO orphan disposables (AC4)."
    )


# --------------------------------------------------------------------------- #
# AC4 — joins the one live_write ring (marker parity, no fixture collision)      #
# --------------------------------------------------------------------------- #

def test_gate_joins_the_single_live_write_ring():
    src = _src()
    # A module-level `pytestmark = pytest.mark.live_write` (not a per-test decorator) is
    # how every family in the ring opts in — so one `pytest -m live_write` selects them
    # all together with no per-test drift.
    assert "pytestmark = pytest.mark.live_write" in src, (
        "the gate must set a module-level pytestmark = pytest.mark.live_write so it "
        "joins the single ring with the docx families + the LD-112 harness (AC4)."
    )


# --------------------------------------------------------------------------- #
# AC5 — writes ONLY against a self-provisioned disposable; WRITE creds only       #
# --------------------------------------------------------------------------- #

def test_gate_uses_write_credentials_only():
    src = _src()
    assert "from_write_credentials" in src, (
        "the gate must build its client + lifecycle gateway from *_from_write_credentials "
        "(LARK_WRITE_APP_* — the write-only resolver that never borrows read/legacy "
        "creds) — AC5, D1."
    )
    # The WRITE app owns what it creates, so the gate needs no read-app collaborator —
    # it must NOT reach for read credentials at all here.
    assert "get_read_credentials" not in src, (
        "the Sheets value-write gate needs NO read app (the WRITE app owns the disposable "
        "it creates and reads its own compare-and-swap anchor) — it must not reference "
        "get_read_credentials (AC5, D1)."
    )


def test_gate_never_references_scratch_canary_zoo_or_external_docs():
    src = _src()
    forbidden = [
        # never the read canary (docx)
        "LARKDOCIO_CANARY_DOC",
        "CANARY_DOC_ENV",
        "canary_doc_url",
        # never the block-zoo doc
        "LARKDOCIO_BLOCKZOO_DOC",
        "BLOCKZOO_DOC_ENV",
        "blockzoo_doc_url",
        # never the standing docx write-sandbox
        "LARKDOCIO_WRITE_SCRATCH_DOC",
        # never the sheets READ canary / base scratch — a read-only target must never be
        # a WRITE destination (the load-bearing D7 invariant for this family).
        "LARKDOCIO_SCRATCH_SHEET",
        "SCRATCH_SHEET_ENV",
        "scratch_sheet_url",
        "LARKDOCIO_SCRATCH_BASE",
        # no hard-coded external doc/sheet URL literal — never a pre-existing / real doc.
        "larksuite.com/sheets/",
        "feishu.cn/sheets/",
        "larksuite.com/docx/",
        "feishu.cn/docx/",
        "feishu.cn/wiki/",
        "larksuite.com/wiki/",
    ]
    for token in forbidden:
        assert token not in src, (
            f"the Sheets value-write gate must not reference {token!r} — it writes ONLY "
            "against the disposable it self-provisions; never the scratch sheet, the read "
            "canary, the zoo, the sandbox, or a real document (AC5, D7)."
        )
