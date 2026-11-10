"""Offline guards for THE W2 GATE live round-trip (LD-073).

NOT marked ``live_write`` — these run in the default ``pytest -q`` with no creds
and no network. They are the automatable half of LD-073: they pin the *shape* of
the credential-gated W2-gate table round-trip
(``tests/test_live_write_w2_gate.py``) so a future edit cannot quietly break the
discipline the gate depends on. The binding round-trip itself (AC2 — create table →
baseline → ``table_locator`` ``EditRequest`` → resolve → dry-run → apply →
re-download → diff (only the target cell's line changed) → teardown) only runs under
``pytest -m live_write`` at QA with write creds; these guards prove the *scaffolding*
offline.

They mirror ``tests/test_live_write_w1_gate_offline.py`` (the W1 gate's offline
guards), extended for the W2 table path:

* AC1 — the W2-gate ring reuses the same ``live_write`` marker and **skips loudly**
  (via ``canary_support.live_write_missing_reason``) when ``LARK_WRITE_APP_*`` is
  unset — never a silent pass; it stays deselected by the default ``addopts``.
* AC2 — the gate **creates a table** (``create_children`` with a docx table block),
  builds a **``TableLocator`` ``EditRequest``** (row-key + column-target), drives the
  **real S2–S4 pipeline** end-to-end (``resolve`` via ``dry_run`` → ``apply``) against
  the reader's parsed **tree** (``parse_docx_tree``), and asserts the **surgical diff**
  (only the target cell's line changed) plus a **byte-identical teardown**.
* AC3 — a static guard proving the gate writes **only** against a doc it creates
  itself (``create_document``): it never references ``LARKDOCIO_CANARY_DOC`` /
  ``LARKDOCIO_BLOCKZOO_DOC`` / the standing sandbox / any hard-coded external doc
  URL for its writes. (The gate takes AC3's hermetic *self-created-doc* arm — the
  spec's recommended fully-hermetic default — so it never reaches for the sandbox.)
* AC4 — writes go through ``get_write_credentials`` (write-only, never read/legacy);
  the reader half prefers ``get_read_credentials`` for the download; teardown runs in
  a ``finally`` so a mid-round-trip failure still leaves nothing behind.
"""
from pathlib import Path

GATE_SRC = Path(__file__).resolve().parent / "test_live_write_w2_gate.py"


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# AC1 — same marker, deselected by default, skips LOUDLY without write creds    #
# --------------------------------------------------------------------------- #

def test_w2_gate_file_exists():
    assert GATE_SRC.exists(), (
        "the W2-gate live round-trip test file "
        f"{GATE_SRC.name} must exist (LD-073 AC1/AC2)."
    )


def test_w2_gate_marked_live_write():
    src = _src()
    assert "pytest.mark.live_write" in src, (
        "the W2-gate round-trip must carry the `live_write` marker so it stays "
        "deselected by the default addopts and joins the same ring as W0/W1 (AC1)."
    )


def test_w2_gate_skips_loudly_when_write_creds_unset():
    src = _src()
    # Reuse the W0 skip helper (never a silent pass — a clear message naming
    # LARK_WRITE_APP_* when the write pair is unset).
    assert "live_write_missing_reason" in src, (
        "the W2-gate must gate on canary_support.live_write_missing_reason() so it "
        "skips loudly when LARK_WRITE_APP_* is unset (AC1)."
    )
    assert "pytest.skip" in src, (
        "the W2-gate must pytest.skip(...) with the missing-creds reason, never run "
        "silently past absent creds (AC1)."
    )


# --------------------------------------------------------------------------- #
# AC2 — create a table, build a TableLocator, drive the real S2–S4 pipeline      #
# --------------------------------------------------------------------------- #

def test_w2_gate_creates_a_table():
    src = _src()
    # The gate provisions its OWN table via the create-children docx API (block_type
    # 31 with a row_size/column_size property) — not a pre-existing table anywhere.
    assert "create_children" in src, (
        "the gate must create its table via WriteClient.create_children (the docx "
        "block-create API) — no pre-existing table is used (AC2)."
    )
    assert "column_size" in src and "row_size" in src, (
        "the gate must create the table by its property (row_size / column_size) so "
        "Lark auto-provisions the cell grid (AC2)."
    )


def test_w2_gate_builds_a_table_locator_edit_request():
    src = _src()
    assert "TableLocator" in src and "EditRequest" in src, (
        "the gate must express the table-cell edit as an "
        "EditRequest(anchor=TableLocator(row_key, column_..., breadcrumb), "
        "replacement) — a bare quote is useless in a table (AC2)."
    )
    assert "row_key" in src, (
        "the TableLocator must locate the row by a verbatim key-cell quote (row_key) "
        "taken from the created table (AC2)."
    )


def test_w2_gate_runs_dry_run_then_apply():
    src = _src()
    assert "dry_run(" in src, (
        "the gate must produce a dry-run Plan via write.preview.dry_run (S3) — the "
        "only input the apply engine accepts (AC2)."
    )
    assert "apply(" in src, (
        "the gate must execute the plan via write.apply.apply (S4) — the real apply "
        "engine, not a hand-rolled _patch_block (AC2)."
    )


def test_w2_gate_resolves_against_the_parsed_tree():
    src = _src()
    # The table resolver (S2) needs the reader's parsed NODE TREE (block_id provenance
    # + the cell grid), not the rendered Markdown — so the gate must parse the tree.
    assert "parse_docx_tree" in src, (
        "the gate must obtain the reader's parsed node tree via "
        "Parser.parse_docx_tree so resolve/dry_run can address a cell (AC2)."
    )


def test_w2_gate_asserts_only_the_target_cell_line_changed():
    src = _src()
    # The binding surgical-diff assertion: exactly one Markdown line differs between
    # the baseline and the post-apply download (the target cell's row line).
    assert "splitlines" in src, (
        "the gate must diff the two reader outputs line-by-line to prove the edit "
        "was surgical (AC2)."
    )
    assert "len(changed) == 1" in src, (
        "the gate must assert EXACTLY ONE line changed (only the target cell's row "
        "line) — the surgical-diff heart of the W2 gate (AC2)."
    )


# --------------------------------------------------------------------------- #
# AC3 — writes ONLY against a doc the gate creates itself (hermetic default)     #
# --------------------------------------------------------------------------- #

def test_w2_gate_self_provisions_its_own_doc():
    src = _src()
    assert "create_document" in src, (
        "the gate must self-provision its target doc via create_document — the W0 "
        "create→teardown mechanism, the hermetic default arm of AC3."
    )


def test_w2_gate_never_references_canary_zoo_sandbox_or_external_docs():
    src = _src()
    forbidden = [
        # never the read canary
        "LARKDOCIO_CANARY_DOC",
        "CANARY_DOC_ENV",
        "canary_doc_url",
        # never the block-zoo doc
        "LARKDOCIO_BLOCKZOO_DOC",
        "BLOCKZOO_DOC_ENV",
        "blockzoo_doc_url",
        # never the standing maintainer sandbox — this gate takes AC3's hermetic self-created
        # arm (zero blast radius), so it must not reach for the sandbox either.
        "LARKDOCIO_WRITE_SCRATCH_DOC",
        # no hard-coded external doc URL literal — never a pre-existing / real doc.
        "larksuite.com/docx/",
        "feishu.cn/docx/",
        "feishu.cn/wiki/",
        "larksuite.com/wiki/",
    ]
    for token in forbidden:
        assert token not in src, (
            f"the W2 gate must not reference {token!r} — it writes only against the "
            "doc it creates itself; never the canary, the zoo, the sandbox, or a "
            "real document (AC3)."
        )


# --------------------------------------------------------------------------- #
# AC4 — write creds for writes; read creds preferred for the reader half;        #
#       teardown in a finally so nothing persists                                #
# --------------------------------------------------------------------------- #

def test_w2_gate_uses_write_credentials_for_writes():
    src = _src()
    assert "get_write_credentials" in src, (
        "the gate must build its WriteClient from get_write_credentials() — the "
        "write-only resolver that never borrows read/legacy creds (AC4)."
    )


def test_w2_gate_reader_half_prefers_read_credentials():
    src = _src()
    assert "get_read_credentials" in src, (
        "the reader half must prefer get_read_credentials() for the download — the "
        "two-app least-privilege separation the gate proves (AC4)."
    )


def test_w2_gate_tears_down_in_a_finally():
    src = _src()
    assert "finally" in src, (
        "the gate must tear down in a `finally` so a mid-round-trip failure still "
        "leaves nothing behind (AC4 — restores on success AND failure)."
    )
    assert "batch_delete" in src and "delete_document" in src, (
        "teardown must empty the doc's children (batch_delete) and best-effort trash "
        "the doc (delete_document) — no orphaned self-created doc (AC4)."
    )
    assert "emptied" in src, (
        "the gate must assert the restore actually emptied the target content — the "
        "byte-identical teardown is a binding part of the gate (AC2/AC4)."
    )
