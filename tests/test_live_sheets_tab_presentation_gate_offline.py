"""Offline guards for the LD-187 TAB-PRESENTATION arm — reorder / retitle / hide-show
(``tests/test_live_sheets_tab_presentation_gate.py``).

NOT marked ``live_write`` — these run in the default ``pytest -q`` with no creds and no
network. They pin the *shape* of the credential-gated arm so a later edit cannot quietly break
the discipline it depends on.

Registered as this gate's mirror in :mod:`gate_registry` (LD-245). The gap the registry
recorded before this file existed was verbatim: *"LD-187 shipped reorder / retitle / hide-show
on a **multi-tab disposable** with no offline mirror; **the multi-tab provisioning is the most
intricate in the set and the least pinned**."* That sentence is this companion's instruction,
so the multi-tab provisioning gets its own tests below: the extra tabs must be added through
the **shipped gated add** (never a raw call), the arm must assert it really got the multi-tab
shape it asked for, and every tab it hides on the way through must be shown again before the
disposable is torn down — a three-tab disposable is three chances to leak, not one.

Mirrors ``tests/test_live_sheets_style_write_gate_offline.py`` (its arc sibling); the gate
source is read as **text** and never imported or executed, so this file makes no API call.
"""
from pathlib import Path

GATE_SRC = Path(__file__).resolve().parent / "test_live_sheets_tab_presentation_gate.py"

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
        f"the LD-187 tab-presentation arm {GATE_SRC.name} must exist — this companion is its "
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
# THE MULTI-TAB PROVISIONING — the registry's named extra, pinned in three ways   #
# --------------------------------------------------------------------------- #


def test_the_extra_tabs_are_added_through_the_shipped_gated_add():
    src = _src()
    assert "AddTab(" in src, (
        "the extra tabs must be created through the SHIPPED gated AddTab request — a raw "
        "client call would provision the multi-tab shape outside the surface under test."
    )
    assert "apply(dry_run([AddTab(" in src, (
        "the add must go through the same dry_run → apply chain as everything else in the arm; "
        "the multi-tab disposable is itself an assertion about the shipped path."
    )
    assert '"applied", "applied"' in src, (
        "the arm must assert BOTH adds applied before it depends on a three-tab shape."
    )


def test_the_arm_asserts_it_really_got_the_multi_tab_shape():
    src = _src()
    assert "len(live) == 3" in src, (
        "the arm must assert the disposable really is a THREE-tab spreadsheet before it "
        "reorders / hides against that assumption — the most intricate provisioning in the set "
        "is exactly the one that must not be assumed (the registry's own words)."
    )
    assert "query_tabs(" in src, (
        "the tab list must be read back through the shipped v3 tab-query leg."
    )
    assert 'target["hidden"] is False' in src, (
        "the arm must assert its baseline: a fresh disposable's tab is visible. A hide test "
        "starting from an unknown visibility proves nothing."
    )


def test_every_tab_hidden_along_the_way_is_shown_again_before_teardown():
    src = _src()
    # The last-visible-tab refusal is only reachable by hiding the OTHER tabs first, so this arm
    # deliberately leaves the disposable in a multi-tab, partly-hidden state mid-run. The
    # close-out proves the SPREADSHEET was deleted; this pins the intermediate tab state too.
    assert "SetTabVisibility.show(" in src, (
        "the arm must show back what it hid — three tabs are three chances to leave the "
        "disposable in a state its later assertions silently depend on."
    )
    assert 'all(t["hidden"] is False for t in final.values())' in src, (
        "the arm must assert EVERY tab ended visible, across the whole multi-tab set — not "
        "just the one it was testing."
    )


# --------------------------------------------------------------------------- #
# (c) the ARM'S SHAPE — the three ops through the shipped engine, read back      #
# --------------------------------------------------------------------------- #


def test_gate_writes_the_three_presentation_ops_through_the_shipped_engine():
    src = _src()
    assert "from larkdocio.sheets.write_apply import" in src, (
        "the arm must import the shipped apply engine — it exists to prove the src/ path."
    )
    for symbol in ("ReorderTab", "RetitleTab", "SetTabVisibility", "dry_run(", "apply("):
        assert symbol in src, (
            f"the arm must drive the shipped chain via {symbol} — all three updateSheet "
            "presentation fields are the surface under test."
        )
    assert "SheetsWriteClient.from_write_credentials" in src, (
        "the arm must drive the shipped SheetsWriteClient, not a hand-rolled transport."
    )


def test_gate_verifies_through_an_independent_read_not_the_writes_own_echo():
    src = _src()
    assert "read INDEPENDENTLY" in src, (
        "the verification tab list must be documented and taken INDEPENDENTLY of the "
        "apply-log's own record — never from the write's echo."
    )
    assert 'structural["observed"]' in src and "TAB_VERIFICATION_LEG" in src, (
        "…and the apply-log's own observed read-back must be asserted to agree with it, and to "
        "name the shipped verification leg."
    )
    assert "sheet_id_survived_retitle" in src, (
        "the retitle's join-breakage note CLAIMS the sheet_id stands still; the arm must "
        "confirm that against the live tab query rather than restating the note."
    )
    assert "readable_while_hidden" in src, (
        "the single assertion the whole hide disclosure rests on: a HIDDEN tab's values still "
        "read back, byte-identical."
    )


def test_gate_pins_the_refusals_as_typed_and_inert():
    src = _src()
    for refusal in ("Refusal.TAB_INDEX_OUT_OF_RANGE", "Refusal.DUPLICATE_TAB_TITLE",
                    "Refusal.LAST_VISIBLE_TAB"):
        assert refusal in src, (
            f"the arm must assert the {refusal} refusal is TYPED — two of these are hazards "
            "Lark itself accepts (a clamped out-of-range index) or answers with an opaque "
            "server error."
        )
    assert "read_revision(d.token) == revision_before" in src, (
        "every refusal must be proven INERT by the live revision standing still — a refusal "
        "that wrote something would be the worst outcome of the three."
    )
    assert "tab-presentation-no-op" in src, (
        "the no-op disclosure must ride a real plan, and the arm must show the revision does "
        "not move for it either."
    )


def test_gate_proves_a_presentation_write_changes_no_cell():
    src = _src()
    assert "values_before" in src and "values_after" in src, (
        "presentation is not content: the arm must capture the tab's values before and after "
        "the whole sequence."
    )
    assert "it must change none" in src, (
        "…and assert they are byte-identical across reorder + retitle + hide + show."
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
        "(create → … → delete-in-`finally`) — every tab it reorders, retitles or hides must "
        "live in a spreadsheet it created itself (D7)."
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
        "the WRITE app owns the multi-tab disposable it creates — the arm needs no read "
        "collaborator and must not reach for read credentials."
    )


def test_gate_never_references_a_non_disposable_target():
    src = _src()
    for name in _FORBIDDEN_TARGETS:
        assert name not in src, (
            f"the LD-187 tab-presentation arm references {name!r} — a non-disposable target. "
            "It may only ever reorder / retitle / hide tabs in a spreadsheet it "
            "self-provisions: never the scratch sheet, never the read canary, never the zoo, "
            "never a real document (D7)."
        )
