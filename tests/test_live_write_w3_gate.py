"""THE W3 GATE — the binding create / delete / sub-span write round-trip
(LD-078).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` +
network). Run it explicitly (with the whole ring — W0 + W1 + W2 + W3)::

    pytest -m live_write

Where the W1 gate proved the apply engine on a **narrative paragraph** and the W2 gate
on a **table cell** — both *whole-block replaces* whose surgical proof is a **same-length
region diff** (exactly one Markdown line changed) — THIS gate proves the three W3
operations whose surgical proof needs a **whole-document diff**, because an insert / delete
changes the **block count**:

* **insert** a text-bearing paragraph **after an anchored reference** → a full-doc diff
  proves **ONLY the inserted paragraph appeared** (every other block byte-identical);
* **delete** an anchored block → a full-doc diff proves **ONLY that block disappeared**,
  **and** the apply-log entry carries the **full removed-block payload** (elements + style)
  — the non-negotiable destructive-safe record;
* **sub-span** edit a quoted span **within** a paragraph (S4 / LD-077 landed) → a full-doc
  diff proves **ONLY the span's line changed** and the **surrounding run styles are
  preserved** (swapping the token back reproduces the styled before-line byte-for-byte;
  the neighbouring bold / italic runs survive at the element level).

All three ride the **real S1–S4 pipeline** — ``InsertRequest`` / ``DeleteRequest`` /
``SubSpanEditRequest`` (S1) → ``dry_run`` Plan (S3) → ``apply`` (S4) — against a doc the
gate **creates and destroys itself** (never the read canary, never the block-zoo doc,
never the standing sandbox, never a real document — AC5). **All live_write gate families
(W0..W3) must pass together** in one ``pytest -m live_write`` run.

**Credentials (AC5).** Writes use ``get_write_credentials()`` only (write-only, never
read/legacy). The **reader half prefers ``get_read_credentials()``** — the two-app
least-privilege separation — and falls back to the owning write app's creds for a
self-provisioned doc a separate read-only app cannot see (the fallback is about *reads*;
the write path never borrows read creds). Teardown runs in a ``finally`` so a
mid-round-trip failure still leaves nothing behind — and it reads the doc's **live** child
count (the W3 ops change it), then empties that whole range. Writes ride the shared core's
throttle (≤3/sec, ``99991400`` backoff).
"""
import difflib
import time

import pytest

import canary_support
from larkdocio.common import get_read_credentials, get_write_credentials
from larkdocio.errors import LarkDocIOError
from larkdocio.read.client import Client as ReadClient
from larkdocio.read.config import new_config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    AnchorById,
    DeleteRequest,
    InsertPosition,
    InsertRequest,
    NewParagraph,
    SubSpanEditRequest,
    apply,
    dry_run,
)
from larkdocio.write.client import WriteClient, text_block

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region (matches the toolkit's default OpenAPI domain).
# NOT a document URL — the gate never addresses a pre-existing doc.
DOMAIN = "larksuite.com"

# Distinctive, unique tokens the gate itself authors — so each anchor quote is a unique
# locator and every full-doc diff is exact and unambiguous. The suffix makes every token
# greppable and collision-free within the self-created doc.
SUFFIX = "w3gate-4c8e1a72"
SECTION_HEADING = f"W3-GATE-SECTION {SUFFIX}"
REF_TOKEN = f"insert-reference :: REF-{SUFFIX}"        # the insert anchor (survives)
DELME_TOKEN = f"delete-me :: DELME-{SUFFIX}"           # the delete target
GUARD_TOKEN = f"guard tail :: GUARD-{SUFFIX}"          # must stay byte-identical throughout
INSERTED_TOKEN = f"INSERTED-{SUFFIX}"                  # the created paragraph's unique mark
INSERTED_PARA = f"the apply engine inserted this whole paragraph :: {INSERTED_TOKEN}"

# The sub-span baseline paragraph — THREE runs so surrounding-style preservation is visible
# in the rendered Markdown: a BOLD prefix run, a PLAIN middle run carrying the editable
# span, and an ITALIC suffix run. The span is a substring *inside* the plain run, so the
# engine must split that run at the span boundaries and keep the bold/italic neighbours.
BOLD_KEEP = f"boldkeep-{SUFFIX}"
ITALIC_KEEP = f"italkeep-{SUFFIX}"
SPAN_BEFORE = f"EDITME-{SUFFIX}"
SPAN_AFTER = f"SPANDONE-{SUFFIX}"
SUBSPAN_MIDDLE = f" left {SPAN_BEFORE} right "

# ---- LD-453's arm: the same-parent multi-insert BATCH (its own doc, below) ---- #
# The measured repro's own body, quoted from the triage capture's `repro` block
# (dev/dogfood4-triage/captures/batch-insert-drift.json), suffixed so every line is a
# unique, greppable locator inside this gate's self-created doc.
DRIFT = f"drift-{SUFFIX}"
DRIFT_SEED = [
    f"Section One :: {DRIFT}",
    f"Alpha body paragraph. :: {DRIFT}",
    f"Section Two :: {DRIFT}",
    f"Beta body paragraph. :: {DRIFT}",
    f"Section Three :: {DRIFT}",
    f"Gamma body paragraph. :: {DRIFT}",
]
# marker text keyed by the 0-based index of the seed paragraph it must land AFTER.
DRIFT_MARKERS = {
    1: f"MARKER-1 belongs after Alpha. :: {DRIFT}",
    3: f"MARKER-2 belongs after Beta. :: {DRIFT}",
    5: f"MARKER-3 belongs after Gamma. :: {DRIFT}",
}


# =========================================================================== #
# Full-doc diff helpers — the surgical-ness proofs (the binding W3 difference)  #
# Pure, offline, unit-tested in tests/test_live_write_w3_gate_offline.py.       #
# =========================================================================== #

def _nonequal_opcodes(before_md: str, after_md: str):
    """The non-``equal`` opcodes of a WHOLE-DOCUMENT line diff, plus the line lists.

    Unlike W1/W2's same-length region diff (``len(changed) == 1`` over equal-length line
    lists), an insert/delete changes the block count, so the surgical proof must diff the
    entire document. ``autojunk=False`` keeps common blank lines from being treated as
    junk (which would distort the opcode partition)."""
    b = before_md.splitlines()
    a = after_md.splitlines()
    opcodes = difflib.SequenceMatcher(a=b, b=a, autojunk=False).get_opcodes()
    nonequal = [op for op in opcodes if op[0] != "equal"]
    return b, a, nonequal


def only_insertion(before_md: str, after_md: str, token: str):
    """Assert the whole-doc diff is EXACTLY an insertion of new lines carrying ``token``.

    Every non-``equal`` opcode must be an ``insert`` (nothing anywhere was deleted or
    replaced), every inserted line must be blank or carry ``token`` (only the new
    paragraph appeared), ``token`` must appear exactly once after and never before.
    Because all opcodes are ``equal``/``insert``, deleting the inserted lines reproduces
    the baseline byte-for-byte — the surgical proof. Returns the inserted lines."""
    b, a, nonequal = _nonequal_opcodes(before_md, after_md)
    assert nonequal, "no change detected in the whole-doc diff (insert produced nothing)"
    assert all(op[0] == "insert" for op in nonequal), (
        f"whole-doc diff shows a non-insert change (delete/replace) — the insert was not "
        f"surgical: {nonequal}"
    )
    inserted = [ln for (_t, _i1, _i2, j1, j2) in nonequal for ln in a[j1:j2]]
    assert all((not ln.strip()) or (token in ln) for ln in inserted), (
        f"inserted lines carry content other than the sentinel paragraph: {inserted!r}"
    )
    assert token not in before_md, f"sentinel {token!r} already present before the insert"
    assert sum(token in ln for ln in a) == 1, (
        f"sentinel {token!r} must appear exactly once after the insert"
    )
    return inserted


def only_deletion(before_md: str, after_md: str, token: str):
    """Assert the whole-doc diff is EXACTLY a deletion of lines carrying ``token``.

    Every non-``equal`` opcode must be a ``delete`` (nothing anywhere was inserted or
    replaced), every deleted line must be blank or carry ``token`` (only the target block
    disappeared), and ``token`` must be gone from the after-doc. Returns the deleted
    lines."""
    b, a, nonequal = _nonequal_opcodes(before_md, after_md)
    assert nonequal, "no change detected in the whole-doc diff (delete produced nothing)"
    assert all(op[0] == "delete" for op in nonequal), (
        f"whole-doc diff shows a non-delete change (insert/replace) — the delete was not "
        f"surgical: {nonequal}"
    )
    deleted = [ln for (_t, i1, i2, _j1, _j2) in nonequal for ln in b[i1:i2]]
    assert all((not ln.strip()) or (token in ln) for ln in deleted), (
        f"deleted lines carry content other than the target block: {deleted!r}"
    )
    assert sum(token in ln for ln in b) == 1, (
        f"target {token!r} must appear exactly once before the delete"
    )
    assert token not in after_md, f"target {token!r} survived the delete"
    return deleted


def only_single_line_edit(before_md: str, after_md: str, old_token: str, new_token: str):
    """Assert the whole-doc diff is EXACTLY one line's span swap, styles preserved.

    A sub-span edit stays within one paragraph, so the block/line count is unchanged and
    the whole-doc diff must be a single ``replace`` of one line by one line. ``old_token``
    is in the before-line, ``new_token`` in the after-line, and — the airtight
    style-preservation proof — swapping ``new_token`` back to ``old_token`` in the
    after-line reproduces the before-line **byte-for-byte**, so ALL surrounding style
    markup (bold ``**`` / italic ``*`` / …) is identical. Returns ``(before_line,
    after_line)``."""
    b, a, nonequal = _nonequal_opcodes(before_md, after_md)
    assert len(nonequal) == 1 and nonequal[0][0] == "replace", (
        f"a sub-span edit must be exactly one replaced line (block count unchanged); "
        f"whole-doc diff was: {nonequal}"
    )
    _t, i1, i2, j1, j2 = nonequal[0]
    assert (i2 - i1) == 1 and (j2 - j1) == 1, (
        f"the sub-span edit changed more than one line (before {i2 - i1}, after {j2 - j1})"
    )
    before_line, after_line = b[i1], a[j1]
    assert old_token in before_line, f"the changed line is not the span target: {before_line!r}"
    assert new_token in after_line, f"the changed line lost the replacement: {after_line!r}"
    assert new_token not in before_md and old_token not in after_md
    assert after_line.replace(new_token, old_token) == before_line, (
        "the sub-span edit changed more than the span — surrounding style markup differs "
        f"(before {before_line!r} vs swap-back {after_line.replace(new_token, old_token)!r})"
    )
    return before_line, after_line


# =========================================================================== #
# Reader half — download + parse via the READER (the same modules the CLI uses) #
# =========================================================================== #

def _download(document_id):
    """Download + parse the doc via the READER. Returns ``(markdown, tree)``.

    AC5: the reader half **prefers read creds**. For a doc this gate self-provisioned with
    the *write* app, a separate read-only app is not a collaborator, so a read-cred
    download can 403 / not-find; we then fall back to the owning write app's creds. The
    fallback is a READ concern only — the write path never borrows read creds."""
    attempts = []
    if canary_support.read_creds_available():
        attempts.append(("read", get_read_credentials()))
    attempts.append(("write", get_write_credentials()))

    last_err = None
    for _label, (app_id, app_secret) in attempts:
        try:
            client = ReadClient(app_id, app_secret, DOMAIN)
            docx, blocks = client.get_docx_content(document_id)
            parser = Parser(new_config())
            markdown = parser.parse_docx_content(docx.document_id, blocks)
            tree = parser.parse_docx_tree(docx.document_id, blocks)
            return markdown, tree
        except (LarkDocIOError, Exception) as e:  # noqa: BLE001 — try the next identity
            last_err = e
    raise last_err


def _iter_runs(block: dict):
    """Yield each ``text_run`` (content, style) of a live read block dict."""
    for value in block.values():
        if isinstance(value, dict) and isinstance(value.get("elements"), list):
            for element in value["elements"]:
                run = element.get("text_run")
                if run is not None:
                    yield run.get("content", ""), (run.get("text_element_style") or {})


# =========================================================================== #
# THE W3 GATE — one self-created doc, three surgical steps, then teardown       #
# =========================================================================== #

def test_w3_gate_create_delete_subspan_round_trip(capsys):
    # Load the repo .env (local runs) — a no-op in CI where creds are injected as
    # variables. Then skip LOUDLY if we cannot run.
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    wc = WriteClient(*get_write_credentials(), DOMAIN)

    # 1) Create the gate's OWN disposable doc.
    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-W3-gate {int(time.time())}",
                             folder_token=dest_folder)
    doc_id = doc["document_id"]

    evidence = {"doc_id": doc_id}
    # Top-level children, all authored by the gate so every diff is exact:
    #   [0] heading (real breadcrumb for every anchor)
    #   [1] the insert REFERENCE paragraph (survives; the insert lands after it)
    #   [2] the DELETE target paragraph
    #   [3] the SUB-SPAN paragraph — bold prefix + plain middle (the span) + italic suffix
    #   [4] a GUARD paragraph that must stay byte-identical through all three steps
    baseline_children = [
        {"block_type": 3, "heading1": {"elements": [{"text_run": {"content": SECTION_HEADING}}]}},
        text_block(REF_TOKEN),
        text_block(DELME_TOKEN),
        {
            "block_type": 2,
            "text": {
                "elements": [
                    {"text_run": {"content": BOLD_KEEP, "text_element_style": {"bold": True}}},
                    {"text_run": {"content": SUBSPAN_MIDDLE}},
                    {"text_run": {"content": ITALIC_KEEP, "text_element_style": {"italic": True}}},
                ]
            },
        },
        text_block(GUARD_TOKEN),
    ]

    try:
        # 2) Populate the baseline, then the determinism control: two clean downloads must
        #    be byte-identical (so any post-edit diff is attributable to the edit alone).
        wc.create_children(doc_id, doc_id, baseline_children, index=0)

        md0, tree0 = _download(doc_id)
        md0_again, _ = _download(doc_id)
        assert md0 == md0_again, (
            "reader is non-deterministic: two downloads of the unchanged doc differ"
        )
        for tok in (REF_TOKEN, DELME_TOKEN, GUARD_TOKEN, SPAN_BEFORE, BOLD_KEEP, ITALIC_KEEP):
            assert tok in md0, f"baseline token missing from download: {tok!r}"
        assert INSERTED_TOKEN not in md0 and SPAN_AFTER not in md0

        # --------------------------------------------------------------------- #
        # STEP A — INSERT a paragraph AFTER the anchored reference (AC2).         #
        #   full-doc diff proves ONLY the inserted paragraph appeared.            #
        # --------------------------------------------------------------------- #
        ins = InsertRequest(
            reference=Anchor(quote=REF_TOKEN, breadcrumb=(SECTION_HEADING,)),
            position=InsertPosition.AFTER,
            content=(NewParagraph(text=INSERTED_PARA),),
        )
        plan_ins = dry_run([ins], tree0)
        assert len(plan_ins.resolved) == 1 and len(plan_ins.refusals) == 0, (
            f"insert dry-run did not resolve cleanly: {plan_ins!r} {plan_ins.refusals!r}"
        )
        assert plan_ins.resolved[0].is_insert, "resolved insert entry lost its insert op"
        log_ins = apply(plan_ins, wc, doc_id)
        assert len(log_ins.entries) == 1
        ins_entry = log_ins.entries[0]
        assert ins_entry.outcome == "inserted", f"insert not applied: {ins_entry.to_dict()!r}"
        assert ins_entry.created_block_ids and all(ins_entry.created_block_ids), (
            f"insert apply-log carries no created block id(s): {ins_entry.to_dict()!r}"
        )

        md1, tree1 = _download(doc_id)
        inserted_lines = only_insertion(md0, md1, INSERTED_TOKEN)
        # Everything else is still present and unchanged (the diff already proved it, but
        # assert the survivors explicitly for the Activity-log evidence).
        for tok in (REF_TOKEN, DELME_TOKEN, GUARD_TOKEN, SPAN_BEFORE, BOLD_KEEP, ITALIC_KEEP):
            assert tok in md1, f"insert disturbed an unrelated block (lost {tok!r})"
        evidence["inserted_block_ids"] = list(ins_entry.created_block_ids)
        evidence["inserted_lines"] = inserted_lines

        # --------------------------------------------------------------------- #
        # STEP B — DELETE the anchored target block (AC3).                        #
        #   full-doc diff proves ONLY it disappeared; the apply-log entry carries  #
        #   the FULL removed payload (elements + style).                          #
        # --------------------------------------------------------------------- #
        dele = DeleteRequest(target=Anchor(quote=DELME_TOKEN, breadcrumb=(SECTION_HEADING,)))
        plan_del = dry_run([dele], tree1)
        assert len(plan_del.resolved) == 1 and len(plan_del.refusals) == 0, (
            f"delete dry-run did not resolve cleanly: {plan_del!r} {plan_del.refusals!r}"
        )
        assert plan_del.resolved[0].is_delete, "resolved delete entry lost its delete op"
        log_del = apply(plan_del, wc, doc_id)
        assert len(log_del.entries) == 1
        del_entry = log_del.entries[0]
        assert del_entry.outcome == "deleted", f"delete not applied: {del_entry.to_dict()!r}"
        # The destructive-safe record: the removed payload must carry the block's elements
        # (its runs) AND its block-level style key — a lossless snapshot.
        payload = del_entry.removed_payload
        assert isinstance(payload, dict), f"removed_payload is not a dict: {payload!r}"
        assert "elements" in payload and "style" in payload, (
            f"removed_payload must carry both 'elements' and 'style': {payload!r}"
        )
        assert payload.get("block_id") == del_entry.block_id
        payload_text = "".join(
            el.get("text_run", {}).get("content", "") for el in (payload.get("elements") or [])
        )
        assert DELME_TOKEN in payload_text, (
            f"removed payload did not capture the deleted block's text: {payload!r}"
        )

        md2, tree2 = _download(doc_id)
        deleted_lines = only_deletion(md1, md2, DELME_TOKEN)
        for tok in (REF_TOKEN, INSERTED_TOKEN, GUARD_TOKEN, SPAN_BEFORE, BOLD_KEEP, ITALIC_KEEP):
            assert tok in md2, f"delete disturbed an unrelated block (lost {tok!r})"
        evidence["deleted_block_id"] = del_entry.block_id
        evidence["removed_payload_keys"] = sorted(payload.keys())
        evidence["deleted_lines"] = deleted_lines

        # --------------------------------------------------------------------- #
        # STEP C — SUB-SPAN edit within the paragraph (AC4; S4/LD-077 landed).    #
        #   full-doc diff proves ONLY the span's line changed and the surrounding  #
        #   run styles are preserved (bold/italic neighbours survive).            #
        # --------------------------------------------------------------------- #
        sub = SubSpanEditRequest(
            anchor=Anchor(quote=BOLD_KEEP, breadcrumb=(SECTION_HEADING,)),
            span=SPAN_BEFORE,
            replacement=SPAN_AFTER,
        )
        plan_sub = dry_run([sub], tree2)
        assert len(plan_sub.resolved) == 1 and len(plan_sub.refusals) == 0, (
            f"sub-span dry-run did not resolve cleanly: {plan_sub!r} {plan_sub.refusals!r}"
        )
        assert plan_sub.resolved[0].is_subspan, "resolved sub-span entry lost its subspan op"
        log_sub = apply(plan_sub, wc, doc_id)
        assert len(log_sub.entries) == 1
        sub_entry = log_sub.entries[0]
        assert sub_entry.outcome == "applied", f"sub-span not applied: {sub_entry.to_dict()!r}"
        assert sub_entry.before == SPAN_BEFORE and sub_entry.after == SPAN_AFTER, (
            f"sub-span apply-log before/after wrong: {sub_entry.to_dict()!r}"
        )

        md3, _ = _download(doc_id)
        b_line, a_line = only_single_line_edit(md2, md3, SPAN_BEFORE, SPAN_AFTER)

        # Element-level proof the surrounding run styles survived: re-read the live block
        # and confirm the bold prefix is still bold, the italic suffix still italic, and
        # the span text was replaced (not the whole paragraph flattened to one plain run).
        live_block = wc.get_block(doc_id, sub_entry.block_id)
        runs = list(_iter_runs(live_block))
        bold_ok = any(BOLD_KEEP in c and s.get("bold") for c, s in runs)
        italic_ok = any(ITALIC_KEEP in c and s.get("italic") for c, s in runs)
        span_replaced = any(SPAN_AFTER in c for c, _s in runs)
        assert bold_ok, f"the bold prefix run lost its style after the sub-span edit: {runs!r}"
        assert italic_ok, f"the italic suffix run lost its style after the sub-span edit: {runs!r}"
        assert span_replaced, f"the span was not replaced in the live block: {runs!r}"
        for tok in (REF_TOKEN, INSERTED_TOKEN, GUARD_TOKEN):
            assert tok in md3, f"sub-span disturbed an unrelated block (lost {tok!r})"
        evidence["subspan_block_id"] = sub_entry.block_id
        evidence["subspan_before_line"] = b_line
        evidence["subspan_after_line"] = a_line
        evidence["subspan_styles_preserved"] = bool(bold_ok and italic_ok)
        evidence["all_steps_surgical"] = True

    finally:
        # 3) Teardown so NOTHING persists. The W3 ops change the top-level child COUNT, so
        #    (unlike W0/W1/W2's fixed count) read the doc's LIVE children and empty that
        #    whole range; verify gone; then best-effort trash the doc. Runs on success AND
        #    failure (no orphan / no drift).
        emptied = False
        deleted = None
        try:
            root = wc.get_block(doc_id, doc_id)
            child_ids = root.get("children") or []
            if child_ids:
                wc.batch_delete(doc_id, doc_id, 0, len(child_ids))
            md_empty, _ = _download(doc_id)
            emptied = not any(
                tok in md_empty
                for tok in (REF_TOKEN, DELME_TOKEN, GUARD_TOKEN, INSERTED_TOKEN,
                            SPAN_BEFORE, SPAN_AFTER, BOLD_KEEP, ITALIC_KEEP)
            )
        except LarkDocIOError as e:
            evidence["empty_error"] = str(e)
        try:
            resp = wc.delete_document(doc_id)
            deleted = resp.get("code") if isinstance(resp, dict) else "ok"
        except LarkDocIOError as e:
            deleted = f"skipped ({e})"
        evidence["emptied"] = emptied
        evidence["deleted"] = deleted

    # The teardown restore is a binding part of the gate: nothing persists.
    assert emptied, "teardown failed: gate content still present after restore"

    with capsys.disabled():
        print(
            "\n[live_write:W3-gate] "
            f"doc_id={evidence['doc_id']} "
            f"inserted_block_ids={evidence.get('inserted_block_ids')} "
            f"deleted_block_id={evidence.get('deleted_block_id')} "
            f"removed_payload_keys={evidence.get('removed_payload_keys')} "
            f"subspan_block_id={evidence.get('subspan_block_id')} "
            f"styles_preserved={evidence.get('subspan_styles_preserved')} "
            f"all_steps_surgical={evidence.get('all_steps_surgical')} "
            f"emptied={evidence.get('emptied')} deleted={evidence.get('deleted')}\n"
            f"  insert : {evidence.get('inserted_lines')!r}\n"
            f"  delete : {evidence.get('deleted_lines')!r}\n"
            f"  subspan before: {evidence.get('subspan_before_line')!r}\n"
            f"  subspan after : {evidence.get('subspan_after_line')!r}"
        )


# =========================================================================== #
# LD-453 — the SAME-PARENT MULTI-INSERT BATCH arm, in its own disposable doc.   #
# =========================================================================== #

def test_w3_gate_ld453_same_parent_multi_insert_batch_lands_each_beside_its_own_anchor(capsys):
    """LD-453 AC3 — three `AFTER` inserts resolving to the SAME parent, in **one** batch,
    each land immediately after **their own** anchor, proven by a live read-back.

    This is the dogfood round-4 defect that no offline double could see (triage
    `dev/dogfood4-triage/dogfood4-drift-repro.md`, capture `captures/batch-insert-drift.json`):
    the plan's insertion `index` is an ordinal of the **pre-batch** snapshot, so entry *k* used
    to write against a tree *k−1* earlier entries had already grown — MARKER-2 landed one
    position early, MARKER-3 two, into the wrong section — with `plan.refusals` empty, three
    `inserted` log entries and three real `created_block_ids`. Only a read-back showed it.

    **The gate is deliberately capable of failing on exactly this defect**: revert
    :func:`~larkdocio.write.apply._live_insertion_point` (i.e. hand `entry.insertion_point.index`
    straight to `create_children` again) and the child-order assertion below reproduces the
    pre-fix misplacement. That two-sided proof is the AC3 obligation, and its evidence is in the
    issue's Activity log.

    Its OWN disposable doc — never the read canary, the block zoo, the sandbox or a real
    document — created and torn down here, kept apart from the ring above so it cannot perturb
    that ring's line-position and diff assertions.
    """
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    wc = WriteClient(*get_write_credentials(), DOMAIN)
    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-LD453-batch-insert-gate {int(time.time())}",
                             folder_token=dest_folder)
    doc_id = doc["document_id"]
    evidence = {"doc_id": doc_id}

    try:
        # 1) Seed the measured repro's six flat children of the page root.
        wc.create_children(doc_id, doc_id, [text_block(t) for t in DRIFT_SEED], index=0)

        md0, tree0 = _download(doc_id)
        md0_again, _ = _download(doc_id)
        assert md0 == md0_again, (
            "reader is non-deterministic: two downloads of the unchanged doc differ")
        seed_ids = list(wc.get_block(doc_id, doc_id).get("children") or ())
        assert len(seed_ids) == len(DRIFT_SEED), (
            f"seeding did not produce {len(DRIFT_SEED)} top-level children: {seed_ids!r}")
        evidence["seed_ids"] = seed_ids

        # 2) THE BATCH — three id-anchored AFTER inserts, all resolving to the page root,
        #    submitted in document order, planned and applied as ONE batch.
        plan = dry_run([
            InsertRequest(
                reference=AnchorById(block_id=seed_ids[at]),
                position=InsertPosition.AFTER,
                content=(NewParagraph(text=marker),),
            )
            for at, marker in sorted(DRIFT_MARKERS.items())
        ], tree0)
        assert len(plan.refusals) == 0, f"the batch refused at dry-run: {plan.refusals!r}"
        assert {e.insertion_point.parent_block_id for e in plan.resolved} == {doc_id}, (
            "the arm is only meaningful if all three entries resolve to the SAME parent: "
            f"{[e.insertion_point.parent_block_id for e in plan.resolved]!r}")
        evidence["plan_indexes"] = [e.insertion_point.index for e in plan.resolved]

        log = apply(plan, wc, doc_id)
        assert [e.outcome for e in log.entries] == ["inserted"] * 3, (
            [e.to_dict() for e in log.entries])
        created = [e.created_block_ids[0] for e in log.entries]
        assert all(created), f"an entry reported inserted with no created id: {created!r}"
        evidence["created"] = created

        # 3) READ BACK — the live child order is the whole point. Expected interleaving:
        #    s1 / alpha / M1 / s2 / beta / M2 / s3 / gamma / M3.
        live_ids = list(wc.get_block(doc_id, doc_id).get("children") or ())
        expected_ids = []
        for i, seed_id in enumerate(seed_ids):
            expected_ids.append(seed_id)
            if i in DRIFT_MARKERS:
                expected_ids.append(created[sorted(DRIFT_MARKERS).index(i)])
        evidence["live_child_order_ok"] = live_ids == expected_ids
        assert live_ids == expected_ids, (
            f"LD-453 regression — a same-parent multi-insert batch misplaced its inserts.\n"
            f"  expected: {expected_ids!r}\n  live    : {live_ids!r}")

        # 4) …and the TEXT at each position, read through the shipped reader.
        md1, _ = _download(doc_id)
        expected_text_order = []
        for i, text in enumerate(DRIFT_SEED):
            expected_text_order.append(text)
            if i in DRIFT_MARKERS:
                expected_text_order.append(DRIFT_MARKERS[i])
        got = [line.strip() for line in md1.splitlines() if DRIFT in line]
        evidence["read_back_order"] = got
        assert got == expected_text_order, (
            f"the document reads back in the wrong order.\n"
            f"  expected: {expected_text_order!r}\n  got     : {got!r}")

        # 5) Purely additive — nothing the batch touched was lost.
        removed = [d for d in difflib.ndiff(md0.splitlines(), md1.splitlines())
                   if d.startswith("- ")]
        assert not removed, f"the batch was not purely additive; lost: {removed}"
        evidence["purely_additive"] = True

    finally:
        emptied = False
        deleted = None
        try:
            child_ids = wc.get_block(doc_id, doc_id).get("children") or []
            if child_ids:
                wc.batch_delete(doc_id, doc_id, 0, len(child_ids))
            md_empty, _ = _download(doc_id)
            emptied = DRIFT not in md_empty
        except LarkDocIOError as e:
            evidence["empty_error"] = str(e)
        try:
            resp = wc.delete_document(doc_id)
            deleted = resp.get("code") if isinstance(resp, dict) else "ok"
        except LarkDocIOError as e:
            deleted = f"skipped ({e})"
        evidence["emptied"] = emptied
        evidence["deleted"] = deleted

    assert emptied, "teardown failed: gate content still present after restore"

    with capsys.disabled():
        print(
            "\n[live_write:W3-gate:LD-453-batch-insert] "
            f"doc_id={evidence['doc_id']} "
            f"plan_indexes={evidence.get('plan_indexes')} "
            f"created={evidence.get('created')} "
            f"child_order_ok={evidence.get('live_child_order_ok')} "
            f"purely_additive={evidence.get('purely_additive')} "
            f"emptied={evidence.get('emptied')} deleted={evidence.get('deleted')}\n"
            f"  read back: {evidence.get('read_back_order')!r}"
        )
