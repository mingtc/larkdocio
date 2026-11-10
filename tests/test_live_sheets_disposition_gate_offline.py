"""Offline guards for the LD-148 DISPOSITION LIVE ARM (`tests/test_live_sheets_disposition_gate.py`).

NOT marked ``live_write`` — these run in the default ``pytest -q`` with no creds and no
network. They pin the *shape* of the credential-gated arm so a later edit cannot quietly break
the discipline it depends on, and they are the **offline proof of the disposables-only
invariant** (D7): the live file must self-provision through the LD-112 harness, delete in
``finally``, run the zero-orphan close-out, and reference **no** non-disposable target (never
the maintainer dogfood sheet, never the canary scratch sheet, never the zoo, never a real document).

Mirrors ``tests/test_live_sheets_revision_guard_gate_offline.py`` (the family's precedent).
"""
from pathlib import Path

GATE_SRC = Path(__file__).resolve().parent / "test_live_sheets_disposition_gate.py"

#: The env targets that are NOT disposables. The arm must never name one.
_FORBIDDEN_TARGETS = (
    "LARKDOCIO_SCRATCH_SHEET",
    "LARKDOCIO_CANARY_DOC",
    "LARKDOCIO_BLOCKZOO_DOC",
    "LARKDOCIO_BLOCKZOO_WIKI",
    "LARKDOCIO_WRITE_SCRATCH_DOC",
    "LARKDOCIO_SCRATCH_BASE",
    "scratch_sheet_url",
    "canary_doc_url",
    "blockzoo_doc_url",
)


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


def test_gate_file_exists():
    assert GATE_SRC.exists(), f"the LD-148 disposition live arm {GATE_SRC.name} must exist."


def test_gate_joins_the_single_live_write_ring():
    assert "pytestmark = pytest.mark.live_write" in _src(), (
        "the arm must set a module-level pytestmark = pytest.mark.live_write so one "
        "`pytest -m live_write` run selects it with every other family."
    )


def test_gate_skips_loudly_when_write_creds_unset():
    src = _src()
    assert "live_write_missing_reason" in src and "pytest.skip" in src, (
        "with no write creds the arm must skip with the shared human-readable reason — "
        "never a silent pass."
    )


def test_gate_arm_a_asserts_the_plan_time_unknown_mention_refusal():
    src = _src()
    assert "Refusal.UNKNOWN_MENTION" in src, (
        "arm (a) must assert the plan-time refusal is typed unknown-mention (AC7a)."
    )
    assert 'mention_validation == "active"' in src, (
        "arm (a) must prove the plan-time check actually RAN — a skipped check that happens "
        "to refuse nothing would pass a weaker assertion."
    )


def test_gate_arm_b_forces_the_bad_id_past_planning_and_asserts_api_error():
    src = _src()
    assert "_NoMentionCheck" in src, (
        "arm (b) must push the bad id PAST the plan-time check to observe the mid-batch "
        "disposition live (AC7b)."
    )
    assert 'mention_validation == "unavailable"' in src, (
        "arm (b) must confirm the plan disclosed the unavailable check (never silent)."
    )
    assert "Refusal.API_ERROR" in src and '"90204" in bad.refusal.detail' in src, (
        "arm (b) must assert the LIVE 90204 became a typed api-error refusal carrying "
        "Lark's own code."
    )
    assert "not log_b.halted" in src, (
        "arm (b) must assert the batch CONTINUED — the maintainer-blessed per-entry doctrine."
    )


def test_gate_asserts_the_sheet_state_matches_the_apply_log_exactly():
    src = _src()
    assert "the log says applied" in src and "the log says" in src, (
        "the arm's payoff assertion is that the sheet's final state matches the log cell for "
        "cell — that equality is what the invariant is FOR (AC7)."
    )
    assert "assert_surgical" in src, "the arm must prove the writes were surgical."


def test_gate_self_provisions_and_deletes_via_the_harness():
    src = _src()
    assert "H.disposable(" in src, "the arm must self-provision via the LD-112 harness."
    assert "H.close_out(" in src and "raise_if_orphans" in src, (
        "the arm must run the zero-orphan close-out and raise on a leak."
    )


def test_gate_uses_write_credentials_only():
    src = _src()
    assert "from_write_credentials" in src, (
        "the arm must build its clients from the WRITE credential pair (doctrine D1)."
    )
    assert "get_read_credentials" not in src and "LARK_READ_APP" not in src


def test_gate_never_references_a_non_disposable_target():
    src = _src()
    for name in _FORBIDDEN_TARGETS:
        assert name not in src, (
            f"the disposition live arm references {name!r} — a non-disposable target. It may "
            f"only ever write to a spreadsheet it self-provisions (D7)."
        )


def test_gate_mention_target_is_a_deliberately_nonexistent_id():
    src = _src()
    assert "BAD_OPEN_ID" in src, "the arm needs a named nonexistent-open_id constant"
    assert "ou_0000000000000000000000000000dead" in src, (
        "the arm's mention target must be a structurally valid but NONEXISTENT open_id — it "
        "must never poke a real user (notify is false either way, but the id itself is fake)."
    )


def test_the_no_mention_check_proxy_hides_only_the_validator():
    """The arm's own helper, unit-tested offline: it must hide ``validate_user_ids`` and
    forward everything else untouched (a proxy that dropped a write would invalidate the arm)."""
    import test_live_sheets_disposition_gate as gate

    class Inner:
        def __init__(self):
            self.puts = []

        def validate_user_ids(self, open_ids):        # pragma: no cover - must be unreachable
            raise AssertionError("the proxy must hide this")

        def put_values(self, spreadsheet_token, a1_range, values):
            self.puts.append((a1_range, values))
            return {"revision": 2}

        def read_revision(self, spreadsheet_token):
            return 1

    inner = Inner()
    proxy = gate._NoMentionCheck(inner)

    assert getattr(proxy, "validate_user_ids", None) is None
    assert proxy.read_revision("t") == 1
    assert proxy.put_values("t", "s!A1:A1", [["x"]]) == {"revision": 2}
    assert inner.puts == [("s!A1:A1", [["x"]])], "the proxy must forward writes verbatim"
