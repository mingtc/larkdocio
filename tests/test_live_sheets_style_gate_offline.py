"""Offline guards for THE L2 GATE — the Sheets style-leg fidelity round-trip
(LD-118).

NOT marked ``live_write`` — these run in the default ``pytest -q`` with no creds and no
network. They pin the *shape* of the credential-gated gate
(``tests/test_live_sheets_style_gate.py``) so a future edit cannot quietly break the
discipline the gate depends on. The binding round-trip itself (AC2–AC4) only runs under
``pytest -m live_write`` at QA with write creds; these guards prove the *scaffolding*
offline (the pure fidelity assertion's own red-then-green — incl. the missing-fill miss —
is ``tests/test_sheets_fidelity_diff.py``).

Mirrors the docx W-gate + the LD-113 value-gate offline guards
(``tests/test_live_sheets_write_gate_offline.py``), adapted to the Sheets **style leg**: the
gate writes bold + a fill + a ``0.00%`` numFmt to a self-provisioned disposable, exports it
(the LD-114 stdlib xlsx-export reader), and asserts ``xl/styles.xml`` carries the bold, the
fill ``FFFFFF00``, and numFmt ``0.00%`` (LD-107 Q2 reproduced through shipped code), then
restores/deletes leak-proof — writing ONLY against a self-provisioned disposable (never the
scratch SHEET, the read canary, the zoo, or a real document — AC5, D7).
"""
from pathlib import Path

GATE_SRC = Path(__file__).resolve().parent / "test_live_sheets_style_gate.py"


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# AC1 — same marker, deselected by default, skips LOUDLY without write creds     #
# --------------------------------------------------------------------------- #

def test_gate_file_exists():
    assert GATE_SRC.exists(), (
        f"the Sheets style-leg gate file {GATE_SRC.name} must exist (LD-118 AC1/AC2)."
    )


def test_gate_marked_live_write_at_module_level():
    src = _src()
    # A module-level `pytestmark = pytest.mark.live_write` (not a per-test decorator) is how
    # every family in the ring opts in — one `pytest -m live_write` selects them all together
    # with the docx W0..W3 gates + the sheets value gate (AC1/AC4).
    assert "pytestmark = pytest.mark.live_write" in src, (
        "the Sheets style-leg gate must set a module-level pytestmark = "
        "pytest.mark.live_write so it joins the SINGLE live_write ring — one `pytest -m "
        "live_write` run exercises ALL families together (AC1/AC4)."
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
# AC2 — write bold + fill + numFmt, export, stdlib-parse, assert EXACT fidelity  #
# --------------------------------------------------------------------------- #

def test_gate_writes_the_style_via_the_harness_style_leg():
    src = _src()
    assert "put_style(" in src, (
        "the gate must write the cell style through the S5 harness style leg "
        "(Disposable.put_style / SheetsStyleWriter) — AC2."
    )
    # the exact LD-107 Q2 style payload: bold font + #FFFF00 backColor + 0.00% formatter.
    assert "backColor" in src and "#FFFF00" in src, (
        "the gate must write the fill via the #FFFF00 backColor (LD-107 Q2) — AC2."
    )
    assert "formatter" in src and '"0.00%"' in src, (
        "the gate must write the 0.00% numFmt via the style `formatter` (LD-107 Q2) — AC2."
    )
    assert '"bold": True' in src or '"bold":True' in src, (
        "the gate must write the bold font (LD-107 Q2) — AC2."
    )


def test_gate_reads_the_style_leg_via_the_shipped_export_reader():
    src = _src()
    assert "SheetsExportReader" in src, (
        "the gate must read the style back through the shipped LD-114 export reader "
        "(SheetsExportReader) — the ONLY full style/numFmt fidelity read (AC2)."
    )
    assert "read_workbook(" in src or "export_xlsx(" in src, (
        "the gate must export→parse the disposable via the export reader "
        "(read_workbook/export_xlsx) — the export→stdlib-parse leg (AC2)."
    )


def test_gate_asserts_exact_bold_fill_numfmt_fidelity():
    src = _src()
    assert "assert_cell_style(" in src, (
        "the gate must assert the parsed cell carries EXACTLY the written style with "
        "assert_cell_style (the absolute per-cell fidelity check) — not just `some style` "
        "(AC2, the amplifier)."
    )
    # the three exact attributes LD-107 Q2 wrote — bold + fill ARGB + numFmt pattern.
    assert "bold=True" in src, "the gate must assert bold=True (AC2)."
    assert '"FFFFFF00"' in src or "fill_rgb=\"FFFFFF00\"" in src, (
        "the gate must assert the fill ARGB is FFFFFF00 (the #FFFF00 → ARGB the export "
        "reader recovers) — AC2."
    )
    assert 'num_fmt="0.00%"' in src or '"0.00%"' in src, (
        "the gate must assert the numFmt pattern is 0.00% (AC2)."
    )


def test_gate_proves_the_style_write_surgical_against_guard_neighbours():
    src = _src()
    # the surgical proof: baseline vs post export diffed, EVERY style change within the
    # target A1 — a stray fill/bold on a guard neighbour reddens (the restore-verify /
    # baseline-confirm amplifier).
    assert "assert_style_surgical(" in src, (
        "the gate must prove the style write surgical via assert_style_surgical(baseline, "
        "post, [target]) — no stray style on a guard neighbour (AC2, D7)."
    )
    assert "guard" in src, (
        "the baseline must author guard-neighbour cells around the styled target so the "
        "surgical style diff has something to protect (AC2)."
    )


# --------------------------------------------------------------------------- #
# AC3 — restore + delete leak-proof (harness lifecycle) + AC4 zero-orphan        #
# --------------------------------------------------------------------------- #

def test_gate_self_provisions_and_deletes_via_the_harness():
    src = _src()
    assert "H.disposable(" in src or "disposable(" in src, (
        "the gate must self-provision its disposable via the LD-112 harness disposable() "
        "context manager (create → ... → delete-in-`finally`) — AC3/AC5."
    )
    assert "close_out(" in src, (
        "the gate must run the LD-112 zero-orphan close-out re-querying every ledger "
        "token — the independent proof nothing leaked (AC3/AC4)."
    )
    assert "raise_if_orphans" in src or "all_clean" in src, (
        "the gate must assert the close-out found ZERO orphan disposables (AC4)."
    )


# --------------------------------------------------------------------------- #
# AC5 — writes ONLY against a self-provisioned disposable; WRITE creds only       #
# --------------------------------------------------------------------------- #

def test_gate_uses_write_credentials_only():
    src = _src()
    assert "from_write_credentials" in src, (
        "the gate must build its client + lifecycle gateway + styler + export reader from "
        "*_from_write_credentials (LARK_WRITE_APP_* — the write-only resolver that never "
        "borrows read/legacy creds) — AC5, D1/D7."
    )
    # The WRITE app owns what it creates, so the gate needs no read-app collaborator — it
    # must NOT reach for read credentials at all here.
    assert "get_read_credentials" not in src, (
        "the Sheets style-leg gate needs NO read app (the WRITE app owns the disposable it "
        "creates and exports its own style) — it must not reference get_read_credentials "
        "(AC5, D1)."
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
        # never the sheets READ canary / base scratch — a read-only target must never be a
        # WRITE destination (the load-bearing D7 invariant for this family).
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
            f"the Sheets style-leg gate must not reference {token!r} — it writes ONLY "
            "against the disposable it self-provisions; never the scratch sheet, the read "
            "canary, the zoo, the sandbox, or a real document (AC5, D7)."
        )
