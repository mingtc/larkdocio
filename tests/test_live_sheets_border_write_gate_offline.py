"""Offline guards for the LD-189 CELL-BORDER WRITE arm
(``tests/test_live_sheets_border_write_gate.py``).

NOT marked ``live_write`` — these run in the default ``pytest -q`` with no creds and no
network. They pin the *shape* of the credential-gated arm so a later edit cannot quietly break
the discipline it depends on.

Registered as this gate's mirror in :mod:`gate_registry` (LD-245). The gap the registry
recorded before this file existed was verbatim: *"LD-189 shipped the cell-border write with no
offline mirror: nothing pins the **disposables-only invariant** or the **finally-delete** for
this arm."* Those two are therefore this companion's load-bearing tests — and around them sits
the arm's shape, including the one thing that makes this arm unusual: because the shipped
:class:`~larkdocio.sheets.export_reader.ExportedCell` reports **no border**, the arm resolves
the border off the export's own ``xl/styles.xml`` while still verifying the fields the shipped
reader *does* report through the shipped reader. A companion that let that XML leg quietly
become the arm's *only* verification would be missing the point, so both halves are pinned.

Mirrors ``tests/test_live_sheets_style_write_gate_offline.py`` (its LD-188 sibling); the gate
source is read as **text** and never imported or executed, so this file makes no API call.
"""
from pathlib import Path

GATE_SRC = Path(__file__).resolve().parent / "test_live_sheets_border_write_gate.py"

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
        f"the LD-189 cell-border write arm {GATE_SRC.name} must exist — this companion is its "
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
# (c) the ARM'S SHAPE — shipped apply engine in, shipped export out              #
# --------------------------------------------------------------------------- #


def test_gate_writes_through_the_shipped_gated_apply_engine():
    src = _src()
    assert "from larkdocio.sheets.write_apply import" in src, (
        "the arm must import the shipped apply engine — it exists to prove the src/ path."
    )
    for symbol in ("StyleWriteRequest", "CellStyle", "dry_run(", "apply("):
        assert symbol in src, (
            f"the arm must drive the shipped chain via {symbol} — typed request → dry_run → "
            "apply is the surface under test."
        )
    assert "border_type=" in src and "border_color=" in src, (
        "the arm must write the border through the shipped CellStyle border fields."
    )
    assert "BORDER_CLEAR" in src, (
        "the arm must exercise the shipped clear constant (NO_BORDER) — it is both the clear "
        "and this arm's restore."
    )
    assert "SheetsWriteClient.from_write_credentials" in src, (
        "the arm must drive the shipped SheetsWriteClient, not a hand-rolled transport."
    )


def test_gate_verifies_through_the_shipped_export_not_the_writes_own_echo():
    src = _src()
    assert "SheetsExportReader" in src, (
        "the arm must verify through the shipped LD-114 export reader — never by trusting what "
        "apply() echoed back."
    )
    assert "export_xlsx(" in src, (
        "the border itself is not a field the shipped ExportedCell reports, so the arm must go "
        "to the export bytes (export_xlsx) and resolve xl/styles.xml — that is why this arm "
        "exists at all."
    )
    assert "xl/styles.xml" in src and "borderId" in src, (
        "the border read must resolve the cell's style index → cellXfs → borderId → the "
        "borders table; anything vaguer would not prove the border LANDED."
    )
    assert "read_workbook(" in src, (
        "the fields the shipped reader DOES report (bold / fill) must still be verified "
        "through it — that is the coverage the plan's disclosure claims is real."
    )


def test_gate_pins_the_not_verifiable_disclosure_in_both_directions():
    src = _src()
    assert "style-border-not-verifiable" in src, (
        "the arm must assert the plan discloses that the export leg cannot check a border — "
        "without it a caller would believe the gate verified it."
    )
    assert "style-verification-cost" in src, (
        "the LD-188 cost note must still ride the same plan — the notes COMPOSE."
    )
    assert '"style-border-not-verifiable") is None' in src, (
        "the disclosure must be pinned in BOTH directions: a fill-only plan in the same run "
        "must NOT carry the border note (a note that always fires proves nothing)."
    )


def test_gate_proves_the_border_write_surgical():
    src = _src()
    assert "guard neighbour" in src, (
        "the arm must author a guard NEIGHBOUR cell so 'the write was surgical' has something "
        "to protect."
    )
    assert "disturbed a cell VALUE" in src, (
        "the arm must prove the border round-trip left cell VALUES alone — a border is "
        "presentation, not content."
    )


# --------------------------------------------------------------------------- #
# (d)+(e) THE TWO THE REGISTRY NAMED — disposables-only, and the finally-delete   #
# --------------------------------------------------------------------------- #


def test_gate_self_provisions_its_target_via_the_harness():
    src = _src()
    assert "sheets_write_harness as H" in src, (
        "the arm must provision through the LD-112 Sheets harness."
    )
    assert "H.disposable(" in src, (
        "the arm must take its target from the harness's disposable() context manager "
        "(create → … → delete-in-`finally`) — it may never write to a spreadsheet it did not "
        "create itself (D7). This is the invariant the registry recorded as unpinned."
    )
    assert "H.Ledger(" in src, (
        "the disposable must be ledgered, so the close-out has something to re-query."
    )
    assert "SheetsLifecycleGateway.from_write_credentials" in src, (
        "the create/delete lifecycle must run through the harness gateway on WRITE creds."
    )


def test_gate_deletes_in_finally_and_proves_zero_orphans():
    src = _src()
    assert "H.close_out(" in src, (
        "the arm must run the LD-112 zero-orphan close-out, which re-queries every ledger "
        "token — the independent proof the finally-delete really fired."
    )
    assert "raise_if_orphans" in src and "all_clean" in src, (
        "the close-out result must be a HARD gate: raise on orphans and assert all_clean. "
        "This is the finally-delete the registry recorded as unpinned."
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
            f"the LD-189 cell-border write arm references {name!r} — a non-disposable target. "
            "It may only ever write to a spreadsheet it self-provisions: never the scratch "
            "sheet, never the read canary, never the zoo, never a real document (D7)."
        )
