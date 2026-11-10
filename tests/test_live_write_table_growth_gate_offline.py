"""Offline guards for THE LD-431 GATE — the oversize-table round-trip.

NOT marked ``live_write``: these run in the default ``pytest -q`` with no creds and no
network. They are the automatable half of the gate's contract — they pin the *shape* of the
credential-gated gate (``tests/test_live_write_table_growth_gate.py``) so a future edit cannot
quietly hollow it out. The binding round-trip itself (author both oversize grids **through the
gate** → read them back through the reader → assert the live ``row_size`` / ``column_size`` →
teardown) runs only under ``pytest -m live_write`` at QA with write creds.

The one thing this gate must never lose is **why it is different from the S2 table gate**: the
grids it authors are past the create endpoint's per-axis ceiling on **both axes**, which is the
only reason it can catch the bug it was written for.
"""
from pathlib import Path

from larkdocio.write.encode import MAX_CREATE_GRID_AXIS

GATE_SRC = Path(__file__).resolve().parent / "test_live_write_table_growth_gate.py"


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The ring's discipline — same marker, deselected by default, skips LOUDLY      #
# --------------------------------------------------------------------------- #

def test_the_gate_file_exists():
    assert GATE_SRC.exists(), f"the LD-431 growth gate {GATE_SRC.name} must exist."


def test_the_gate_is_marked_live_write_and_conformance():
    src = _src()
    assert "pytest.mark.live_write" in src, (
        "the gate must carry the `live_write` marker so it stays deselected by the default "
        "addopts and joins the same ring as W0/W1/W2/W3/S2.")
    assert "pytest.mark.conformance" in src, (
        "a gate pinning measured external truth is conformance-tier "
        "(process/doctrine/conformance-tier.md § A.4).")


def test_the_gate_skips_loudly_when_write_creds_are_unset():
    src = _src()
    assert "live_write_missing_reason" in src and "pytest.skip" in src, (
        "the gate must gate on canary_support.live_write_missing_reason() and pytest.skip "
        "— never run silently past absent creds.")


# --------------------------------------------------------------------------- #
# Disposables only — the gate creates its target and destroys it               #
# --------------------------------------------------------------------------- #

def test_the_gate_creates_its_own_document_and_never_names_a_configured_one():
    src = _src()
    assert "create_document(" in src, (
        "the gate must self-provision its document — it may never address a doc it did not "
        "create.")
    for forbidden in ("LARKDOCIO_CANARY_DOC", "LARK_DOC_URL", "SCRATCH_DOC"):
        assert forbidden not in src, (
            f"the gate names {forbidden} — a live write may only ever touch a document the "
            f"harness itself created.")


def test_the_gate_tears_down_in_a_finally():
    src = _src()
    assert "finally:" in src and "batch_delete(" in src and "delete_document(" in src, (
        "teardown must run on success AND failure, or a failing run leaves litter.")
    assert "assert emptied" in src, (
        "the gate must ASSERT the teardown worked — a best-effort cleanup nobody checks is "
        "how orphans accumulate.")


# --------------------------------------------------------------------------- #
# What THIS gate adds — grids past the ceiling, on BOTH axes                    #
# --------------------------------------------------------------------------- #

def test_the_gate_authors_grids_past_the_create_ceiling_on_both_axes():
    from test_live_write_table_growth_gate import (
        TALL_COLS,
        TALL_ROWS,
        WIDE_COLS,
        WIDE_ROWS,
    )
    assert TALL_ROWS > MAX_CREATE_GRID_AXIS >= TALL_COLS, (
        "the tall grid must exceed the ceiling on the ROW axis and only that axis — "
        "otherwise the gate cannot attribute a failure to row growth.")
    assert WIDE_COLS > MAX_CREATE_GRID_AXIS >= WIDE_ROWS, (
        "the wide grid must exceed the ceiling on the COLUMN axis and only that axis.")


def test_the_gate_authors_from_MARKDOWN_through_the_plan_gate():
    src = _src()
    assert "compose(" in src, (
        "the bug arrived through compose() — the gate must enter the same way a consumer "
        "does, not by hand-building typed content.")
    assert "dry_run(" in src and "apply(" in src, (
        "content must reach Lark only through dry_run → Plan → apply.")
    for authored_key in ('"row_size":', '"column_size":'):
        assert authored_key not in src, (
            f"the gate must not author {authored_key} itself — the grid property is the "
            f"encoder's business, and a gate that writes it is not testing the encoder.")


def test_the_gate_earns_its_verdict_from_a_FRESH_READ_BACK():
    src = _src()
    assert "_download(doc_id)" in src, (
        "the verdict must come from re-downloading through the reader, never from the "
        "write's own success code.")
    assert "row_size" in src and "column_size" in src, (
        "the gate must assert the LIVE grid property, so a table that was created short "
        "cannot pass on Markdown alone.")
    assert "ndiff" in src, (
        "the gate must prove the write was purely additive — a growth path that clobbers "
        "neighbouring content would otherwise pass.")
