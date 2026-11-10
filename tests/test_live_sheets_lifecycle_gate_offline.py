"""Offline guards for the LIFECYCLE LIVE ARM (``tests/test_live_sheets_lifecycle_gate.py``).

NOT marked ``live_write`` — these run in the default ``pytest -q`` with no creds and no
network. They pin the *shape* of the credential-gated arm so a later edit cannot quietly break
the discipline it depends on, and they are the **offline proof of the disposables-only
invariant**: the live file must self-provision through the SHIPPED create, delete in a
``finally``, confirm the delete by OBSERVING the deleted-token error, run the arm **twice** on
fresh disposables, sweep a zero-orphan close-out, and reference **no** non-disposable target
(never the canary, never the standing scratch sheet, never the zoo, never a real document).

Mirrors ``tests/test_live_sheets_disposition_gate_offline.py`` (the family's precedent).
"""
from pathlib import Path

GATE_SRC = Path(__file__).resolve().parent / "test_live_sheets_lifecycle_gate.py"

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
    assert GATE_SRC.exists(), f"the lifecycle live arm {GATE_SRC.name} must exist."


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


def test_gate_exercises_the_shipped_lifecycle_calls_not_a_local_copy():
    """The whole point of the arm: it proves the SHIPPED pair against real Lark."""
    src = _src()
    assert "SheetsWriteClient.from_write_credentials" in src, (
        "the arm must build the shipped write client (WRITE creds, no fallback).")
    for op in ("create_spreadsheet(", "delete_spreadsheet("):
        assert op in src, f"the arm never calls the shipped {op[:-1]}"
    imported = {
        line.split()[1].split(".")[0]
        for line in src.splitlines()
        if line.startswith("import ")
    }
    assert "urllib" not in imported, (
        "the arm imports urllib — it must not hand-build HTTP, because the shipped calls "
        "are exactly what it exists to prove.")


def test_gate_captures_the_created_token_and_ledgers_it():
    src = _src()
    assert "spreadsheet_token" in src, (
        "the arm must capture the token the create returns — a dropped token is an orphan "
        "by construction.")
    assert "record_create" in src, (
        "every created token must reach the ledger before anything else can fail.")


def test_gate_deletes_in_a_finally():
    src = _src()
    assert "finally:" in src, (
        "the delete must run in a `finally` — a mid-arm failure still has to clean up.")


def test_gate_confirms_the_delete_by_observing_the_deleted_token_error():
    """AC5 verbatim: the deleted-token error IS the confirmation. A ``code: 0`` from the
    delete is the API's word for "accepted", not proof the file is gone."""
    src = _src()
    assert "SPREADSHEET_GONE_CODE" in src, (
        "the arm must compare against the shipped deleted-token constant.")
    assert "pytest.raises(LarkAPIError)" in src, (
        "the confirmation must be an OBSERVED typed error, not an assumption.")
    assert "confirm" in src.lower()


def test_gate_runs_twice_on_fresh_disposables():
    """The amplifier: two arms, so a clean close-out is structural rather than lucky."""
    src = _src()
    assert "for arm in (1, 2)" in src, (
        "the arm must run TWICE on fresh disposables — one clean run could be luck.")


def test_gate_runs_the_zero_orphan_close_out():
    src = _src()
    assert "close_out(" in src and "raise_if_orphans" in src, (
        "the arm must run the zero-orphan close-out and raise on a leak.")


def test_gate_uses_write_credentials_only():
    src = _src()
    assert "from_write_credentials" in src
    assert "get_read_credentials" not in src and "LARK_READ_APP" not in src


def test_gate_titles_its_disposables_with_the_grep_able_prefix():
    src = _src()
    assert "disposable_title" in src, (
        "a disposable must carry the grep-able DISPOSABLE title prefix, so a stray survivor "
        "is findable by name as well as by the ledger.")


def test_gate_never_references_a_non_disposable_target():
    src = _src()
    for name in _FORBIDDEN_TARGETS:
        assert name not in src, (
            f"the lifecycle live arm references {name!r} — a non-disposable target. It may "
            f"only ever create, write to and delete a spreadsheet it provisions itself."
        )
