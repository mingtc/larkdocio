"""Offline guards for the LD-188 CELL-STYLE WRITE arm
(``tests/test_live_sheets_style_write_gate.py``).

NOT marked ``live_write`` — these run in the default ``pytest -q`` with no creds and no
network. They pin the *shape* of the credential-gated arm so a later edit cannot quietly break
the discipline it depends on, and they are the **offline proof of the disposables-only
invariant** (D7) for this arm: it must self-provision through the LD-112 harness, delete in
``finally``, run the zero-orphan close-out, and reference **no** non-disposable target.

Registered as this gate's mirror in :mod:`gate_registry` (LD-245). The gap the registry
recorded before this file existed was verbatim: *"LD-188 shipped the cell-style write through
src/ with no offline mirror of the arm's shape or its disposables-only invariant."* Both halves
are pinned below — the **shape** (typed request → ``dry_run`` → ``apply``, verified through the
shipped export reader rather than the write's own echo) and the **invariant**.

Mirrors ``tests/test_live_sheets_style_gate_offline.py`` (the L2 read-leg sibling); the gate
source is read as **text** and never imported or executed, so this file makes no API call.
"""
from pathlib import Path

GATE_SRC = Path(__file__).resolve().parent / "test_live_sheets_style_write_gate.py"

#: Env targets / URL literals that are NOT disposables. The arm must never name one.
_FORBIDDEN_TARGETS = (
    "LARKDOCIO_SCRATCH_SHEET",
    "SCRATCH_SHEET_ENV",
    "scratch_sheet_url",
    "LARKDOCIO_SCRATCH_BASE",
    "LARKDOCIO_CANARY_DOC",
    "CANARY_DOC_ENV",
    "canary_doc_url",
    "LARKDOCIO_BLOCKZOO_DOC",
    "LARKDOCIO_BLOCKZOO_WIKI",
    "blockzoo_doc_url",
    "LARKDOCIO_WRITE_SCRATCH_DOC",
    "larksuite.com/sheets/",
    "feishu.cn/sheets/",
    "larksuite.com/docx/",
    "feishu.cn/docx/",
    "larksuite.com/wiki/",
    "feishu.cn/wiki/",
)


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# (a) the gate exists and joins the single live_write ring at module level       #
# --------------------------------------------------------------------------- #


def test_gate_file_exists():
    assert GATE_SRC.exists(), (
        f"the LD-188 cell-style write arm {GATE_SRC.name} must exist — this companion is its "
        "offline mirror and has nothing to mirror without it."
    )


def test_gate_joins_the_single_live_write_ring():
    assert "pytestmark = pytest.mark.live_write" in _src(), (
        "the arm must set a MODULE-LEVEL pytestmark = pytest.mark.live_write (not a per-test "
        "decorator) so one `pytest -m live_write` run selects it with every other family."
    )


def test_gate_skips_loudly_when_write_creds_unset():
    src = _src()
    assert "live_write_missing_reason" in src, (
        "the arm must gate on canary_support.live_write_missing_reason() so it skips loudly "
        "when LARK_WRITE_APP_* is unset."
    )
    assert "pytest.skip" in src, (
        "the arm must pytest.skip(...) with that reason — never run silently past absent creds."
    )


# --------------------------------------------------------------------------- #
# (c) the ARM'S SHAPE — the write goes through the shipped src/ apply engine …    #
# --------------------------------------------------------------------------- #


def test_gate_writes_through_the_shipped_gated_apply_engine():
    src = _src()
    # This is what distinguishes LD-188's arm from LD-118's older L2 gate: the style is written
    # through the SHIPPED typed request → dry_run → apply chain, not the harness's own styler.
    assert "from larkdocio.sheets.write_apply import" in src, (
        "the arm must import the shipped apply engine — it exists to prove the src/ path, not "
        "the harness's private styler."
    )
    for symbol in ("StyleWriteRequest", "CellStyle", "dry_run(", "apply("):
        assert symbol in src, (
            f"the arm must drive the shipped chain via {symbol} — typed request → dry_run → "
            "apply is the surface under test."
        )
    assert "BatchStyleWriteRequest" in src and "StyleSpan" in src, (
        "the arm must exercise the BATCH form (N ranges, one call) as well as the single-span "
        "form — the batch is the shape a caller reaches for."
    )
    assert "SheetsWriteClient.from_write_credentials" in src, (
        "the arm must drive the shipped SheetsWriteClient, not a hand-rolled transport."
    )


def test_gate_verifies_through_the_shipped_reader_not_the_writes_own_echo():
    src = _src()
    assert "SheetsExportReader" in src, (
        "the style leg is only readable through the shipped LD-114 export reader — the arm "
        "must verify there, not trust what apply() echoed back."
    )
    assert "read_workbook(" in src, (
        "the arm must read the styled cells back through the export reader's read_workbook()."
    )
    for field in ("bold", "fill_rgb", "num_fmt"):
        assert field in src, (
            f"the arm must assert the resolved cell's {field} — the three fields the shipped "
            "ExportedCell actually reports."
        )
    assert "read_revision(" in src, (
        "the arm proves 'one call' by the spreadsheet revision moving exactly once, and proves "
        "a refusal wrote nothing by it not moving at all — both need read_revision()."
    )


def test_gate_proves_the_style_write_surgical_and_the_refusal_inert():
    src = _src()
    assert "guard neighbour" in src, (
        "the arm must author a guard NEIGHBOUR cell so 'the write was surgical' has something "
        "to protect."
    )
    assert "Refusal.UNKNOWN_TAB" in src, (
        "the arm must assert the plan-time unknown-tab refusal is typed."
    )
    assert "read_revision(d.token) == revision_before" in src, (
        "the arm must prove the refusal cost NO write by the live revision standing still."
    )


# --------------------------------------------------------------------------- #
# (d)+(e) the disposables-only invariant and the finally-delete close-out         #
# --------------------------------------------------------------------------- #


def test_gate_self_provisions_its_target_via_the_harness():
    src = _src()
    assert "sheets_write_harness as H" in src, (
        "the arm must provision through the LD-112 Sheets harness."
    )
    assert "H.disposable(" in src, (
        "the arm must take its target from the harness's disposable() context manager "
        "(create → … → delete-in-`finally`) — it may never write to a spreadsheet it did not "
        "create itself (D7)."
    )
    assert "H.Ledger(" in src, (
        "the disposable must be ledgered, so the close-out has something to re-query."
    )


def test_gate_deletes_in_finally_and_proves_zero_orphans():
    src = _src()
    assert "H.close_out(" in src, (
        "the arm must run the LD-112 zero-orphan close-out, which re-queries every ledger "
        "token — the independent proof nothing leaked."
    )
    assert "raise_if_orphans" in src and "all_clean" in src, (
        "the close-out result must be a HARD gate: raise on orphans and assert all_clean."
    )


# --------------------------------------------------------------------------- #
# (f)+(g) WRITE credentials only, and never a target it did not create            #
# --------------------------------------------------------------------------- #


def test_gate_uses_write_credentials_only():
    src = _src()
    assert "from_write_credentials" in src, (
        "the arm must build its gateway, writer and export reader from "
        "*_from_write_credentials (LARK_WRITE_APP_* — the write-only resolver that never "
        "borrows read/legacy creds) — doctrine D1/D7."
    )
    assert "get_read_credentials" not in src and "LARK_READ_APP" not in src, (
        "the WRITE app owns the disposable it creates and exports it itself — the arm needs no "
        "read collaborator and must not reach for read credentials."
    )


def test_gate_never_references_a_non_disposable_target():
    src = _src()
    for name in _FORBIDDEN_TARGETS:
        assert name not in src, (
            f"the LD-188 cell-style write arm references {name!r} — a non-disposable target. "
            "It may only ever write to a spreadsheet it self-provisions: never the scratch "
            "sheet, never the read canary, never the zoo, never a real document (D7)."
        )
