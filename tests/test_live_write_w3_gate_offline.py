"""Offline guards for THE W3 GATE live round-trip (LD-078).

NOT marked ``live_write`` — these run in the default ``pytest -q`` with no creds
and no network. They are the automatable half of LD-078, in two parts:

1. **Pure-logic unit tests** of the gate's **full-doc diff** helpers
   (``only_insertion`` / ``only_deletion`` / ``only_single_line_edit``, imported
   from ``tests/test_live_write_w3_gate``). These prove the surgical-ness assertions
   the gate relies on — the **binding difference from W1/W2's region diffs**: because
   an insert/delete changes the **block count**, W3 must diff the **whole document**
   (not a same-length line-by-line region) and prove that the *only* change is the
   intended insertion / deletion / single-line sub-span edit.
2. **Source-inspection guards** that pin the *shape* of the credential-gated W3-gate
   round-trip (``tests/test_live_write_w3_gate.py``) so a future edit cannot quietly
   break the discipline the gate depends on. The binding round-trip itself (AC2–AC6)
   only runs under ``pytest -m live_write`` at QA with write creds; these guards prove
   the *scaffolding* offline.

Mirrors ``tests/test_live_write_w2_gate_offline.py`` (the W2 gate's offline guards),
extended for the W3 insert / delete / sub-span paths and their full-doc diffs.
"""
from pathlib import Path

import pytest

from test_live_write_w3_gate import (
    only_deletion,
    only_insertion,
    only_single_line_edit,
)

GATE_SRC = Path(__file__).resolve().parent / "test_live_write_w3_gate.py"


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


# =========================================================================== #
# PART 1 — pure-logic unit tests of the full-doc diff helpers                  #
# (the surgical-ness heart of the W3 gate; the binding difference from W1/W2)  #
# =========================================================================== #

# --------------------------------------------------------------------------- #
# only_insertion — the whole-doc diff is EXACTLY an insertion of the new para  #
# --------------------------------------------------------------------------- #

def test_only_insertion_accepts_a_pure_insertion():
    before = "# H\n\nalpha\n\nbeta\n"
    after = "# H\n\nalpha\n\nINS-tok\n\nbeta\n"
    inserted = only_insertion(before, after, "INS-tok")
    # every inserted line is blank or the sentinel paragraph — nothing else appeared.
    assert any("INS-tok" in ln for ln in inserted)
    assert all((not ln.strip()) or ("INS-tok" in ln) for ln in inserted)


def test_only_insertion_rejects_a_concurrent_replacement():
    # An insertion that ALSO mutated an existing line is NOT surgical.
    before = "# H\n\nalpha\n\nbeta\n"
    after = "# H\n\nalphaX\n\nINS-tok\n\nbeta\n"
    with pytest.raises(AssertionError):
        only_insertion(before, after, "INS-tok")


def test_only_insertion_rejects_a_concurrent_deletion():
    # An insertion that ALSO removed an existing line is NOT surgical.
    before = "# H\n\nalpha\n\nbeta\n"
    after = "# H\n\nINS-tok\n\nbeta\n"  # 'alpha' disappeared too
    with pytest.raises(AssertionError):
        only_insertion(before, after, "INS-tok")


def test_only_insertion_rejects_missing_sentinel():
    before = "# H\n\nalpha\n\nbeta\n"
    after = "# H\n\nalpha\n\nSOMETHING-ELSE\n\nbeta\n"
    with pytest.raises(AssertionError):
        only_insertion(before, after, "INS-tok")


def test_only_insertion_rejects_no_change():
    before = "# H\n\nalpha\n"
    with pytest.raises(AssertionError):
        only_insertion(before, before, "INS-tok")


# --------------------------------------------------------------------------- #
# only_deletion — the whole-doc diff is EXACTLY a deletion of the target block  #
# --------------------------------------------------------------------------- #

def test_only_deletion_accepts_a_pure_deletion():
    before = "# H\n\nalpha\n\nDEL-tok\n\nbeta\n"
    after = "# H\n\nalpha\n\nbeta\n"
    deleted = only_deletion(before, after, "DEL-tok")
    assert any("DEL-tok" in ln for ln in deleted)
    assert all((not ln.strip()) or ("DEL-tok" in ln) for ln in deleted)


def test_only_deletion_rejects_a_concurrent_replacement():
    before = "# H\n\nalpha\n\nDEL-tok\n\nbeta\n"
    after = "# H\n\nalphaX\n\nbeta\n"  # 'alpha' mutated too
    with pytest.raises(AssertionError):
        only_deletion(before, after, "DEL-tok")


def test_only_deletion_rejects_target_surviving():
    before = "# H\n\nDEL-tok\n\nbeta\n"
    after = "# H\n\nDEL-tok\n"  # target still present after
    with pytest.raises(AssertionError):
        only_deletion(before, after, "DEL-tok")


def test_only_deletion_rejects_no_change():
    before = "# H\n\nalpha\n"
    with pytest.raises(AssertionError):
        only_deletion(before, before, "DEL-tok")


# --------------------------------------------------------------------------- #
# only_single_line_edit — the whole-doc diff is EXACTLY one line's span, and    #
# swapping the new token back reproduces the old line byte-for-byte (so ALL     #
# surrounding style markup is byte-identical — the sub-span preservation proof) #
# --------------------------------------------------------------------------- #

def test_only_single_line_edit_accepts_a_span_swap_preserving_markup():
    before = "# H\n\n**bold** left OLD-tok right *ital*\n\ntail\n"
    after = "# H\n\n**bold** left NEW-tok right *ital*\n\ntail\n"
    b_line, a_line = only_single_line_edit(before, after, "OLD-tok", "NEW-tok")
    # the surrounding bold/italic markup survives byte-identically on both sides.
    assert "**bold**" in b_line and "**bold**" in a_line
    assert "*ital*" in b_line and "*ital*" in a_line


def test_only_single_line_edit_rejects_dropped_surrounding_style():
    # A whole-paragraph replace (styles dropped) is NOT a surgical sub-span edit:
    # swapping NEW->OLD would not reproduce the styled before-line.
    before = "# H\n\n**bold** left OLD-tok right *ital*\n\ntail\n"
    after = "# H\n\nbold left NEW-tok right ital\n\ntail\n"  # ** and * gone
    with pytest.raises(AssertionError):
        only_single_line_edit(before, after, "OLD-tok", "NEW-tok")


def test_only_single_line_edit_rejects_a_second_changed_line():
    before = "# H\n\n**bold** OLD-tok\n\nkeep\n"
    after = "# H\n\n**bold** NEW-tok\n\nCHANGED\n"  # 'keep'->'CHANGED' too
    with pytest.raises(AssertionError):
        only_single_line_edit(before, after, "OLD-tok", "NEW-tok")


def test_only_single_line_edit_rejects_line_count_change():
    # A sub-span edit must NOT change the block/line count — that would be an
    # insert/delete, not a within-paragraph edit.
    before = "# H\n\n**bold** OLD-tok\n"
    after = "# H\n\n**bold** NEW-tok\n\nEXTRA\n"
    with pytest.raises(AssertionError):
        only_single_line_edit(before, after, "OLD-tok", "NEW-tok")


# =========================================================================== #
# PART 2 — source-inspection guards over the credential-gated gate file        #
# =========================================================================== #

# --------------------------------------------------------------------------- #
# AC1 — same marker, deselected by default, skips LOUDLY without write creds    #
# --------------------------------------------------------------------------- #

def test_w3_gate_file_exists():
    assert GATE_SRC.exists(), (
        "the W3-gate live round-trip test file "
        f"{GATE_SRC.name} must exist (LD-078 AC1/AC2)."
    )


def test_w3_gate_marked_live_write():
    src = _src()
    assert "pytest.mark.live_write" in src, (
        "the W3-gate round-trip must carry the `live_write` marker so it stays "
        "deselected by the default addopts and joins the same ring as W0/W1/W2 (AC1)."
    )


def test_w3_gate_skips_loudly_when_write_creds_unset():
    src = _src()
    assert "live_write_missing_reason" in src, (
        "the W3-gate must gate on canary_support.live_write_missing_reason() so it "
        "skips loudly when LARK_WRITE_APP_* is unset (AC1)."
    )
    assert "pytest.skip" in src, (
        "the W3-gate must pytest.skip(...) with the missing-creds reason, never run "
        "silently past absent creds (AC1)."
    )


# --------------------------------------------------------------------------- #
# AC2 — insert a paragraph after an anchored reference; full-doc diff proves     #
#       ONLY the inserted paragraph appeared                                     #
# --------------------------------------------------------------------------- #

def test_w3_gate_self_provisions_its_own_doc():
    src = _src()
    assert "create_document" in src, (
        "the gate must self-provision its target doc via create_document — the W0 "
        "create->teardown mechanism, the hermetic default arm of AC5."
    )


def test_w3_gate_builds_an_insert_request():
    src = _src()
    assert "InsertRequest" in src and "InsertPosition" in src and "NewParagraph" in src, (
        "the gate must express the insert as an InsertRequest(reference=Anchor(...), "
        "position=InsertPosition..., content=(NewParagraph(...),)) — the W3 block-insert "
        "vocabulary (AC2)."
    )


def test_w3_gate_runs_dry_run_then_apply():
    src = _src()
    assert "dry_run(" in src, (
        "the gate must produce a dry-run Plan via write.preview.dry_run (S3) — the "
        "only input the apply engine accepts (AC2)."
    )
    assert "apply(" in src, (
        "the gate must execute the plan via write.apply.apply (S4) — the real apply "
        "engine, not a hand-rolled create_children/batch_delete (AC2)."
    )


def test_w3_gate_resolves_against_the_parsed_tree():
    src = _src()
    assert "parse_docx_tree" in src, (
        "the gate must obtain the reader's parsed node tree via "
        "Parser.parse_docx_tree so resolve/dry_run can address the anchor (AC2)."
    )


def test_w3_gate_insert_asserts_only_inserted_paragraph_appeared():
    src = _src()
    assert "only_insertion(" in src, (
        "the gate must assert the INSERT step with the whole-doc only_insertion diff "
        "(ONLY the inserted paragraph appeared; every other block byte-identical) — the "
        "surgical heart of AC2."
    )
    assert 'outcome == "inserted"' in src or "'inserted'" in src, (
        "the gate must assert the apply-log records an `inserted` outcome with the "
        "created block id(s) (AC2)."
    )


# --------------------------------------------------------------------------- #
# AC3 — delete an anchored block; full-doc diff proves ONLY it disappeared;      #
#       the apply-log entry carries the full removed payload (elements + style)  #
# --------------------------------------------------------------------------- #

def test_w3_gate_builds_a_delete_request():
    src = _src()
    assert "DeleteRequest" in src, (
        "the gate must express the delete as a DeleteRequest(target=Anchor(...)) — the "
        "W3 block-delete vocabulary (AC3)."
    )


def test_w3_gate_delete_asserts_only_block_disappeared():
    src = _src()
    assert "only_deletion(" in src, (
        "the gate must assert the DELETE step with the whole-doc only_deletion diff "
        "(ONLY the target block disappeared; every other block byte-identical) — AC3."
    )


def test_w3_gate_delete_asserts_removed_payload_carries_elements_and_style():
    src = _src()
    assert "removed_payload" in src, (
        "the gate must assert the delete apply-log entry carries the removed payload "
        "(the non-negotiable destructive-safe record) — AC3."
    )
    assert '"elements"' in src or "'elements'" in src, (
        "the removed-payload assertion must check the captured `elements` — the block's "
        "runs (AC3)."
    )
    assert '"style"' in src or "'style'" in src, (
        "the removed-payload assertion must check the captured block-level `style` (AC3)."
    )
    assert 'outcome == "deleted"' in src or "'deleted'" in src, (
        "the gate must assert the apply-log records a `deleted` outcome (AC3)."
    )


# --------------------------------------------------------------------------- #
# AC4 — one sub-span edit; surrounding run styles preserved, only the span       #
#       changed (S4 LANDED — LD-077 in qa_complete/ — so this step is included)  #
# --------------------------------------------------------------------------- #

def test_w3_gate_builds_a_subspan_request():
    src = _src()
    assert "SubSpanEditRequest" in src, (
        "S4 (LD-077) LANDED, so the W3 gate MUST include a sub-span edit expressed as a "
        "SubSpanEditRequest(anchor=Anchor(...), span=..., replacement=...) (AC4)."
    )


def test_w3_gate_subspan_asserts_only_the_span_changed_and_styles_preserved():
    src = _src()
    assert "only_single_line_edit(" in src, (
        "the gate must assert the SUB-SPAN step with the whole-doc only_single_line_edit "
        "diff (ONLY the span's line changed; swapping the token back reproduces the "
        "styled before-line byte-for-byte) — AC4."
    )
    # The sub-span baseline must be authored with mixed runs so preservation is visible.
    assert "bold" in src and "italic" in src, (
        "the sub-span baseline paragraph must carry surrounding bold/italic runs so the "
        "gate can prove those styles survive the span edit (AC4)."
    )


# --------------------------------------------------------------------------- #
# AC5 — writes ONLY against a doc the gate creates itself; write creds only;      #
#       reader half prefers read creds; teardown in a finally on success+failure #
# --------------------------------------------------------------------------- #

def test_w3_gate_never_references_canary_zoo_sandbox_or_external_docs():
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
        # never the standing maintainer sandbox — this gate takes AC5's hermetic self-created
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
            f"the W3 gate must not reference {token!r} — it writes only against the "
            "doc it creates itself; never the canary, the zoo, the sandbox, or a "
            "real document (AC5)."
        )


def test_w3_gate_uses_write_credentials_for_writes():
    src = _src()
    assert "get_write_credentials" in src, (
        "the gate must build its WriteClient from get_write_credentials() — the "
        "write-only resolver that never borrows read/legacy creds (AC5)."
    )


def test_w3_gate_reader_half_prefers_read_credentials():
    src = _src()
    assert "get_read_credentials" in src, (
        "the reader half must prefer get_read_credentials() for the download — the "
        "two-app least-privilege separation the gate proves (AC5)."
    )


def test_w3_gate_tears_down_in_a_finally():
    src = _src()
    assert "finally" in src, (
        "the gate must tear down in a `finally` so a mid-round-trip failure still "
        "leaves nothing behind (AC5 — restores on success AND failure)."
    )
    assert "batch_delete" in src and "delete_document" in src, (
        "teardown must empty the doc's children (batch_delete) and best-effort trash "
        "the doc (delete_document) — no orphaned self-created doc (AC5)."
    )
    assert "emptied" in src, (
        "the gate must assert the restore actually emptied the target content — the "
        "byte-identical teardown is a binding part of the gate (AC5/AC6)."
    )


# --------------------------------------------------------------------------- #
# AC6 — the FULL-DOC diff (not a region diff) is the binding W3 difference       #
# --------------------------------------------------------------------------- #

def test_w3_gate_uses_a_whole_doc_diff_not_a_region_diff():
    src = _src()
    # W1/W2 asserted `len(changed) == 1` on same-length line lists (a region diff).
    # W3 changes the block COUNT (insert/delete), so it must diff the WHOLE document
    # via difflib opcodes — the binding difference this story exists to prove.
    assert "difflib" in src, (
        "the W3 gate must use a whole-document diff (difflib opcodes) — a same-length "
        "region diff cannot express an insert/delete where the block count changes "
        "(AC2/AC3, the binding difference from W1/W2)."
    )


# --------------------------------------------------------------------------- #
# LD-453 — the same-parent multi-insert BATCH arm's shape                       #
# --------------------------------------------------------------------------- #

def test_w3_gate_carries_the_ld453_same_parent_multi_insert_arm():
    src = _src()
    assert "ld453_same_parent_multi_insert_batch" in src, (
        "the W3 gate must carry LD-453's arm — the same-parent multi-insert batch is the "
        "one shape whose misplacement no offline double could see before LD-453 (AC3).")
    assert "AnchorById" in src, (
        "the LD-453 arm anchors the three inserts by the live ids of the seeded "
        "paragraphs, as the measured repro did.")


def test_the_ld453_arm_applies_ALL_THREE_INSERTS_IN_ONE_BATCH():
    src = _src()
    arm = src.split("ld453_same_parent_multi_insert_batch", 1)[1]
    # one dry_run, one apply — the defect only exists when the entries share a batch.
    assert arm.count("dry_run(") == 1 and arm.count("apply(plan, wc, doc_id)") == 1, (
        "the LD-453 arm must plan and apply the three inserts as ONE batch — applying "
        "them one at a time is the CONTROL, which was always green and proves nothing.")


def test_the_ld453_arm_reads_the_document_back_and_verifies_structure():
    src = _src()
    arm = src.split("ld453_same_parent_multi_insert_batch", 1)[1]
    assert "expected_ids" in arm and "live_ids" in arm, (
        "the arm must read the LIVE child order back and compare it position by position — "
        "an apply-log full of `inserted` entries is exactly what the defect produced (AC3).")
    assert "expected_text_order" in arm, (
        "the arm must also verify the marker TEXT at each position through the shipped "
        "reader, not only the ids (AC3).")


def test_the_ld453_arm_tears_its_own_disposable_doc_down():
    src = _src()
    arm = src.split("ld453_same_parent_multi_insert_batch", 1)[1]
    assert "create_document" in arm and "finally" in arm and "delete_document" in arm, (
        "the LD-453 arm must self-provision its own disposable doc and tear it down in a "
        "`finally` — it never touches the ring's doc, the canary, the zoo or a real one.")
