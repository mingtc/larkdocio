"""LD-151 / dogfood **F14** — the multi-turn rule, and the intra-batch ``not-found`` hedge.

The headline seat-session finding: queue an ``InsertRequest`` and then an ``EditRequest``
**anchored on the text that insert will create**, and the second one refuses ``not-found`` —
which is **correct** (one tree, one batch: every entry is resolved against a *single consistent
snapshot*) — but the refusal's ``detail`` ended *"re-read the document and copy the quote
verbatim"*, advice that **can never succeed** because the block does not exist yet. An agent
that trusts it **loops**.

The fix is **guidance, not engine** (see :mod:`larkdocio.write.intrabatch`'s docstring for the
one-tree-one-batch rationale, recorded so the limitation reads as deliberate):

* **(a) the recipe states the rule** — verbatim, derived here from the shipped
  :data:`~larkdocio.write.intrabatch.COMMIT_THEN_ANCHOR_RULE` constant so the doc guard cannot
  drift from the code's own words — and ends with a **worked two-commit example** that
  **executes** in the LD-133 extract-and-run harness;
* **(b) the ``not-found`` detail gains a hedging clause** when the failing anchor's text appears
  in the **same batch's** queued insert content: it names the intra-batch cause and the working
  recovery (commit, then anchor by ``created_block_ids``) instead of the re-read that cannot
  succeed.

Every guard here is on the thing it describes: the hedge is asserted by planning real batches
against a real parsed tree, the ordinary detail is asserted **byte-unchanged** for every
non-intra-batch case, and the doc claims are asserted at **content** level (the LD-132 lesson)
against the shipped guide text.
"""
from domain_vocabulary import RETIRED_ID
import json
import re

import pytest

import guide_recipes as gr
from doc_prose import missing_phrases, prose
from log_reading_apply import reading_the_log
from larkdocio import capabilities, guide
from larkdocio.model import Node
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write import (
    Anchor,
    AnchorById,
    DeleteRequest,
    EditRequest,
    InsertPosition,
    InsertRequest,
    NewBlock,
    NewParagraph,
    RefusalReason,
    SubSpanEditRequest,
    dry_run,
)
from larkdocio.write.intrabatch import (
    COMMIT_THEN_ANCHOR_RULE,
    INTRA_BATCH_HEDGE,
    authored_own_texts,
    hedge_intra_batch_not_found,
    queued_insert_texts,
)

MULTI_TURN_SLUG = "accumulate-edits-across-turns-a-multi-turn-request-queue"

#: The F14 batch's authored sentence — present ONLY in the batch's own queued insert content.
QUEUED = "On-time delivery held at 97.2%."
#: A quote absent from the tree AND from the batch — the control that must stay unchanged.
ABSENT = "a sentence that exists nowhere at all"
#: The fixture tree's real paragraph text (tests/guide_recipes.py's offline document).
FIXTURE_QUOTE = "Revenue grew 12.4% in Q3."


# --------------------------------------------------------------------------- #
# Shared helpers — one real parsed tree, one place that builds a plan.           #
# --------------------------------------------------------------------------- #

def _tree(doc_token: str = "LD151DOCTOKEN") -> Node:
    """The real reader's node tree over the harness fixture payload — never a hand-mocked
    stand-in, so every refusal below is the shipped resolver's own."""
    import harness  # tests/ is on sys.path (conftest)

    blocks = harness.build_blocks(gr.fixture_block_dicts(doc_token))
    return Parser(Config()).parse_docx_tree(doc_token, blocks)


def _tree_with_a_duplicated_paragraph(doc_token: str = "LD151DUPETOKEN") -> Node:
    """The same fixture plus a **second** paragraph carrying the identical sentence — so a
    quote anchor on it refuses ``ambiguous-N-candidates`` rather than ``not-found``."""
    import harness  # tests/ is on sys.path (conftest)

    payload = [dict(block) for block in gr.fixture_block_dicts(doc_token)]
    for block in payload:
        if block["block_id"] == "h1":
            block["children"] = ["p1", "p2"]
    payload.append({
        "block_id": "p2", "parent_id": "h1", "block_type": 2,
        "text": {"elements": [{"text_run": {"content": FIXTURE_QUOTE}}]},
        "children": [],
    })
    return Parser(Config()).parse_docx_tree(doc_token, harness.build_blocks(payload))


def _insert(text, *, quote=FIXTURE_QUOTE, position=InsertPosition.AFTER):
    return InsertRequest(
        reference=Anchor(quote=quote, breadcrumb=()),
        position=position,
        content=(NewBlock.paragraph(text),),
    )


def _edit(quote, replacement="rewritten"):
    return EditRequest(anchor=Anchor(quote=quote, breadcrumb=()), replacement=replacement)


def _refusal_of(plan, index):
    entry = plan.entries[index]
    assert not entry.is_resolved, entry.to_dict()
    return entry.refusal


def _ordinary_not_found_detail(quote) -> str:
    """The detail the resolver produces for ``quote`` with **no** insert in the batch — the
    byte-for-byte baseline every no-hedge assertion below compares against."""
    return _refusal_of(dry_run([_edit(quote)], _tree()), 0).detail


# --------------------------------------------------------------------------- #
# AC1 (a) — the recipe STATES the rule, verbatim, at content level.              #
# --------------------------------------------------------------------------- #

def test_ac1_the_rule_constant_is_the_sentence_the_ac_names():
    """AC1: the shipped constant IS the maintainer's sentence — the doc guards derive the required
    wording from it, so there is exactly one place the rule is written down."""
    assert COMMIT_THEN_ANCHOR_RULE == (
        "every queued request must target content that exists at commit time; commit the "
        "insert, then anchor follow-ups by created_block_ids"
    )


def test_ac1_the_multi_turn_recipe_states_the_rule():
    """AC1: the rule appears in the multi-turn recipe's **preamble** — the text a consumer
    reads before pasting — at content level (wrapping and emphasis are irrelevant, the words
    are not)."""
    preamble = gr.recipe_preamble(MULTI_TURN_SLUG)
    assert not missing_phrases(preamble, [COMMIT_THEN_ANCHOR_RULE]), (
        "the multi-turn recipe preamble must state the rule: " + COMMIT_THEN_ANCHOR_RULE)


def test_ac1_the_rule_guard_bites_on_a_paraphrase():
    """AC1 (red-then-green on the guard itself): a faithful **paraphrase** must FAIL the same
    check that greens the shipped text — otherwise "states the rule" means nothing.

    **TRANSFORMED by LD-547, for the reason LD-512 transformed the four ``…_BITES`` proofs in**
    ``tests/test_read_back_law_and_restructure.py`` (that file's own comment at the foot states
    the shape). This proof used to hand-roll a *second copy* of the predicate — ``prose(RULE)
    not in paraphrased`` — over a copy it had itself prose-normalized and mutated, so the only
    way it could fail was for ``str.replace`` to stop removing what it replaces. It never asked
    :func:`doc_prose.missing_phrases`, which is the check that greens the shipped text one test
    above, and whose own docstring says it returns rather than asserts *"so the same function
    can be used to prove a guard bites"*. Now it calls THAT — once on the shipped text, where
    nothing may be missing, and once on the paraphrase, where the rule must be reported missing
    **by name**. A future loosening of ``missing_phrases`` (fuzzy matching, a similarity score)
    reddens here instead of sailing past a tautology.
    """
    text = guide(full=True)
    assert missing_phrases(text, [COMMIT_THEN_ANCHOR_RULE]) == [], (
        "the shipped guide does not state the rule even before crippling — the proof would "
        "be measuring the wrong thing")
    paraphrased = prose(text).replace(
        prose(COMMIT_THEN_ANCHOR_RULE),
        prose("target only content that is already there, and follow up using the returned ids"),
    )
    assert paraphrased != prose(text), "the mutation did not apply — the proof would be vacuous"
    assert missing_phrases(paraphrased, [COMMIT_THEN_ANCHOR_RULE]) == [COMMIT_THEN_ANCHOR_RULE], (
        "the same check that greens the shipped text ACCEPTED a faithful paraphrase — "
        '"states the rule" then means nothing')


def test_ac1_the_guard_is_not_satisfied_by_the_mere_word_commit():
    """AC1 (the AC's own words): "a content-level test asserts the sentence (**not mere
    presence of the word 'commit'**)". A preamble that says "commit" and nothing else must
    fail."""
    decoy = "Then commit the queue when the user approves."
    assert missing_phrases(decoy, [COMMIT_THEN_ANCHOR_RULE]) == [COMMIT_THEN_ANCHOR_RULE]


def test_ac1_the_recipe_explains_why_the_rule_exists():
    """AC1: the rule is *argued*, not listed (dogfood D1) — the preamble states the one-tree-
    one-batch cause and that a batch cannot depend on its own writes."""
    missing = missing_phrases(gr.recipe_preamble(MULTI_TURN_SLUG), [
        "one tree, one batch",
        "single consistent snapshot",
        "a batch cannot depend on its own writes",
    ])
    assert not missing, f"the multi-turn preamble does not argue the rule: {missing}"


# --------------------------------------------------------------------------- #
# AC2 (a) — the WORKED TWO-COMMIT EXAMPLE, executing in the LD-133 harness.      #
# --------------------------------------------------------------------------- #

def test_ac2_the_recipe_source_shows_two_commits_in_order():
    """AC2: the recipe's own source is the two-commit shape — commit 1 applies, its
    ``created_block_ids`` are captured, and commit 2 anchors **by id** after that."""
    src = gr.recipe_source(MULTI_TURN_SLUG)
    # `= apply(` — a real commit binds its log; a bare `apply()` in prose does not count.
    applies = [m.start() for m in re.finditer(r"=\s*apply\(", src)]
    assert len(applies) == 2, (
        f"the recipe must show TWO commits (two apply() calls); found {len(applies)}")
    capture = src.index("created_block_ids")
    assert applies[0] < capture < applies[1], (
        "commit 1 must apply, THEN its created_block_ids captured, THEN commit 2 apply")
    # The USE of AnchorById (its import sits at the top of every recipe), after the capture.
    assert src.index("AnchorById(block_id=") > capture, (
        "the follow-up must be anchored by an id apply() returned, not by a quote")


def test_ac2_the_two_commit_example_executes_in_the_harness(monkeypatch, tmp_path):
    """AC2: the example **runs** (offline, injected transport) — commit 1 lands the batch and
    hands back ids, commit 2 resolves one of those ids through an ``AnchorById`` and lands."""
    ns = gr.stage(monkeypatch, tmp_path).run(MULTI_TURN_SLUG)

    created = ns["created_block_ids"]
    assert created and all(created), f"commit 1 must hand back created ids: {created!r}"
    (follow_up_entry,) = ns["follow_up_plan"].entries
    assert follow_up_entry.is_resolved, follow_up_entry.to_dict()
    assert follow_up_entry.anchor == AnchorById(block_id=created[0]), (
        follow_up_entry.to_dict())
    assert [e.to_dict()["outcome"] for e in ns["follow_up_log"].entries] == ["inserted"], (
        [e.to_dict() for e in ns["follow_up_log"].entries])


def test_ac2_commit_two_reads_the_document_again_before_planning():
    """AC2: the second commit re-reads — a plan resolves against a freshly parsed tree, and
    what commit 1 created is not in the tree commit 1 planned from."""
    src = gr.recipe_source(MULTI_TURN_SLUG)
    reads = [m.start() for m in re.finditer(r"get_docx_content\(", src)]
    assert len(reads) == 2, f"each commit must read the document itself; found {len(reads)}"
    assert reads[1] > src.index("created_block_ids")


# --------------------------------------------------------------------------- #
# AC3 (b) — the F14 batch: the not-found detail gains the hedging clause.        #
# --------------------------------------------------------------------------- #

def test_ac3_the_exact_f14_two_request_batch_hedges_its_refusal():
    """AC3: **the** F14 shape — insert a paragraph, then edit the text that insert will
    create. The second entry refuses, and its detail names the intra-batch cause plus the
    recovery that works."""
    plan = dry_run([_insert(QUEUED), _edit(QUEUED)], _tree())
    assert plan.entries[0].is_resolved, plan.entries[0].to_dict()
    refusal = _refusal_of(plan, 1)
    missing = missing_phrases(refusal.detail, [
        "this batch queues an insert containing this text",
        "a batch cannot depend on its own writes",
        "commit the insert first, then anchor by created_block_ids",
    ])
    assert not missing, f"the hedged detail omits {missing}: {refusal.detail!r}"


def test_ac3_the_hedge_says_the_re_read_advice_cannot_help():
    """AC3: the misdirection is *corrected*, not merely followed by more text — the detail
    states that re-reading cannot help for this case."""
    refusal = _refusal_of(dry_run([_insert(QUEUED), _edit(QUEUED)], _tree()), 1)
    assert not missing_phrases(refusal.detail, ["re-reading the document cannot help"]), (
        refusal.detail)


def test_ac3_the_hedged_detail_extends_the_ordinary_one():
    """AC3: the hedge is **additive** — the ordinary diagnosis survives verbatim as the
    prefix, so nothing a consumer already parses is lost."""
    ordinary = _ordinary_not_found_detail(QUEUED)
    hedged = _refusal_of(dry_run([_insert(QUEUED), _edit(QUEUED)], _tree()), 1).detail
    assert hedged == ordinary + INTRA_BATCH_HEDGE
    assert hedged.startswith(ordinary)


def test_ac3_the_hedge_fires_for_every_block_level_family():
    """AC3: the shape is not edit-specific — a delete or a sub-span anchored on the batch's
    own queued text gets the same hedge (an agent loops just as hard on any of them)."""
    families = [
        DeleteRequest(target=Anchor(quote=QUEUED, breadcrumb=())),
        SubSpanEditRequest(anchor=Anchor(quote=QUEUED, breadcrumb=()), span="97.2%",
                           replacement="98.0%"),
        InsertRequest(reference=Anchor(quote=QUEUED, breadcrumb=()),
                      position=InsertPosition.AFTER,
                      content=(NewParagraph(text="after the block this batch creates"),)),
    ]
    for request in families:
        plan = dry_run([_insert(QUEUED), request], _tree())
        refusal = _refusal_of(plan, 1)
        assert refusal.reason is RefusalReason.NOT_FOUND, refusal.to_dict()
        assert INTRA_BATCH_HEDGE in refusal.detail, (type(request).__name__, refusal.detail)


# --------------------------------------------------------------------------- #
# AC4 — detected at PLAN time by scanning the batch's OWN queued insert content. #
# --------------------------------------------------------------------------- #

def test_ac4_a_genuinely_absent_quote_keeps_the_ordinary_detail_byte_for_byte():
    """AC4: a quote absent from the tree **and** from the batch keeps the shipped wording
    **byte-unchanged** — including its remedy tail, which for a single-request batch is
    exactly the right advice.

    **LD-455 amended the tail, not this property.** The remedy used to read "re-read the
    document and copy the quote verbatim" and now reads
    :data:`~larkdocio.write.resolve.NOT_FOUND_REMEDY`, because the old sentence named the
    action the consumer had just taken. What this test asserts is unchanged and is the thing
    it was written for: the intra-batch hedge does not fire, and the ordinary detail comes
    back byte-identical — so the tail is imported rather than re-spelled here.
    """
    from larkdocio.write.resolve import NOT_FOUND_REMEDY

    ordinary = _ordinary_not_found_detail(ABSENT)
    batched = _refusal_of(dry_run([_insert(QUEUED), _edit(ABSENT)], _tree()), 1).detail
    assert batched == ordinary
    assert NOT_FOUND_REMEDY in batched
    assert INTRA_BATCH_HEDGE not in batched


def test_ac4_the_scan_reads_the_authored_content_not_the_tree():
    """AC4: the corpus is built from the batch's queued **insert content** — the authored
    strings, one per block that would be created (nested children and table cells included),
    mirroring the resolver's own "a block's OWN text" rule."""
    content = (
        NewBlock.bullet("parent item", children=(NewBlock.bullet("nested child"),)),
        NewBlock.table([["Metric", "Value"], ["On-time delivery", "97.2%"]]),
        NewParagraph(text="a legacy tagless paragraph"),
    )
    texts = authored_own_texts(content)
    for expected in ("parent item", "nested child", "Metric", "Value", "On-time delivery",
                     "97.2%", "a legacy tagless paragraph"):
        assert expected in texts, (expected, texts)


def test_ac4_the_corpus_comes_only_from_insert_entries():
    """AC4: ``queued_insert_texts`` reads insert entries and nothing else — an edit's
    ``replacement`` and a delete's target are not content the batch creates."""
    plan = dry_run([
        _insert("authored by the insert"),
        _edit(FIXTURE_QUOTE, replacement="replaced by the edit"),
        DeleteRequest(target=Anchor(quote="Overview", breadcrumb=())),
    ], _tree())
    texts = queued_insert_texts(plan.entries)
    assert texts == ("authored by the insert",), texts


def test_ac4_the_corpus_filters_on_the_op_not_merely_on_the_content_field():
    """AC4: the filter is **``op == "insert"``**, not "whatever entry happens to carry
    ``content``".

    Today only an insert entry populates ``content``, so a test built from real requests cannot
    tell the two rules apart — and the day a future op carries authored content (or a shape
    changes underneath), the weaker rule would start seeding the corpus from ops that create no
    block, hedging with a recovery that does not apply. Asserted against the filter directly, on
    entry-shaped stand-ins, so the mutation is visible.
    """
    class _Entry:
        def __init__(self, op, content):
            self.op, self.content = op, content

    payload = (NewBlock.paragraph("content on a non-insert entry"),)
    assert queued_insert_texts([_Entry("insert", payload)]) == (
        "content on a non-insert entry",)
    for op in ("edit", "delete", "subspan"):
        assert queued_insert_texts([_Entry(op, payload)]) == (), op


def test_ac4_the_hedge_costs_zero_extra_api_calls(monkeypatch, tmp_path):
    """AC4 (the amplifier's call-count spy): the hedge is pure plan-time inspection —
    ``dry_run`` takes no client at all, and a hedged batch makes **exactly** the same calls as
    an unhedged one (the single read that built the tree, and no write)."""
    stage = gr.stage(monkeypatch, tmp_path)
    from larkdocio.read.client import Client
    from larkdocio.write.client import WriteClient

    reader = Client("cli_read_offline", "read-secret-offline", "larksuite.com")
    writer = WriteClient("cli_write_offline", "write-secret-offline", "larksuite.com")
    doc_token = "LD151SPYDOCTOKEN"
    docx, blocks = reader.get_docx_content(doc_token)
    tree = Parser(Config()).parse_docx_tree(doc_token, blocks)
    assert len(reader.calls) == 1, reader.calls

    hedged = dry_run([_insert(QUEUED), _edit(QUEUED)], tree)
    assert INTRA_BATCH_HEDGE in _refusal_of(hedged, 1).detail
    plain = dry_run([_insert(QUEUED), _edit(ABSENT)], tree)
    assert INTRA_BATCH_HEDGE not in _refusal_of(plain, 1).detail

    assert len(reader.calls) == 1, f"the hedge read the document again: {reader.calls}"
    assert (writer.patches, writer.created, writer.deleted) == ([], [], []), (
        "a dry-run must issue ZERO writes, hedged or not")
    assert stage.documents is not None


def test_ac4_the_scan_is_exact_substring_never_normalized():
    """AC4 (the amplifier's decision, PINNED): the scan matches the quote as an **exact
    substring** of one authored block's text — the *same* rule the resolver applies at commit
    time.

    **Why exact and not normalized.** A case-folded / whitespace-collapsed match would hedge
    anchors that the post-commit ``AnchorById`` recovery does not even need and that a
    *quote*-anchored retry would still refuse — i.e. it would promise a recovery that fails,
    which is worse than the plain refusal. The hedge is only ever emitted where the sanctioned
    idiom genuinely applies.
    """
    for near_miss in (QUEUED.lower(), QUEUED.replace(" ", "  "), QUEUED.rstrip(".")+ " !"):
        if near_miss == QUEUED:                     # guard against a no-op mutation
            continue
        detail = _refusal_of(dry_run([_insert(QUEUED), _edit(near_miss)], _tree()), 1).detail
        assert detail == _ordinary_not_found_detail(near_miss), near_miss
        assert INTRA_BATCH_HEDGE not in detail, near_miss


def test_ac4_the_scan_never_crosses_two_authored_blocks():
    """AC4: the corpus is one string **per block**, never the concatenation — a quote that
    spans two authored blocks matches no block's own text at commit time either, so hedging it
    would be a promise the recovery cannot keep."""
    plan = dry_run([
        InsertRequest(
            reference=Anchor(quote=FIXTURE_QUOTE, breadcrumb=()),
            position=InsertPosition.AFTER,
            content=(NewBlock.paragraph("first half"), NewBlock.paragraph("second half")),
        ),
        _edit("first half second half"),
    ], _tree())
    detail = _refusal_of(plan, 1).detail
    assert INTRA_BATCH_HEDGE not in detail
    assert detail == _ordinary_not_found_detail("first half second half")


def test_ac4_the_hedge_finds_the_text_in_the_second_of_two_queued_inserts():
    """AC4 (the amplifier): the scan covers the WHOLE batch, not just the first insert."""
    plan = dry_run([_insert("something else entirely"), _insert(QUEUED), _edit(QUEUED)],
                   _tree())
    assert INTRA_BATCH_HEDGE in _refusal_of(plan, 2).detail


def test_ac4_the_hedge_is_order_independent():
    """AC4: one tree, one batch — **order inside a batch is not a dependency order**, so the
    hedge fires even when the failing request is queued BEFORE the insert that would create
    its text. (An agent that "fixed" F14 by reordering would otherwise get silence.)"""
    plan = dry_run([_edit(QUEUED), _insert(QUEUED)], _tree())
    assert INTRA_BATCH_HEDGE in _refusal_of(plan, 0).detail


def test_ac4_a_refused_insert_still_seeds_the_corpus():
    """AC4: the batch *queues* the insert whether or not the insert itself resolved, so the
    hedge still explains the follow-up's refusal (the consumer sees both refusals and fixes
    the insert first)."""
    plan = dry_run([_insert(QUEUED, quote=ABSENT), _edit(QUEUED)], _tree())
    assert not plan.entries[0].is_resolved, plan.entries[0].to_dict()
    assert INTRA_BATCH_HEDGE in _refusal_of(plan, 1).detail


# --------------------------------------------------------------------------- #
# AC5 — NO false hedging.                                                       #
# --------------------------------------------------------------------------- #

def test_ac5_an_edit_replacement_does_not_trigger_the_insert_clause():
    """AC5: a quote that appears in a queued **edit**'s replacement is not content the batch
    *creates* — committing that edit does not mint a block to anchor by id, so the
    insert-specific clause must not fire."""
    replacement = "text that only a queued EDIT would produce"
    plan = dry_run([_edit(FIXTURE_QUOTE, replacement=replacement), _edit(replacement)],
                   _tree())
    detail = _refusal_of(plan, 1).detail
    assert INTRA_BATCH_HEDGE not in detail
    assert detail == _ordinary_not_found_detail(replacement)


def test_ac5_a_delete_target_does_not_trigger_the_insert_clause():
    """AC5: a quote that appears in a queued **delete** does not trigger the clause either —
    a delete creates nothing."""
    plan = dry_run([DeleteRequest(target=Anchor(quote=ABSENT, breadcrumb=())), _edit(ABSENT)],
                   _tree())
    detail = _refusal_of(plan, 1).detail
    assert INTRA_BATCH_HEDGE not in detail
    assert detail == _ordinary_not_found_detail(ABSENT)


def test_ac5_a_batch_with_no_insert_at_all_is_byte_unchanged():
    """AC5: with no insert in the batch there is nothing to scan and nothing may change."""
    plan = dry_run([_edit(ABSENT), _edit("another missing quote")], _tree())
    assert _refusal_of(plan, 0).detail == _ordinary_not_found_detail(ABSENT)
    assert _refusal_of(plan, 1).detail == _ordinary_not_found_detail("another missing quote")


def test_ac5_an_id_anchor_is_never_hedged():
    """AC5: an ``AnchorById`` carries no quote — an id cannot "appear in queued content", and
    its shipped detail already names ``created_block_ids`` as the repair. It stays unchanged."""
    plan = dry_run([_insert(QUEUED),
                    EditRequest(anchor=AnchorById(block_id="nosuchid"),
                                replacement="never")], _tree())
    refusal = _refusal_of(plan, 1)
    assert refusal.reason is RefusalReason.NOT_FOUND
    assert INTRA_BATCH_HEDGE not in refusal.detail
    assert "nosuchid" in refusal.detail


def test_ac5_other_refusal_reasons_are_never_touched():
    """AC5: only ``not-found`` is enriched. An ambiguous quote, a write-hostile target and a
    position-capability refusal keep their own details even in a batch full of inserts."""
    # AMBIGUOUS — the quote IS in the batch's queued insert content, and it also matches two
    # real blocks. Two candidates is not "does not exist yet"; the repair is a longer quote.
    ambiguous = dry_run([_insert(FIXTURE_QUOTE, quote="Overview"), _edit(FIXTURE_QUOTE)],
                        _tree_with_a_duplicated_paragraph())
    entry = ambiguous.entries[1]
    assert entry.refusal.reason is RefusalReason.AMBIGUOUS, entry.to_dict()
    assert INTRA_BATCH_HEDGE not in entry.refusal.detail

    # CANNOT_HOLD_SIBLINGS — a POSITION failure on a reference that resolved, even though the
    # batch queues the very text the reference quotes. The repair is the position, not a commit.
    siblings = dry_run([
        _insert("Q3 Board Update", quote="Overview"),
        InsertRequest(reference=Anchor(quote="Q3 Board Update", breadcrumb=()),
                      position=InsertPosition.BEFORE,
                      content=(NewBlock.paragraph("beside the document root"),)),
    ], _tree())
    entry = siblings.entries[1]
    assert entry.refusal.reason is RefusalReason.CANNOT_HOLD_SIBLINGS, entry.to_dict()
    assert INTRA_BATCH_HEDGE not in entry.refusal.detail


# --------------------------------------------------------------------------- #
# AC6 — ENGINE UNCHANGED (reason, resolution, batch semantics, and the record).  #
# --------------------------------------------------------------------------- #

def test_ac6_the_reason_is_still_not_found():
    """AC6: only the ``detail`` is enriched — the typed reason (what a consumer branches on)
    is untouched, so no code reading ``refusal.reason`` changes behavior."""
    refusal = _refusal_of(dry_run([_insert(QUEUED), _edit(QUEUED)], _tree()), 1)
    assert refusal.reason is RefusalReason.NOT_FOUND
    assert refusal.to_dict()["reason"] == "not-found"
    assert refusal.candidate_ids == ()


def test_ac6_the_resolver_itself_is_batch_blind():
    """AC6: resolution is unchanged — the shipped resolver returns the **identical** refusal
    for the request whether or not sibling requests are in the batch. The hedge lives strictly
    above it, as plan-time disclosure."""
    from larkdocio.write.resolve import resolve

    tree = _tree()
    alone = resolve(_edit(QUEUED), tree)
    batched = resolve(_edit(QUEUED), tree)
    assert alone == batched
    assert alone.detail == _ordinary_not_found_detail(QUEUED)
    assert INTRA_BATCH_HEDGE not in alone.detail


def test_ac6_resolved_entries_are_untouched_by_the_hedge():
    """AC6: batch semantics are unchanged — the resolved entries of a hedged batch serialize
    **identically** to the same requests planned without the failing sibling."""
    with_failure = dry_run([_insert(QUEUED), _edit(QUEUED)], _tree())
    without = dry_run([_insert(QUEUED)], _tree())
    assert with_failure.entries[0].to_dict() == without.entries[0].to_dict()
    assert len(with_failure.entries) == 2 and len(with_failure.refusals) == 1


def test_ac6_the_hedge_is_a_pure_function_of_the_entries():
    """AC6: the hedge pass is idempotent and total — applied to entries that carry no insert
    it returns them unchanged (identity), so it cannot mutate a plan by being run twice."""
    entries = dry_run([_edit(ABSENT)], _tree()).entries
    assert hedge_intra_batch_not_found(entries) == entries

    hedged = dry_run([_insert(QUEUED), _edit(QUEUED)], _tree()).entries
    assert hedge_intra_batch_not_found(hedged) == hedged


def test_ac6_the_one_tree_one_batch_rationale_is_recorded_in_the_code():
    """AC6: the limitation is recorded **in the code's docstring** so a future reader cannot
    mistake it for an oversight — including WHY the engine fix is rejected and WHEN to
    revisit."""
    import larkdocio.write.intrabatch as intrabatch

    missing = missing_phrases(intrabatch.__doc__ or "", [
        "one tree, one batch",
        "single consistent snapshot",
        "sequential re-planning inside apply()",
        "do not fix this in the engine",
        "session layer",
    ])
    assert not missing, f"the one-tree-one-batch rationale is not recorded: {missing}"


def test_ac6_the_engine_modules_are_not_the_hedge_site():
    """AC6: the hedge lives in its own module and is applied by the previewer — the resolver
    and the apply engine never mention it, which is the structural form of "engine
    unchanged"."""
    import importlib
    from pathlib import Path

    # ``larkdocio.write.apply`` the ATTRIBUTE is the apply() function (the package re-exports
    # it), so the modules are fetched by name rather than by attribute access.
    for name in ("larkdocio.write.resolve", "larkdocio.write.apply"):
        source = Path(importlib.import_module(name).__file__).read_text(encoding="utf-8")
        assert "intrabatch" not in source and "INTRA_BATCH" not in source, name


# --------------------------------------------------------------------------- #
# AC7 — truth-rows: capabilities() + the guide, content-guarded (LD-132).        #
# --------------------------------------------------------------------------- #

def test_ac7_capabilities_carries_the_one_tree_one_batch_contract():
    """AC7: the contract is a first-class, discoverable safety contract of docx-write — the
    rule had no home in ``capabilities()`` at all, which is part of why F14 happened."""
    caps = capabilities(full=True)
    assert "one-tree-one-batch" in caps["safety_contracts"]
    assert "one-tree-one-batch" in caps["surfaces"]["docx-write"]["safety_contracts"]
    assert "one-tree-one-batch" not in caps["surfaces"]["sheets-write"]["safety_contracts"]


def test_ac7_the_contract_summary_states_the_rule_and_the_hedge():
    """AC7 (**content**-guarded — the LD-132 lesson): an id in a table is blind to the prose
    rotting, so the summary itself must carry the rule, the cause, and the disclosure."""
    summary = capabilities(full=True)["safety_contracts"]["one-tree-one-batch"]["summary"]
    missing = missing_phrases(summary, [
        COMMIT_THEN_ANCHOR_RULE,
        "single consistent snapshot",
        "a batch cannot depend on its own writes",
        "created_block_ids",
        "not-found",
    ])
    assert not missing, f"the one-tree-one-batch summary omits {missing}"


def test_ac7_the_guide_matrix_row_states_the_rule_and_the_hedge():
    """AC7: the guide's capability-matrix row is the human-facing half of the same truth —
    content-guarded, not merely present."""
    row = _matrix_contract_row("one-tree-one-batch")
    missing = missing_phrases(row, [
        COMMIT_THEN_ANCHOR_RULE,
        "a batch cannot depend on its own writes",
        "not-found",
    ])
    assert not missing, f"the guide's one-tree-one-batch row omits {missing}: {row!r}"


def test_ac7_the_guide_and_capabilities_agree_on_the_contract_set():
    """AC7: the shipped bidirectional guard covers the NEW coupling too — a contract in code
    with no guide row (or the reverse) reddens. Asserted here directly so this issue's own
    coupling is proven, not assumed."""
    # The "applies to" column was write-surface-only when this guard was written. It is not
    # any more: a scope denial can happen on a READ surface too, so the cross-cutting
    # permission contract's row reads "every surface". Matching that alternative keeps the
    # coupling bidirectional instead of silently dropping the one contract that is not
    # write-specific.
    # LD-260 widened the alternation again, for the same reason: `base-write` is a third
    # write surface, and its staleness contract's row names it alone. LD-266 widened it once
    # more for `base-schema-write`, whose three contracts each name only it — and the longer
    # id is listed FIRST so the alternation cannot match its prefix and stop.
    # LD-410 widened it once more for `docx-read` — the first READ-side contract; a
    # contract this alternation cannot see reads to the check as an omission.
    # LD-432 widened it once more for `drive-access-write` — a write surface outside the
    # docx/sheets/base families, whose read-back contract's row names it alone.
    # LD-645 TRANSFORMED the alternation rather than widening it a fifth time. THE REASON
    # ABOVE IS UNCHANGED AND STILL BINDS — a contract whose "applies to" column this pattern
    # cannot see still reads to the check as an omission, which is exactly why the list may
    # not be hand-kept: it went stale on every new surface, and a stale one makes the
    # bidirectional check quietly narrower instead of red. The surface ids now come from the
    # census itself (longest first, so an id cannot match a shorter id's prefix and stop),
    # with "every surface" kept as the one non-id spelling a row is allowed to use.
    _surface_ids = sorted(capabilities(full=True)["surfaces"], key=len, reverse=True)
    assert _surface_ids, "the census reports no surfaces; this guard would match nothing"
    guide_ids = set(re.findall(
        r"^\| `([^`]+)` \| (?:" + "|".join(_surface_ids + ["every surface"]) + r")",
        _matrix_region(), flags=re.MULTILINE))
    assert "one-tree-one-batch" in guide_ids
    assert guide_ids == set(capabilities(full=True)["safety_contracts"]), (
        sorted(guide_ids ^ set(capabilities(full=True)["safety_contracts"])))


def test_ac7_the_live_gate_ring_proves_the_contract():
    """AC7: a safety contract nothing proves live is a claim, not a guarantee — the docx ring
    must name an arm for it (the shipped ``test_capabilities`` guard requires a prover; this
    pins WHICH arm, so the arm cannot be quietly dropped)."""
    members = capabilities(full=True)["surfaces"]["docx-write"]["gate_coverage"]["members"]
    provers = [m for m in members if "one-tree-one-batch" in m["proves_contracts"]]
    assert provers, "no docx live gate member proves one-tree-one-batch"
    assert any("intra-batch" in arm for m in provers for arm in m["arms"]), (
        [m["arms"] for m in provers])


def test_ac7_the_new_strings_are_dialect_free_at_birth():
    """AC7 / LD-153's scope, honoured up front: nothing this issue ships leaks an internal
    dialect token (a tranche id, a finding code, a role name) into consumer-facing text."""
    surfaces = {
        "the hedge": INTRA_BATCH_HEDGE,
        "the rule": COMMIT_THEN_ANCHOR_RULE,
        "the contract summary":
            capabilities(full=True)["safety_contracts"]["one-tree-one-batch"]["summary"],
        "the guide row": _matrix_contract_row("one-tree-one-batch"),
        "the recipe preamble": gr.recipe_preamble(MULTI_TURN_SLUG),
    }
    for where, text in surfaces.items():
        for token in ("LD-1", "F14", "dogfood", "W3 ", "AC1", "tranche"):
            assert token not in text, f"{where} leaks the internal token {token!r}"
        assert not RETIRED_ID.search(text), f"{where} leaks a private-set id"


# --------------------------------------------------------------------------- #
# The amplifier's 3-COMMIT CHAIN — executing in the harness.                     #
# --------------------------------------------------------------------------- #

def test_a_three_commit_chain_executes_offline(monkeypatch, tmp_path):
    """The amplifier: insert → id-anchored edit → id-anchored delete, three separate commits
    against the harness's shared offline document. This is the sanctioned idiom carried past
    two hops — proof the rule scales, not just a one-off pair."""
    gr.stage(monkeypatch, tmp_path)
    from larkdocio.read.client import Client
    from larkdocio.write import apply
    apply = reading_the_log(apply)
    from larkdocio.write.client import WriteClient

    doc_token = "LD151CHAINDOCTOKEN"
    reader = Client("cli_read_offline", "read-secret-offline", "larksuite.com")
    writer = WriteClient("cli_write_offline", "write-secret-offline", "larksuite.com")

    def tree():
        _docx, blocks = reader.get_docx_content(doc_token)
        return Parser(Config()).parse_docx_tree(doc_token, blocks)

    # COMMIT 1 — create.
    log1 = apply(dry_run([_insert("drafted in commit one")], tree()), writer,
                 document_id=doc_token)
    (created_id,) = log1.entries[0].created_block_ids

    # COMMIT 2 — refine BY ID (a quote of what commit 1 wrote is exactly what the rule bans
    # inside one batch; across commits it is simply unnecessary).
    plan2 = dry_run([EditRequest(anchor=AnchorById(block_id=created_id),
                                 replacement="revised in commit two")], tree())
    assert not plan2.refusals, [e.to_dict() for e in plan2.refusals]
    log2 = apply(plan2, writer, document_id=doc_token)
    assert [e.to_dict()["outcome"] for e in log2.entries] == ["applied"]

    # COMMIT 3 — remove BY ID.
    plan3 = dry_run([DeleteRequest(target=AnchorById(block_id=created_id))], tree())
    assert not plan3.refusals, [e.to_dict() for e in plan3.refusals]
    log3 = apply(plan3, writer, document_id=doc_token)
    assert [e.to_dict()["outcome"] for e in log3.entries] == ["deleted"]

    document = gr.OfflineWriteClient.documents.for_token(doc_token)
    assert created_id not in document.blocks, "commit 3 did not remove the block"


# --------------------------------------------------------------------------- #
# The hedge survives serialization + reaches the apply log.                      #
# --------------------------------------------------------------------------- #

def test_the_hedged_detail_survives_the_plan_wire_form():
    """A refusal an agent reads out of ``plan.to_json()`` must carry the hedge too — the
    approval UX is where an autonomous consumer actually looks."""
    plan = dry_run([_insert(QUEUED), _edit(QUEUED)], _tree())
    wire = json.loads(plan.to_json())
    assert INTRA_BATCH_HEDGE in wire["entries"][1]["refusal"]["detail"]


def test_the_hedged_detail_reaches_the_apply_log(monkeypatch, tmp_path):
    """The refusal a *plan* carries is the refusal the **apply log** carries — an agent that
    only inspects the log after apply() still gets the working recovery."""
    gr.stage(monkeypatch, tmp_path)
    from larkdocio.read.client import Client
    from larkdocio.write import apply
    apply = reading_the_log(apply)
    from larkdocio.write.client import WriteClient

    doc_token = "LD151LOGDOCTOKEN"
    reader = Client("cli_read_offline", "read-secret-offline", "larksuite.com")
    writer = WriteClient("cli_write_offline", "write-secret-offline", "larksuite.com")
    _docx, blocks = reader.get_docx_content(doc_token)
    tree = Parser(Config()).parse_docx_tree(doc_token, blocks)

    log = apply(dry_run([_insert(QUEUED), _edit(QUEUED)], tree), writer, document_id=doc_token)
    refused = [e for e in log.entries if e.to_dict()["outcome"] == "refused"]
    assert len(refused) == 1, [e.to_dict() for e in log.entries]
    assert INTRA_BATCH_HEDGE in refused[0].refusal.detail


# --------------------------------------------------------------------------- #
# Guide-matrix readers (local, so this module does not import a test module).    #
# --------------------------------------------------------------------------- #

def _matrix_region() -> str:
    text = guide(full=True)
    b = text.find("<!-- BEGIN CAPABILITY-MATRIX")
    e = text.find("<!-- END CAPABILITY-MATRIX")
    assert b != -1 and e > b, "the guide has no CAPABILITY-MATRIX region"
    return text[b:e]


def _matrix_contract_row(contract_id: str) -> str:
    rows = [line for line in _matrix_region().splitlines()
            if line.strip().startswith(f"| `{contract_id}` |")]
    assert len(rows) == 1, (
        f"the capability matrix must carry exactly one {contract_id!r} row; found {len(rows)}")
    return rows[0]


@pytest.mark.parametrize("contract_id", ["one-tree-one-batch"])
def test_the_matrix_row_reader_finds_the_row(contract_id):
    """A guard on the guard: the row reader used above really locates a row (a silent miss
    would make every content assertion vacuous — the LD-132 failure mode)."""
    assert f"`{contract_id}`" in _matrix_contract_row(contract_id)
