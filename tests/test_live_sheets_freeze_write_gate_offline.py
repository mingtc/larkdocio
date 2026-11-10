"""Offline guards for the LD-186 FREEZE-PANES WRITE arm
(``tests/test_live_sheets_freeze_write_gate.py``).

NOT marked ``live_write`` — these run in the default ``pytest -q`` with no creds and no
network. They pin the *shape* of the credential-gated arm so a later edit cannot quietly break
the discipline it depends on.

Registered as this gate's mirror in :mod:`gate_registry` (LD-245). The gap the registry
recorded before this file existed was verbatim: *"LD-186 shipped the freeze write **and its own
read leg together**, with no offline mirror for **either** the arm's shape or its
disposables-only provisioning."* Because the write and the read shipped in one issue, this
companion pins **both legs** — a freeze that were verified only by the writer's own echo would
be one half of the pair marking the other half's homework.

Mirrors ``tests/test_live_sheets_style_write_gate_offline.py`` (its arc sibling); the gate
source is read as **text** and never imported or executed, so this file makes no API call.
"""
from pathlib import Path

GATE_SRC = Path(__file__).resolve().parent / "test_live_sheets_freeze_write_gate.py"

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
        f"the LD-186 freeze-panes write arm {GATE_SRC.name} must exist — this companion is its "
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
# (c) LEG ONE — the WRITE goes through the shipped gated apply engine            #
# --------------------------------------------------------------------------- #


def test_gate_writes_the_freeze_through_the_shipped_gated_apply_engine():
    src = _src()
    assert "from larkdocio.sheets.write_apply import" in src, (
        "the arm must import the shipped apply engine — it exists to prove the src/ path."
    )
    for symbol in ("FreezePanes", "dry_run(", "apply("):
        assert symbol in src, (
            f"the arm must drive the shipped chain via {symbol} — typed request → dry_run → "
            "apply is the surface under test."
        )
    assert "FreezePanes.unfreeze(" in src, (
        "the arm must exercise the shipped unfreeze constructor as well as the freeze — the "
        "clear is half of the round-trip."
    )
    assert "SheetsWriteClient.from_write_credentials" in src, (
        "the arm must drive the shipped SheetsWriteClient, not a hand-rolled transport."
    )


def test_gate_pins_the_patch_invariant_and_the_replacement_disclosure():
    src = _src()
    assert "freeze-replaces-freeze" in src, (
        "the plan that changes an existing freeze must disclose the current and target counts; "
        "the arm must assert that note rode a real plan."
    )
    assert "preserved_axes" in src, (
        "the arm must pin the PATCH invariant's own disclosure — which axis survives."
    )
    assert "did not PATCH" in src, (
        "the arm must assert the live patch invariant itself: a rows-only freeze over an "
        "existing frozen COLUMN leaves the column standing. This is the single assertion a "
        "REPLACE misreading would fail."
    )
    assert "Refusal.FROZEN_COUNT_OUT_OF_RANGE" in src, (
        "the arm must assert the over-count refusal is typed."
    )
    assert "read_revision(d.token) == revision_before" in src, (
        "the arm must prove the refusal cost NO write by the live revision standing still."
    )


# --------------------------------------------------------------------------- #
# (c) LEG TWO — the READ leg this issue shipped in the same breath               #
# --------------------------------------------------------------------------- #


def test_gate_verifies_through_an_independent_read_not_the_writes_own_echo():
    src = _src()
    assert "read_frozen_panes(" in src, (
        "the arm must read the frozen state back through the shipped read leg."
    )
    assert "read INDEPENDENTLY" in src, (
        "the freeze arm's whole point is that write and read confront each other: the "
        "verification read must be documented and taken INDEPENDENTLY of the apply-log's own "
        "record, never from the write's echo."
    )
    assert 'structural["observed"]' in src, (
        "…and the apply-log's own observed read-back must then be asserted to AGREE with that "
        "independent read — agreement is the proof, one number alone is not."
    )
    assert "FREEZE_VERIFICATION_LEG" in src, (
        "the arm must assert the apply log names the shipped verification leg."
    )


def test_gate_exercises_the_shipped_graceful_read_leg_and_its_states():
    src = _src()
    assert "read_tabs_frozen" in src, (
        "LD-186 shipped the frozen READ leg alongside the write; the arm must exercise the "
        "shipped SheetsReadClient.read_tabs_frozen composition, not only the raw metainfo read."
    )
    assert "FROZEN_ACTIVE" in src and "FROZEN_NONE" in src, (
        "the graceful leg must be pinned in BOTH resolved states — active after the freeze and "
        "none after the unfreeze; it must never silently resolve to 'unavailable' on a read "
        "that succeeded."
    )
    assert "frozen_state" in src, (
        "the arm must assert on the resolved frozen_state the read leg carries on the tab."
    )


def test_gate_proves_a_freeze_changes_no_cell():
    src = _src()
    assert "values_before" in src and "values_after" in src, (
        "a freeze is VIEW STATE: the arm must capture the tab's values before and after the "
        "whole sequence."
    )
    assert "it is view state and must not" in src, (
        "…and assert they are byte-identical — a freeze/unfreeze sequence that moved a cell "
        "would be a data bug hiding inside a presentation op."
    )


# --------------------------------------------------------------------------- #
# (d)+(e) the disposables-only provisioning and the finally-delete close-out      #
# --------------------------------------------------------------------------- #


def test_gate_self_provisions_its_target_via_the_harness():
    src = _src()
    assert "sheets_write_harness as H" in src, (
        "the arm must provision through the LD-112 Sheets harness."
    )
    assert "H.disposable(" in src, (
        "the arm must take its target from the harness's disposable() context manager "
        "(create → … → delete-in-`finally`) — it may never freeze a spreadsheet it did not "
        "create itself (D7). This is the provisioning the registry recorded as unmirrored."
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
        "the close-out result must be a HARD gate: raise on orphans and assert all_clean."
    )


# --------------------------------------------------------------------------- #
# (f)+(g) WRITE credentials only, and never a target it did not create            #
# --------------------------------------------------------------------------- #


def test_gate_uses_write_credentials_only():
    src = _src()
    assert "from_write_credentials" in src, (
        "the arm must build its gateway and writer from *_from_write_credentials "
        "(LARK_WRITE_APP_* — the write-only resolver that never borrows read/legacy creds) — "
        "doctrine D1/D7."
    )
    assert "get_read_credentials" not in src and "LARK_READ_APP" not in src, (
        "this is a WRITE-credential ring: the arm binds the shipped graceful read method to "
        "the write client rather than constructing a read client, and so must never reach for "
        "the READ credential pair."
    )


def test_gate_never_references_a_non_disposable_target():
    src = _src()
    for name in _FORBIDDEN_TARGETS:
        assert name not in src, (
            f"the LD-186 freeze-panes write arm references {name!r} — a non-disposable target. "
            "It may only ever write to a spreadsheet it self-provisions: never the scratch "
            "sheet, never the read canary, never the zoo, never a real document (D7)."
        )
