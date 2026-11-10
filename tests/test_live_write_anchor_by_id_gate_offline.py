"""Offline guards for THE S4 GATE — the by-id anchoring round-trip (LD-137).

NOT marked ``live_write``: these run in the default ``pytest -q`` with no creds and no
network. They are the automatable half of AC6 — they pin the *shape* of the credential-gated
gate (``tests/test_live_write_anchor_by_id_gate.py``) so a future edit cannot quietly break the
discipline it depends on. The binding round-trip itself (author → take the ids back → insert by
id → compare-and-swap refusal → delete by id → stale-race refusal → vanished-id refusal →
teardown) runs only under ``pytest -m live_write`` at QA with write creds.

Mirrors ``tests/test_live_write_table_create_gate_offline.py`` (the S2 gate's guards),
retargeted at what S4 adds: the follow-ups are anchored **by the ids ``apply`` returned**, and
both staleness arms an id anchor introduces are proven against a real document.
"""
from pathlib import Path

GATE_SRC = Path(__file__).resolve().parent / "test_live_write_anchor_by_id_gate.py"


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The ring's discipline — same marker, deselected by default, skips LOUDLY      #
# --------------------------------------------------------------------------- #

def test_s4_gate_file_exists():
    assert GATE_SRC.exists(), (
        f"the S4 by-id anchoring gate {GATE_SRC.name} must exist (LD-137 AC6).")


def test_s4_gate_marked_live_write():
    assert "pytest.mark.live_write" in _src(), (
        "the S4 gate must carry the `live_write` marker so it stays deselected by the "
        "default addopts and joins the same ring as W0/W1/W2/W3/S2.")


def test_s4_gate_skips_loudly_when_write_creds_unset():
    src = _src()
    assert "live_write_missing_reason" in src and "pytest.skip" in src, (
        "the S4 gate must gate on canary_support.live_write_missing_reason() and "
        "pytest.skip(...) — never run silently past absent creds.")


# --------------------------------------------------------------------------- #
# What S4 adds — the follow-ups are anchored by the ids apply() RETURNED         #
# --------------------------------------------------------------------------- #

def test_s4_gate_anchors_by_an_id_apply_returned():
    src = _src()
    assert "AnchorById" in src, (
        "the gate must use AnchorById — the anchor kind S4 shipped (AC1).")
    assert "created_block_ids" in src, (
        "the gate must anchor by an id apply() RETURNED, not a hand-written literal — that "
        "loop (author → created_block_ids → follow up by id) IS dogfood F19's ask (AC6).")
    assert "block_id=paragraph_id" in src or "block_id=by_id_block" in src, (
        "an AnchorById in the gate must be constructed from a captured live id.")


def test_s4_gate_covers_both_an_insert_and_a_delete_by_id():
    src = _src()
    assert "InsertRequest(" in src and "DeleteRequest(" in src, (
        "AC6 names a live id-anchored INSERT **and** DELETE — both must be in the ring.")
    assert "reference=AnchorById" in src, "the insert must be anchored by id"
    assert "target=AnchorById" in src, (
        "the delete must be anchored by id — 'deletes cannot target block ids' is F19's "
        "headline complaint.")


def test_s4_gate_goes_only_through_the_plan_gate_for_its_write_ops():
    src = _src()
    assert "dry_run(" in src and "apply(" in src, (
        "every authored change must go through dry_run → Plan → apply, the only path content "
        "reaches Lark by (AC6).")


def test_s4_gate_asserts_the_by_id_precondition_is_captured():
    src = _src()
    assert "precondition_text" in src, (
        "the gate must assert the plan captured the by-id staleness precondition — it is what "
        "makes an id-anchored write a compare-and-swap (AC4).")
    assert "precondition_text is None" in src, (
        "…and that a QUOTE-anchored entry carries NONE, which is what keeps the shipped wire "
        "format byte-identical.")


def test_s4_gate_proves_the_compare_and_swap_refusal_live():
    src = _src()
    assert "STALE_ANCHOR" in src, (
        "AC4's contract is drift → stale-anchor; the gate must assert the typed reason.")
    assert "_patch_block(" in src, (
        "the compare-and-swap arm needs a CONCURRENT out-of-band edit to the anchored block — "
        "otherwise nothing drifts and the refusal is never exercised.")
    assert "NEVER_LINE not in md_drifted" in src, (
        "a refusal must be proven by RE-READING the document (the replacement text never "
        "appears), not merely by the apply-log claiming it skipped.")


def test_s4_gate_proves_the_stale_race_when_the_id_is_deleted_between_plan_and_apply():
    src = _src()
    assert "race_plan" in src, (
        "the amplifier's stale race — an id deleted BETWEEN plan and apply — must be a real "
        "arm of the gate: a plan built while the block existed, applied after it is gone.")
    assert "md_race == md_deleted" in src, (
        "the stale-race entry must be proven to have written NOTHING (the document is "
        "byte-identical to before the attempt).")


def test_s4_gate_proves_a_vanished_id_refuses_with_the_id_named():
    src = _src()
    assert "RefusalReason.NOT_FOUND" in src, (
        "AC3: a vanished id refuses not-found.")
    assert "refusal.detail" in src, (
        "…and the LD-131 mandatory detail must be asserted to NAME the id — a detail-less "
        "refusal gives a consumer nothing to recover from.")


def test_s4_gate_asserts_the_insert_position_semantics_read_back():
    src = _src()
    assert "InsertPosition.AFTER" in src and "_line_index(" in src, (
        "an id-anchored insert must be proven to land in the right PLACE (immediately after "
        "its reference), not merely to have been created (AC1).")


def test_s4_gate_proves_the_delete_captured_its_removed_payload():
    src = _src()
    assert "removed_payload" in src, (
        "deletion is destructive: the gate must assert the removed-block payload came back, "
        "so an id-anchored delete stays as reconstructable as a quote-anchored one.")


def test_s4_gate_proves_the_writes_were_purely_additive_or_surgical():
    src = _src()
    assert "difflib" in src, (
        "the gate must diff the downloads to prove each insert only ADDED lines and the "
        "delete removed exactly its own (AC6).")


def test_s4_gate_resolves_against_the_parsed_tree():
    assert "parse_docx_tree" in _src(), (
        "anchors — including an AnchorById — resolve against the reader's parsed node tree, "
        "not the rendered Markdown; the gate must parse it.")


def test_s4_gate_keeps_the_reader_determinism_control():
    assert "md_baseline == md_baseline_2" in _src(), (
        "two downloads of the unchanged doc must be asserted byte-identical first — that is "
        "what makes every later diff attributable to a write.")


# --------------------------------------------------------------------------- #
# LD-141 — the ROOT arm. The document root's own text lives under `page.elements`,#
# a shape no other block has, so the by-id precondition basis for it is provable  #
# only against a live root block. The ring's blindness to the root is HOW a false #
# `stale-anchor` on every id-anchored root write shipped past a green suite.       #
# --------------------------------------------------------------------------- #

def test_s4_gate_covers_an_id_anchored_append_into_the_document_ROOT():
    src = _src()
    assert "InsertPosition.APPEND_INTO" in src, (
        "LD-141: the root is the only anchor target in an empty document and APPEND_INTO is "
        "the only position it accepts, so the ring must exercise that position.")
    assert "AnchorById(block_id=doc_id)" in src, (
        "the root arm must anchor the document ROOT by its own id (a docx document_id IS its "
        "root block id) — the one node whose precondition basis is its page title, not its "
        "`content`.")


def test_s4_gate_root_arm_runs_a_quote_anchored_control():
    src = _src()
    assert "Anchor(quote=root_title" in src, (
        "LD-141 was a by-id-ONLY regression, and only the title-quote control proves that: "
        "the same insert, the same document, the other anchor kind, one run.")
    assert "ROOT_BY_ID_LINE in md_root" in src, (
        "the root arm must be proven by RE-READING the document — an apply-log claiming "
        "'inserted' is not evidence the line landed.")


def test_s4_gate_root_arm_asserts_the_precondition_is_the_page_title():
    src = _src()
    assert "precondition_text == root_title" in src, (
        "the root arm must assert the captured precondition IS the live page title — that "
        "equality is the whole of LD-141, and asserting only the outcome would let a "
        "precondition captured on the wrong basis pass again the moment the title is empty.")


# --------------------------------------------------------------------------- #
# Allowed targets only — a doc the gate creates itself; always torn down         #
# --------------------------------------------------------------------------- #

def test_s4_gate_self_provisions_its_own_doc():
    assert "create_document" in _src(), (
        "the gate must self-provision its target doc via create_document — never a "
        "pre-existing document.")


def test_s4_gate_never_references_canary_zoo_sandbox_or_external_docs():
    src = _src()
    forbidden = [
        "LARKDOCIO_CANARY_DOC", "CANARY_DOC_ENV", "canary_doc_url",
        "LARKDOCIO_BLOCKZOO_DOC", "BLOCKZOO_DOC_ENV", "blockzoo_doc_url",
        "LARKDOCIO_WRITE_SCRATCH_DOC",
        "larksuite.com/docx/", "feishu.cn/docx/", "feishu.cn/wiki/", "larksuite.com/wiki/",
    ]
    for token in forbidden:
        assert token not in src, (
            f"the S4 gate must not reference {token!r} — it writes only against the doc it "
            "creates itself; never the canary, the zoo, the sandbox, or a real document.")


def test_s4_gate_uses_write_credentials_for_writes():
    assert "get_write_credentials" in _src(), (
        "writes must come from get_write_credentials() — the write-only resolver that never "
        "borrows read/legacy creds.")


def test_s4_gate_reader_half_prefers_read_credentials():
    assert "get_read_credentials" in _src(), (
        "the reader half must prefer get_read_credentials() — the two-app least-privilege "
        "separation.")


def test_s4_gate_tears_down_in_a_finally():
    src = _src()
    assert "finally" in src, (
        "the gate must tear down in a `finally` so a mid-round-trip failure still leaves "
        "nothing behind.")
    assert "batch_delete" in src and "delete_document" in src, (
        "teardown must empty the doc's children and best-effort trash the doc — no orphaned "
        "self-created doc, and no orphaned blocks.")
    assert "emptied" in src, (
        "the gate must assert the restore actually removed the authored content — the "
        "teardown is a binding part of the gate.")
