"""Offline half of **THE AUTHORING GATE** — the authoring round-trip + the live concurrency
arm (LD-140).

NOT marked ``live_write``: everything here runs in the default ``pytest -q`` with no creds
and no network. It is the automatable part of AC1–AC3b, and it is deliberately *more* than
the shape guards its predecessors ship (``test_live_write_anchor_by_id_gate_offline.py`` et
al.), in three layers:

**(A) The differ and the equivalence are proven against FIXTURES first.** The gate's two
load-bearing measurements — "the authored region reads back as the same Markdown" and "the
full-document diff shows only additions" — are functions in ``tests/authoring_gate.py``, and
they are unit-tested here against hand-written inputs (including inputs that must make them
FAIL). A gate whose comparison function silently returns "equal" for everything proves
nothing, so the comparison is tested before it is trusted.

**(B) The WHOLE RING runs offline** against the shared fake-Lark document doubles
(``guide_recipes.OfflineWriteClient`` / ``OfflineDocxReadClient``: a real per-document block
store with Lark's own table-cell auto-provisioning and its one-bump-per-write ``revision_id``).
The live gate and this test call the **same** :func:`authoring_gate.run_authoring_ring` — so
the ring's logic, its assertions and its evidence are exercised on every ``pytest -q``, and
the credential-gated run adds the one thing a double cannot supply: **real Lark**.

**(C) The gate's discipline is pinned** over the live module's source — same marker, skips
loudly, self-provisions its own doc, never names the canary / zoo / scratch doc, tears down in
a ``finally``.
"""
from pathlib import Path

import pytest

import authoring_gate as ag

from larkdocio.write import compose
from larkdocio.write.model import NewBlockKind


# =========================================================================== #
# (A1) The fragment — every creatable kind + escaped metachars, CANONICAL.      #
# =========================================================================== #

def test_the_fragment_exercises_every_creatable_kind():
    """AC2 / the amplifier: the fragment deliberately includes **every** creatable kind
    (projected off the CLOSED ``NewBlockKind`` enum, so a kind added to the engine without
    joining the gate reddens here) — heading, paragraph, bullet, ordered, todo, code, quote
    and table, with the list kinds NESTED."""
    seen = set()

    def walk(blocks):
        for block in blocks:
            seen.add(block.kind)
            walk(block.children)

    walk(compose(ag.FRAGMENT))
    assert seen == set(NewBlockKind), (
        f"the gate's fragment must cover every creatable kind; missing: "
        f"{sorted(k.value for k in set(NewBlockKind) - seen)}")


def test_the_fragment_nests_a_list_under_a_list():
    """AC2 names a **nested** list: nesting is the one structural property a flat fragment
    would silently drop, and it is what makes the create a multi-level (multi-call) one."""
    nested = [b for b in compose(ag.FRAGMENT) if b.children]
    assert len(nested) >= 2, "the fragment must carry nested list items (bullet AND todo)"
    assert {b.kind for b in nested} == {NewBlockKind.BULLET, NewBlockKind.TODO}


def test_the_fragment_carries_escaped_metachars_that_are_literal_text():
    """The amplifier's escaped-metachar paragraph: a leading ``\\#`` and an inline
    ``\\*\\*`` must compose to **literal text** (LD-130's escaping rules read in reverse),
    so the round-trip proves escaping survives authoring rather than being re-parsed as a
    heading or as bold."""
    texts = [b.text for b in compose(ag.FRAGMENT) if b.kind is NewBlockKind.PARAGRAPH]
    assert any(t.startswith("# ") for t in texts), (
        r"a paragraph whose text literally starts with '# ' must be authored — that is the "
        r"escaped '\#' case")
    assert any("**" in t for t in texts), (
        r"a paragraph carrying literal '**' must be authored — the escaped '\*\*' case")
    # …and a table cell carries an escaped pipe as literal text.
    table = [b for b in compose(ag.FRAGMENT) if b.kind is NewBlockKind.TABLE][0]
    assert any("|" in cell for row in table.rows for cell in row), (
        r"a table cell must carry a literal '|' (the escaped '\|' case)")


def test_the_fragment_is_canonical_so_the_round_trip_is_byte_identical():
    """AC2 at its strongest: the fragment is written in the reader's **own** dialect (tier A
    of the LD-136 property), so the Markdown the reader emits for the composed content is
    the fragment **byte-identically** — no normalization to hand-wave over. That is what
    lets the live gate assert equality against the fragment itself."""
    assert ag.expected_region() == ag.FRAGMENT


def test_the_expected_region_is_the_ld_136_property_not_a_hand_written_string():
    """The prediction the live gate compares against is computed by the **shipped** encoder
    + parser + renderer (``tests/compose_roundtrip.py``, the LD-136 doc-double), never
    hand-copied: a reader change that altered the emission must redden the gate, not be
    absorbed by a stale literal."""
    from compose_roundtrip import reader_markdown

    assert ag.expected_region() == reader_markdown(compose(ag.FRAGMENT))


# =========================================================================== #
# (A2) The region extractor — proven on fixtures, including the failing cases. #
# =========================================================================== #

_DOC_BEFORE = f"# Title\n\n{ag.ANCHOR_LINE}\n\n"
_DOC_AFTER = f"# Title\n\n{ag.ANCHOR_LINE}\n\n## Section\n\nbody\n"


def test_authored_region_is_what_follows_the_anchor_line():
    assert ag.authored_region(_DOC_AFTER) == "## Section\n\nbody\n"


def test_authored_region_is_empty_before_anything_is_authored():
    """The baseline document's region is empty — so "the region equals the fragment" cannot
    pass vacuously on a document nothing was written to."""
    assert ag.authored_region(_DOC_BEFORE) == ""
    assert ag.authored_region(_DOC_BEFORE) != ag.expected_region()


def test_authored_region_normalizes_only_the_document_wrapper():
    """Leading/trailing blank lines belong to the **document** (the page's child separator),
    not to the authored fragment, so they are normalized away — and **interior** blank lines
    are left exactly as the renderer emitted them, because they are part of the dialect (a
    table's own trailing blank line is why the fragment carries two)."""
    assert ag.authored_region(f"{ag.ANCHOR_LINE}\n\n\n\nx\n\n\n") == "x\n"
    assert ag.authored_region(f"{ag.ANCHOR_LINE}\n\na\n\n\nb\n") == "a\n\n\nb\n"


def test_authored_region_refuses_an_ambiguous_or_absent_anchor():
    """The extractor is only meaningful if the anchor line is UNIQUE: two matches (or none)
    would silently slice the wrong region, so it raises instead."""
    with pytest.raises(AssertionError):
        ag.authored_region("nothing here\n")
    with pytest.raises(AssertionError):
        ag.authored_region(f"{ag.ANCHOR_LINE}\n{ag.ANCHOR_LINE}\n")


# =========================================================================== #
# (A3) The full-document differ — proven to SEE both directions.                #
# =========================================================================== #

def test_the_full_document_diff_reports_added_lines():
    added, removed = ag.full_document_diff(_DOC_BEFORE, _DOC_AFTER)
    assert removed == []
    assert "## Section" in added and "body" in added


def test_the_full_document_diff_reports_removed_lines():
    """The direction that matters for AC3: a write that LOST a line must be visible. A
    differ that only ever reports additions would pass a destructive bug."""
    added, removed = ag.full_document_diff(_DOC_AFTER, _DOC_BEFORE)
    assert "## Section" in removed and "body" in removed
    assert added == []


def test_the_full_document_diff_is_silent_on_an_unchanged_document():
    added, removed = ag.full_document_diff(_DOC_AFTER, _DOC_AFTER)
    assert (added, removed) == ([], [])


def test_the_full_document_diff_sees_a_changed_line_as_both_removed_and_added():
    """A modified line is a removal AND an addition — so "nothing was removed" really does
    mean "nothing outside the authored region changed", which is what AC3 asserts."""
    added, removed = ag.full_document_diff("a\nb\n", "a\nB\n")
    assert removed == ["b"] and added == ["B"]


# =========================================================================== #
# (B) THE WHOLE RING, offline — the same function the live gate runs, bound to  #
#     the shared fake-Lark document doubles.                                    #
# =========================================================================== #

_DOC = "doccnExample00001"


@pytest.fixture
def offline_backend(monkeypatch):
    """A fake-Lark backend for the ring: one shared per-test document store, an **empty**
    self-provisioned document, two independent write clients, and a ``download`` that runs
    the **shipped** parser over the double's block payloads.

    The doubles are ``guide_recipes``' — a real per-document block store with Lark's own
    table-cell auto-provisioning and its live-characterized one-bump-per-write ``revision_id``
    — so ``dry_run`` → ``apply`` is a genuine compare-and-swap here, not a decoration.
    """
    import guide_recipes as gr

    from larkdocio.read.config import new_config
    from larkdocio.read.parser import Parser
    from larkdocio.write.client import text_block

    store = gr.OfflineDocuments(empty=True)
    monkeypatch.setattr(gr.OfflineWriteClient, "documents", store, raising=False)
    monkeypatch.setattr(gr.OfflineDocxReadClient, "documents", store, raising=False)

    def download(document_id):
        read_client = gr.OfflineDocxReadClient("read-app", "read-secret", "larksuite.com")
        docx, blocks = read_client.get_docx_content(document_id)
        parser = Parser(new_config())
        return (parser.parse_docx_content(docx.document_id, blocks),
                parser.parse_docx_tree(docx.document_id, blocks),
                docx.revision_id)

    write_client = gr.OfflineWriteClient("write-app", "write-secret")
    # A genuinely SECOND client — its own instance, sharing only the document, exactly like
    # the live arm's second WriteClient (the out-of-band editor).
    other_client = gr.OfflineWriteClient("write-app", "write-secret")
    write_client.create_children(_DOC, _DOC, [text_block(ag.ANCHOR_LINE)], index=0)
    return {"write_client": write_client, "second_write_client": other_client,
            "download": download, "document_id": _DOC}


def test_the_whole_ring_runs_offline_against_the_fake_lark_doubles(offline_backend):
    """AC2/AC3/AC3b, offline: the **same** ring the live gate runs — compose → dry-run →
    apply → re-download → same Markdown → delete by id → byte-identical restore → the armed
    concurrency arm (out-of-band edit → ``STALE_DOCUMENT`` → byte-unchanged → re-plan
    proceeds). Its evidence dict is the shape the live gate prints."""
    evidence = ag.run_authoring_ring(**offline_backend)

    # the round-trip arm
    assert evidence["round_trip_equal"] is True
    assert evidence["authored_region"] == ag.FRAGMENT
    assert evidence["created_block_ids"] and evidence["removed_lines_after_insert"] == []
    # the restore
    assert evidence["restored_byte_identical"] is True
    # the concurrency arm
    assert evidence["stale_document_reason"] == "stale-document"
    assert evidence["refused_writes"] == []
    assert evidence["refused_calls"] == ["read_document_revision"]
    assert evidence["byte_unchanged_by_the_refused_batch"] is True
    assert evidence["replan_outcome"] == "inserted"
    assert evidence["replan_round_trip_equal"] is True


def test_the_ring_arms_the_document_guard_rather_than_leaving_it_unavailable(offline_backend):
    """AC3b's precondition: the plan must carry the document's ``revision_id`` — an unarmed
    plan is marked ``revision_guard: 'unavailable'`` and could never observe drift, so the
    arm would silently prove nothing (the LD-132 never-silent lesson)."""
    evidence = ag.run_authoring_ring(**offline_backend)
    assert evidence["revision_guard"] == "active"
    assert evidence["armed_revision_guard"] == "active"
    assert evidence["apply_log_revision_guard"] == "active"


def test_the_ring_proves_the_refusal_is_the_DOCUMENT_guard_not_the_anchor(offline_backend):
    """The D9 case, isolated: the out-of-band edit deliberately does **not** touch the
    anchored block, so its own ``STALE_ANCHOR`` precondition still holds at the moment of
    the refusal — the batch is refused by the **whole-document** compare-and-swap alone.
    Without this the arm could pass for the wrong reason."""
    evidence = ag.run_authoring_ring(**offline_backend)
    assert evidence["anchor_still_matched_at_refusal"] is True
    assert evidence["out_of_band_landed"] is True
    assert evidence["revision_advanced"] is True


def test_the_teardown_is_idempotent(offline_backend):
    """The amplifier's second-run assertion: teardown runs on the success **and** failure
    paths, so running it twice must be a clean no-op rather than an API error."""
    ag.run_authoring_ring(**offline_backend)
    first = ag.authoring_teardown(offline_backend["write_client"],
                                  offline_backend["download"], _DOC)
    second = ag.authoring_teardown(offline_backend["write_client"],
                                   offline_backend["download"], _DOC)
    assert first["emptied"] is True and second["emptied"] is True
    assert second["children_removed"] == 0, (
        "the second teardown must find nothing left to remove — it is a no-op")


def test_the_ring_fails_loudly_when_authored_cell_text_goes_nowhere(offline_backend):
    """The gate's own safety net, aimed at its subtlest failure mode: a table is created in
    **two steps** (Lark provisions the grid, the engine then patches each cell), so a backend
    where the cell patches go nowhere would show a table that *exists* with **empty cells** —
    structure right, content lost. The round-trip equality must catch that; if it could not,
    the gate's green would mean nothing live."""
    offline_backend["write_client"] = _LostCellText(offline_backend["write_client"])
    with pytest.raises(AssertionError, match="ROUND-TRIP FAILED"):
        ag.run_authoring_ring(**offline_backend)


class _LostCellText:
    """A client whose cell writes silently do nothing — authored cell text vanishes.

    Both routes are neutered, and deliberately: the fill has been BATCHED (LD-481), so a
    double that only swallowed ``_patch_block`` would leave the amplifier passing for the
    wrong reason — it would prove the gate catches a call the engine no longer makes.
    """

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def _patch_block(self, document_id, block_id, update):
        return {"block_id": block_id}

    def batch_update_blocks(self, document_id, requests):
        return {"blocks": []}


# =========================================================================== #
# (C) The gate's discipline — pinned over the LIVE module's source.             #
# =========================================================================== #

GATE_SRC = Path(__file__).resolve().parent / "test_live_write_authoring_gate.py"


def _src() -> str:
    return GATE_SRC.read_text(encoding="utf-8")


def test_the_gate_file_exists():
    assert GATE_SRC.exists(), (
        f"THE AUTHORING gate {GATE_SRC.name} must exist (LD-140 AC1).")


def test_the_gate_is_marked_live_write():
    assert "pytest.mark.live_write" in _src(), (
        "AC1: the authoring gate must carry the `live_write` marker so it stays deselected "
        "by the default addopts and joins the SAME ring as W0/W1/W2/W3/S2/S4 (AC4).")


def test_the_gate_skips_loudly_when_write_creds_unset():
    src = _src()
    assert "live_write_missing_reason" in src and "pytest.skip" in src, (
        "AC1: the gate must gate on canary_support.live_write_missing_reason() and "
        "pytest.skip(...) — never run silently past absent creds.")


def test_the_gate_runs_the_shared_ring_rather_than_a_second_copy_of_it():
    src = _src()
    assert "run_authoring_ring" in src, (
        "the live gate must run the SHARED ring (tests/authoring_gate.py) — the same "
        "function this file executes offline, so the two cannot drift.")
    assert "authoring_teardown" in src, (
        "…and the shared, idempotent teardown, so 'restores on both paths' is one "
        "implementation rather than two.")


def test_the_gate_self_provisions_its_own_doc_and_trashes_it():
    """AC5/AC3, split across the two halves that own them: the live module **provisions** the
    doc (``create_document``) and the shared teardown **trashes** it (``delete_document``) —
    so neither half can quietly stop doing its part."""
    assert "create_document" in _src(), (
        "AC5: the gate must self-provision its target doc via create_document — never a "
        "pre-existing document.")
    ring_src = (Path(ag.__file__)).read_text(encoding="utf-8")
    assert "delete_document" in ring_src and "batch_delete" in ring_src, (
        "AC3: the shared teardown must empty the doc's children AND best-effort trash the "
        "doc — no orphaned scratch doc, no orphaned blocks.")


def test_the_gate_tears_down_in_a_finally():
    src = _src()
    assert "finally" in src, (
        "AC3: teardown must run in a `finally` so a mid-ring failure still leaves nothing "
        "behind — restore on the success AND failure paths.")


def test_the_gate_never_references_the_canary_zoo_scratch_or_any_external_doc():
    src = _src()
    forbidden = [
        "LARKDOCIO_CANARY_DOC", "CANARY_DOC_ENV", "canary_doc_url",
        "LARKDOCIO_BLOCKZOO_DOC", "BLOCKZOO_DOC_ENV", "blockzoo_doc_url",
        "LARKDOCIO_WRITE_SCRATCH_DOC", "LARKDOCIO_SCRATCH_SHEET",
        "larksuite.com/docx/", "feishu.cn/docx/", "feishu.cn/wiki/", "larksuite.com/wiki/",
    ]
    for token in forbidden:
        assert token not in src, (
            f"AC5: the gate must not reference {token!r} — it writes only against the doc "
            "it creates itself; never the canary, the zoo, the maintainer scratch doc, or any real "
            "document.")


def test_the_gate_uses_write_credentials_for_writes_and_read_creds_for_reads():
    src = _src()
    assert "get_write_credentials" in src, (
        "AC5: writes must come from get_write_credentials() — the write-only resolver that "
        "never borrows read/legacy creds.")
    assert "get_read_credentials" in src, (
        "the reader half must prefer get_read_credentials() — the two-app least-privilege "
        "separation.")


def test_the_gate_uses_a_second_client_for_the_out_of_band_edit():
    """AC3b says the out-of-band edit comes from a **second client path**. One client
    mutating its own document is not a concurrency test — the drift has to come from
    somewhere else."""
    src = _src()
    assert src.count("WriteClient(") >= 2, (
        "AC3b: the concurrency arm needs a genuinely SECOND WriteClient — the out-of-band "
        "editor — not the same object that applies the batch.")


def test_the_gate_records_its_evidence():
    src = _src()
    assert "capsys" in src and "evidence" in src, (
        "AC3b/AC4: the gate must print its evidence (the fragment, the diff, the refusal "
        "detail, the byte-unchanged proof, the successful re-plan) so the Activity log can "
        "carry it.")
