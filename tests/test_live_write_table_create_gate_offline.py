"""Offline guards for THE S2 GATE — the table-creation round-trip (LD-135).

NOT marked ``live_write``: these run in the default ``pytest -q`` with no creds and no
network. They are the automatable half of AC6 — they pin the *shape* of the credential-gated
gate (``tests/test_live_write_table_create_gate.py``) so a future edit cannot quietly break
the discipline it depends on. The binding round-trip itself (create the tables **through the
gate** → read them back → edit a created cell via ``TableLocator`` → surgical diff →
teardown) runs only under ``pytest -m live_write`` at QA with write creds.

Mirrors ``tests/test_live_write_w2_gate_offline.py`` (the W2 gate's guards), retargeted at
what S2 adds: the table is created **by the engine through the plan gate**, not by a raw
``create_children`` call in the test.
"""
from pathlib import Path

GATE_SRC = Path(__file__).resolve().parent / "test_live_write_table_create_gate.py"


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The ring's discipline — same marker, deselected by default, skips LOUDLY      #
# --------------------------------------------------------------------------- #

def test_s2_gate_file_exists():
    assert GATE_SRC.exists(), (
        f"the S2 table-creation gate {GATE_SRC.name} must exist (LD-135 AC6).")


def test_s2_gate_marked_live_write():
    assert "pytest.mark.live_write" in _src(), (
        "the S2 gate must carry the `live_write` marker so it stays deselected by the "
        "default addopts and joins the same ring as W0/W1/W2/W3.")


def test_s2_gate_skips_loudly_when_write_creds_unset():
    src = _src()
    assert "live_write_missing_reason" in src and "pytest.skip" in src, (
        "the S2 gate must gate on canary_support.live_write_missing_reason() and "
        "pytest.skip(...) — never run silently past absent creds.")


# --------------------------------------------------------------------------- #
# What S2 adds — the TABLE is created BY THE ENGINE, through the plan gate        #
# --------------------------------------------------------------------------- #

def test_s2_gate_authors_the_table_through_the_typed_model():
    src = _src()
    assert "NewBlock.table(" in src, (
        "the gate must author its tables with NewBlock.table(...) — the typed creatable "
        "content S2 shipped (AC1/AC2).")
    assert "header_row=True" in src, (
        "the gate must exercise the optional header row (AC1) — the header/headerless "
        "distinction is a create-payload difference.")


def test_s2_gate_creates_the_table_only_through_the_plan_gate():
    src = _src()
    assert "dry_run(" in src and "apply(" in src, (
        "the table must be created through dry_run → Plan → apply, the only path content "
        "reaches Lark by (AC6).")
    # The W2 gate built its table with a RAW create_children call; S2's whole point is that
    # the ENGINE creates it, so the gate must not hand-roll a table payload.
    assert "block_type\": 31" not in src and "block_type': 31" not in src, (
        "the S2 gate must NOT hand-roll a type-31 table payload — the engine's encoder is "
        "what is under test.")
    # …and it must not author the grid property either. Reading it back off the LIVE block
    # (``.get("row_size")``) is the assertion; writing it (a ``"row_size":`` dict key) would
    # mean the gate, not the encoder, decided the grid.
    for authored_key in ('"row_size":', '"column_size":', '"header_row":'):
        assert authored_key not in src, (
            f"the S2 gate must not author {authored_key} itself — the grid property is the "
            "encoder's business, and a gate that writes it is not testing the encoder (AC2).")


def test_s2_gate_asserts_the_authored_grid_reads_back():
    src = _src()
    assert "|---|---|" in src, (
        "the gate must assert the created table reads back as a GFM table (the header "
        "delimiter row) — the round-trip, not just a 200 from the API (AC6).")
    assert "header_row=False" in src, (
        "the gate must author a HEADERLESS grid too — the header flag is a create-payload "
        "difference and both forms must be proven live (AC1/AC2).")
    assert 'get("header_row")' in src, (
        "header_row must be asserted on the LIVE block property: Lark OMITS a false flag "
        "from the payload it returns, so the Markdown projection cannot prove it reached "
        "the document (LD-135's documented lossiness).")


def test_s2_gate_proves_the_write_was_purely_additive():
    src = _src()
    assert "difflib" in src, (
        "the gate must diff the baseline against the post-insert download to prove the "
        "insert added lines and changed none (AC6).")


def test_s2_gate_composes_creation_with_the_table_locator_edit_path():
    src = _src()
    assert "TableLocator" in src and "EditRequest" in src, (
        "the composition S2 exists for: a table the engine created must be addressable by "
        "the shipped TableLocator cell-edit path (the create→edit composition test).")
    assert "len(changed) == 1" in src, (
        "the cell edit on the created table must be proven SURGICAL — exactly one Markdown "
        "line changed (the W2 gate's discipline, applied to a created table).")


def test_s2_gate_resolves_against_the_parsed_tree():
    assert "parse_docx_tree" in _src(), (
        "anchors and the TableLocator resolve against the reader's parsed node tree, not "
        "the rendered Markdown — the gate must parse it.")


# --------------------------------------------------------------------------- #
# Allowed targets only — a doc the gate creates itself; always torn down         #
# --------------------------------------------------------------------------- #

def test_s2_gate_self_provisions_its_own_doc():
    assert "create_document" in _src(), (
        "the gate must self-provision its target doc via create_document — never a "
        "pre-existing document.")


def test_s2_gate_never_references_canary_zoo_sandbox_or_external_docs():
    src = _src()
    forbidden = [
        "LARKDOCIO_CANARY_DOC", "CANARY_DOC_ENV", "canary_doc_url",
        "LARKDOCIO_BLOCKZOO_DOC", "BLOCKZOO_DOC_ENV", "blockzoo_doc_url",
        "LARKDOCIO_WRITE_SCRATCH_DOC",
        "larksuite.com/docx/", "feishu.cn/docx/", "feishu.cn/wiki/", "larksuite.com/wiki/",
    ]
    for token in forbidden:
        assert token not in src, (
            f"the S2 gate must not reference {token!r} — it writes only against the doc it "
            "creates itself; never the canary, the zoo, the sandbox, or a real document.")


def test_s2_gate_uses_write_credentials_for_writes():
    assert "get_write_credentials" in _src(), (
        "writes must come from get_write_credentials() — the write-only resolver that never "
        "borrows read/legacy creds.")


def test_s2_gate_reader_half_prefers_read_credentials():
    assert "get_read_credentials" in _src(), (
        "the reader half must prefer get_read_credentials() — the two-app least-privilege "
        "separation.")


def test_s2_gate_tears_down_in_a_finally():
    src = _src()
    assert "finally" in src, (
        "the gate must tear down in a `finally` so a mid-round-trip failure still leaves "
        "nothing behind.")
    assert "batch_delete" in src and "delete_document" in src, (
        "teardown must empty the doc's children and best-effort trash the doc — no orphaned "
        "self-created doc, and no orphaned table.")
    assert "emptied" in src, (
        "the gate must assert the restore actually removed the authored table content — the "
        "teardown is a binding part of the gate.")
