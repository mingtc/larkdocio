"""Offline guards for THE W1 GATE live round-trip (LD-069).

NOT marked ``live_write`` — these run in the default ``pytest -q`` with no creds
and no network. They are the automatable half of LD-069: they pin the *shape* of
the credential-gated W1-gate round-trip (``tests/test_live_write_w1_gate.py``) so
that a future edit cannot quietly break the discipline the gate depends on. The
binding round-trip itself (AC2 — download → EditRequest → resolve → dry-run → apply
→ re-download → diff → restore) only runs under ``pytest -m live_write`` at QA with
write creds; these guards prove the *scaffolding* offline.

They mirror ``tests/test_live_write_offline.py`` (the W0 harness's offline guards):

* AC1 — the W1-gate ring reuses the same ``live_write`` marker and **skips loudly**
  (via ``canary_support.live_write_missing_reason``) when ``LARK_WRITE_APP_*`` is
  unset — never a silent pass; it stays deselected by the default ``addopts``.
* AC2 — the gate drives the **real S1–S4 apply engine** end-to-end
  (``EditRequest`` → ``dry_run`` → ``apply``) against the reader's parsed **tree**
  (``parse_docx_tree``), not the low-level ``_patch_block`` the W0 harness used.
* AC3 — a static guard proving the gate writes **only** against a doc it creates
  itself (``create_document``): it never references ``LARKDOCIO_CANARY_DOC`` /
  ``LARKDOCIO_BLOCKZOO_DOC`` / the standing sandbox / any hard-coded external doc
  URL for its writes.
* AC4 — writes go through ``get_write_credentials`` (write-only, never read/legacy);
  the reader half prefers ``get_read_credentials`` for the download.
"""
from pathlib import Path

GATE_SRC = Path(__file__).resolve().parent / "test_live_write_w1_gate.py"


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# AC1 — same marker, deselected by default, skips LOUDLY without write creds    #
# --------------------------------------------------------------------------- #

def test_w1_gate_file_exists():
    assert GATE_SRC.exists(), (
        "the W1-gate live round-trip test file "
        f"{GATE_SRC.name} must exist (LD-069 AC1/AC2)."
    )


def test_w1_gate_marked_live_write():
    src = _src()
    assert "pytest.mark.live_write" in src, (
        "the W1-gate round-trip must carry the `live_write` marker so it stays "
        "deselected by the default addopts (AC1)."
    )


def test_w1_gate_skips_loudly_when_write_creds_unset():
    src = _src()
    # Reuse the W0 skip helper (never a silent pass — a clear message naming
    # LARK_WRITE_APP_* when the write pair is unset).
    assert "live_write_missing_reason" in src, (
        "the W1-gate must gate on canary_support.live_write_missing_reason() so it "
        "skips loudly when LARK_WRITE_APP_* is unset (AC1)."
    )
    assert "pytest.skip" in src, (
        "the W1-gate must pytest.skip(...) with the missing-creds reason, never run "
        "silently past absent creds (AC1)."
    )


# --------------------------------------------------------------------------- #
# AC2 — the gate drives the REAL S1–S4 apply engine over the parsed tree        #
# --------------------------------------------------------------------------- #

def test_w1_gate_builds_an_edit_request():
    src = _src()
    assert "EditRequest" in src and "Anchor" in src, (
        "the gate must express the edit as an EditRequest(anchor=Anchor(quote, "
        "breadcrumb), replacement) built from the downloaded baseline (AC2)."
    )


def test_w1_gate_runs_dry_run_then_apply():
    src = _src()
    assert "dry_run(" in src, (
        "the gate must produce a dry-run Plan via write.preview.dry_run (S3) — the "
        "only input the apply engine accepts (AC2)."
    )
    assert "apply(" in src, (
        "the gate must execute the plan via write.apply.apply (S4) — the real apply "
        "engine, not a hand-rolled _patch_block (AC2)."
    )


def test_w1_gate_resolves_against_the_parsed_tree():
    src = _src()
    # The resolver (S2) needs the reader's parsed NODE TREE (breadcrumb + block_id
    # provenance), not the rendered Markdown — so the gate must parse the tree.
    assert "parse_docx_tree" in src, (
        "the gate must obtain the reader's parsed node tree via "
        "Parser.parse_docx_tree so resolve/dry_run can address a block (AC2)."
    )


# --------------------------------------------------------------------------- #
# AC3 — writes ONLY against a doc the gate creates itself                        #
# --------------------------------------------------------------------------- #

def test_w1_gate_self_provisions_its_own_doc():
    src = _src()
    assert "create_document" in src, (
        "the gate must self-provision its target doc via create_document — the W0 "
        "create→teardown mechanism (AC3)."
    )


def test_w1_gate_never_references_canary_zoo_sandbox_or_external_docs():
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
        # never the standing maintainer sandbox either — this gate writes ONLY to the doc it
        # creates itself (zero blast radius), so it must not reach for the sandbox.
        "LARKDOCIO_WRITE_SCRATCH_DOC",
        # no hard-coded external doc URL literal — never a pre-existing / real doc.
        "larksuite.com/docx/",
        "feishu.cn/docx/",
        "feishu.cn/wiki/",
        "larksuite.com/wiki/",
    ]
    for token in forbidden:
        assert token not in src, (
            f"the W1 gate must not reference {token!r} — it writes only against the "
            "doc it creates itself; never the canary, the zoo, the sandbox, or a "
            "real document (AC3)."
        )


# --------------------------------------------------------------------------- #
# AC4 — write creds for writes; read creds preferred for the reader half         #
# --------------------------------------------------------------------------- #

def test_w1_gate_uses_write_credentials_for_writes():
    src = _src()
    assert "get_write_credentials" in src, (
        "the gate must build its WriteClient from get_write_credentials() — the "
        "write-only resolver that never borrows read/legacy creds (AC4)."
    )


def test_w1_gate_reader_half_prefers_read_credentials():
    src = _src()
    assert "get_read_credentials" in src, (
        "the reader half must prefer get_read_credentials() for the download — the "
        "two-app least-privilege separation the W1 gate proves (AC4)."
    )
