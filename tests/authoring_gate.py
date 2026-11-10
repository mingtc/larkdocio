"""THE AUTHORING GATE's ring, written ONCE and run against two backends (LD-140 / § F1-S7).

The gate this module implements is the tranche closer: **author a multi-block Markdown
fragment into a real document, read it back, and prove it is the SAME Markdown** — plus the
**live concurrency arm** proving ``STALE_DOCUMENT`` fires on real out-of-band drift, leaves
the document byte-unchanged, and is **recoverable** by a re-plan.

**Why the ring lives here instead of inside the live test.** A credential-gated test that
only ever runs at QA is a test that is only ever *debugged* at QA, and its assertions are
invisible to ``pytest -q``. So the ring is a plain function
(:func:`run_authoring_ring`) parameterized by a tiny backend seam — a write client, a
**second** write client (the out-of-band editor), and a ``download`` callable returning
``(markdown, tree, revision)``:

* ``tests/test_live_write_authoring_gate.py`` binds it to **real Lark** against a doc it
  self-provisions and destroys — that run is **the binding gate**;
* ``tests/test_live_write_authoring_gate_offline.py`` binds it to the shared fake-Lark
  document doubles (``guide_recipes``) — so the ring's logic, assertions and evidence are
  exercised on every offline run, and the live run adds the one thing a double cannot: real
  Lark.

Both call the same code, so the two cannot drift: a change that breaks the ring reddens
offline **before** it burns a live run.

**The fragment is CANONICAL.** :data:`FRAGMENT` is written in the reader's own dialect (tier
A of the LD-136 round-trip property), covers **every** creatable kind — heading, paragraph,
bullet, ordered, todo (the list kinds NESTED), code, quote, table — and carries the
escaped-metachar cases (a leading ``\\#``, an inline ``\\*\\*``, a table cell's ``\\|``), so
the round-trip proves **escaping survives authoring**. Canonical means the expected Markdown
is the fragment **byte-identically**: there is no normalization to hand-wave over.
"""
import difflib
from typing import List, Tuple

from compose_roundtrip import reader_markdown

from larkdocio.write import (
    Anchor,
    AnchorById,
    DeleteRequest,
    InsertPosition,
    InsertRequest,
    RefusalReason,
    apply,
    compose,
    dry_run,
)
from larkdocio.errors import LarkApplyRefusedError
from larkdocio.write.client import text_block
from larkdocio.write.encode import encode_content

#: Unique, greppable token every line the gate authors carries, so every assertion is exact
#: and a stray leftover in a document is attributable.
SUFFIX = "s7gate-4d1f9c2b"

#: The seed paragraph the fragment is anchored AFTER. It is the gate's own baseline content
#: (a self-provisioned doc starts empty), and it doubles as the region delimiter: everything
#: after this line in the re-downloaded Markdown is the authored region.
ANCHOR_LINE = f"anchor paragraph for the authoring gate :: {SUFFIX}"

#: The out-of-band editor's line (the concurrency arm). Inserted at index 0 — **above** the
#: anchor, deliberately NOT touching the anchored block — which is exactly the drift
#: ``STALE_ANCHOR`` is structurally blind to and ``STALE_DOCUMENT`` exists to catch.
OUT_OF_BAND_LINE = f"inserted out of band by somebody else :: {SUFFIX}"

#: THE FRAGMENT (AC2 + the amplifier). Every creatable kind, lists nested, escaped
#: metacharacters, and **canonical** — see the module docstring.
FRAGMENT = (
    f"## Authoring gate :: {SUFFIX}\n"
    "\n"
    "Composed prose with an \\*\\*escaped\\*\\* marker.\n"
    "\n"
    "\\# not a heading and \\*\\*not bold\\*\\*\n"
    "\n"
    "- top bullet\n"
    "\t- nested bullet\n"
    "\n"
    "1. first step\n"
    "\n"
    "2. second step\n"
    "\n"
    "- [x] done task\n"
    "\t- [ ] nested open task\n"
    "\n"
    "```python\n"
    "x = 1\n"
    "```\n"
    "\n"
    # LD-192 — the diagram kind. A type-40 add_ons block is the one creatable kind whose
    # payload is not text elements, so the binding write gate covers it too: the fragment is
    # projected off the CLOSED kind enum, and a kind this gate never authors would be a kind
    # the live round-trip never proves. Placed BEFORE the quote deliberately — the quote must
    # stay adjacent to the table, because the blank line between them is the quote's own
    # documented projection normalization.
    "```mermaid\n"
    "flowchart TD\n"
    "    A[\"Draft\"] --> B[\"Shipped\"]\n"
    "```\n"
    "\n"
    "> quoted conclusion\n"
    "\n"
    "\n"
    "| Metric | Value |\n|---|---|\n| a \\| b | 97.2% |\n"
)


# --------------------------------------------------------------------------- #
# The two measurements the gate rests on — the equivalence and the differ.      #
# Both are unit-tested against fixtures (including inputs that must make them    #
# FAIL) before the live gate trusts them.                                       #
# --------------------------------------------------------------------------- #

def expected_region() -> str:
    """The Markdown the reader must emit for the authored fragment — **computed**, via the
    shipped encoder + parser + renderer (the LD-136 doc-double), never hand-copied.

    This is the D4 property's own statement of the round-trip. Because :data:`FRAGMENT` is
    canonical it equals the fragment byte-identically, which is what lets the live gate
    assert equality against the fragment itself; computing it anyway means a reader change
    that altered the emission reddens the gate instead of being absorbed by a stale literal.
    """
    return reader_markdown(compose(FRAGMENT))


def authored_region(markdown: str, *, after: str = ANCHOR_LINE) -> str:
    """The authored region of a downloaded document: everything after the ``after`` line.

    The anchor line must appear **exactly once** (a second match would silently slice the
    wrong region, so it raises). The document **wrapper** — the page's leading blank line and
    the trailing child separator — is normalized away, because those belong to the document
    rather than to the authored fragment; **interior** blank lines are left exactly as the
    renderer emitted them (they are part of the dialect: a table, like a quote, carries its
    own trailing blank line, which is why the canonical fragment has two).
    """
    lines = markdown.splitlines()
    hits = [i for i, line in enumerate(lines) if after in line]
    assert len(hits) == 1, (
        f"expected exactly one line carrying {after!r} to delimit the authored region; "
        f"got {hits}")
    body = "\n".join(lines[hits[0] + 1:]).strip("\n")
    return body + "\n" if body else ""


def full_document_diff(before: str, after: str) -> Tuple[List[str], List[str]]:
    """``(added, removed)`` — a **whole-document** line diff of two downloads.

    A region diff cannot prove AC3: an insert changes the block count, so the only way to
    show "everything else is byte-identical" is to diff the entire document and require the
    ``removed`` side to be empty. A changed line shows up on **both** sides, so an empty
    ``removed`` really does mean nothing outside the authored region moved.
    """
    delta = list(difflib.ndiff(before.splitlines(), after.splitlines()))
    return ([line[2:] for line in delta if line.startswith("+ ")],
            [line[2:] for line in delta if line.startswith("- ")])


def top_level_created_ids(content, created_block_ids) -> List[str]:
    """The **top-level** ids among the ones ``apply`` returned for an authored fragment.

    ``ApplyLogEntry.created_block_ids`` is the flat **pre-order** list of every created
    block, nested children included. Deleting a top-level block takes its subtree with it, so
    the restore addresses only the roots — and which entries are roots is read off the
    **real** encoder (``encode_content(...).parent is None``), never counted by hand.
    """
    encoded = encode_content(tuple(content))
    assert len(encoded) == len(created_block_ids), (
        f"apply() returned {len(created_block_ids)} created ids for {len(encoded)} encoded "
        f"blocks — the pre-order correspondence the restore relies on is broken")
    return [bid for bid, child in zip(created_block_ids, encoded) if child.parent is None]


# --------------------------------------------------------------------------- #
# The call spy — the ZERO-WRITES measurement, portable across both backends.    #
# --------------------------------------------------------------------------- #

#: Every client method that MUTATES the document. ``apply``'s only route to Lark is these
#: methods, so "no write method was called" is what zero writes issued means here.
WRITE_METHODS = frozenset({
    "create_children", "_patch_block", "batch_update_blocks", "batch_delete",
    "create_document", "delete_document",
})
#: Every client method that only READS. Listed explicitly so an unknown method name is a
#: hard failure rather than a silently uncounted call (the LD-139 routing-spy lesson: a
#: double that cannot classify a call cannot prove anything about it).
READ_METHODS = frozenset({"get_block", "get_document", "read_document_revision",
                          "list_document_blocks"})


class CallSpy:
    """A pass-through proxy over a write client that RECORDS every call ``apply`` makes.

    Used to measure the concurrency arm's headline claim — a ``STALE_DOCUMENT`` refusal
    issues **ZERO writes** — as a *measurement* rather than an inference from the apply-log
    (which is exactly the entity under test). It is a proxy, so the calls that do happen go
    to the real client and hit the real API: the gate is not weakened by the spy.

    The classification is total: an unrecognized method name raises, so a future engine that
    reached Lark through a new call would redden here rather than pass uncounted.
    """

    def __init__(self, client):
        self._client = client
        self.calls: List[str] = []

    def __getattr__(self, name):
        attribute = getattr(self._client, name)
        if not callable(attribute):
            return attribute
        assert name in WRITE_METHODS or name in READ_METHODS, (
            f"the apply engine called {name!r}, which the gate's spy cannot classify as a "
            f"read or a write — the zero-writes measurement would silently miss it")

        def recording(*args, **kwargs):
            self.calls.append(name)
            return attribute(*args, **kwargs)

        return recording

    @property
    def writes(self) -> List[str]:
        return [name for name in self.calls if name in WRITE_METHODS]

    @property
    def reads(self) -> List[str]:
        return [name for name in self.calls if name in READ_METHODS]


# --------------------------------------------------------------------------- #
# THE RING — one implementation, two backends (real Lark / the fake-Lark doubles).#
# --------------------------------------------------------------------------- #

def _insert_the_fragment():
    """The authoring request: the composed fragment, anchored AFTER the seed paragraph.

    Quote-anchored, because that is the only anchor a consumer has before anything exists —
    the by-id half of the loop is exercised by the restore, which deletes the blocks by the
    ids ``apply`` just handed back (LD-137).
    """
    return InsertRequest(
        reference=Anchor(quote=ANCHOR_LINE),
        position=InsertPosition.AFTER,
        content=compose(FRAGMENT),
    )


def run_authoring_ring(*, write_client, second_write_client, download, document_id) -> dict:
    """Run THE AUTHORING GATE's ring against one backend; return the evidence dict.

    The backend seam is three objects: ``write_client`` (the engine's client),
    ``second_write_client`` (a genuinely **separate** client — the out-of-band editor), and
    ``download(document_id) -> (markdown, tree, revision)``. The document must already exist
    and hold :data:`ANCHOR_LINE` as its own top-level paragraph.

    The ring, in order — every step asserted here so both backends are held to the same bar:

    1. **the determinism control** — two downloads of the unchanged document are
       byte-identical, which is what makes every later diff attributable to a write, and the
       revision is stable across reads (a read must not bump it, or an armed batch could
       never apply);
    2. **THE ROUND-TRIP ARM (AC2)** — ``compose(FRAGMENT)`` → ``dry_run`` **armed** with the
       document's revision → ``apply`` → re-download → the authored region is the **same
       Markdown**, byte-identically, and equals the LD-136 property's own prediction;
    3. **surgical (AC3)** — the **whole-document** diff removed nothing: only the authored
       lines appeared;
    4. **the restore** — the authored blocks are deleted **by the ids apply returned**
       (LD-137) and the document is byte-identical to its baseline again;
    5. **THE CONCURRENCY ARM (AC3b)** — an armed plan, then an out-of-band insert **above**
       the anchor via the second client (deliberately not touching the anchored block, so
       ``STALE_ANCHOR`` is blind to it), then ``apply`` → ``STALE_DOCUMENT``, **zero writes
       measured at the client boundary**, the document unchanged by the refused batch, the
       anchor still matching (so the refusal is the DOCUMENT guard's), and finally a
       **re-plan that applies** — a recoverable refusal, not a dead end.
    """
    evidence: dict = {"document_id": document_id, "fragment": FRAGMENT}

    # 1) BASELINE + the determinism control.
    md_baseline, tree_baseline, revision = download(document_id)
    md_baseline_2, _, revision_2 = download(document_id)
    assert md_baseline == md_baseline_2, (
        "reader is non-deterministic: two downloads of the unchanged document differ, so no "
        "later diff would be attributable to a write")
    assert revision == revision_2, (
        f"the document revision moved across two READS ({revision!r} → {revision_2!r}) — a "
        f"read must be inert or no armed batch could ever apply")
    assert ANCHOR_LINE in md_baseline, "the document must carry the gate's seed anchor line"
    assert authored_region(md_baseline) == "", (
        "the baseline already carries content after the anchor — the round-trip equality "
        "could then pass without anything being authored")
    evidence["baseline_revision"] = revision

    # 2) THE ROUND-TRIP ARM — armed with the revision the READER handed back for free.
    plan = dry_run([_insert_the_fragment()], tree_baseline, document_revision_id=revision)
    assert not plan.refusals, f"dry-run refused the authoring insert: {plan.refusals!r}"
    evidence["revision_guard"] = plan.revision_guard
    assert plan.revision_guard == "active", (
        f"the plan's whole-document guard is {plan.revision_guard!r}, not active — the "
        f"reader's revision_id did not arm it, so the concurrency arm could prove nothing: "
        f"{plan.revision_guard_detail}")

    spy = CallSpy(write_client)
    log = apply(plan, spy, document_id)
    (entry,) = log.entries
    assert entry.outcome == "inserted", entry.to_dict()
    created = list(entry.created_block_ids)
    assert created and all(created), (
        f"apply() must return one id per authored block: {created!r}")
    evidence["created_block_ids"] = created
    evidence["apply_log_revision_guard"] = log.revision_guard
    evidence["round_trip_writes"] = len(spy.writes)

    md_authored, tree_authored, revision_authored = download(document_id)
    region = authored_region(md_authored)
    evidence["authored_region"] = region
    evidence["expected_region"] = expected_region()
    evidence["round_trip_equal"] = region == FRAGMENT
    assert region == FRAGMENT, (
        "THE ROUND-TRIP FAILED — the authored region is not the Markdown that was "
        f"composed.\n--- composed ---\n{FRAGMENT}--- read back ---\n{region}")
    assert region == expected_region(), (
        "the authored region does not match the LD-136 property's own prediction "
        "(reader_markdown(compose(fragment))) — the live document and the offline "
        "doc-double disagree about what the reader emits")

    # 3) SURGICAL — the FULL-document diff (an insert changes the block count, so a region
    #    diff could not show that everything else stayed byte-identical).
    added, removed = full_document_diff(md_baseline, md_authored)
    evidence["added_lines_after_insert"] = len(added)
    evidence["removed_lines_after_insert"] = removed
    assert removed == [], f"the authoring insert was not purely additive; lost: {removed}"

    # 4) THE RESTORE — delete the authored blocks BY THE IDS apply RETURNED (LD-137).
    roots = top_level_created_ids(plan.entries[0].content, created)
    evidence["top_level_created_ids"] = roots
    delete_plan = dry_run([DeleteRequest(target=AnchorById(block_id=block_id))
                           for block_id in roots],
                          tree_authored, document_revision_id=revision_authored)
    assert not delete_plan.refusals, (
        f"the by-id restore refused at dry-run: {delete_plan.refusals!r}")
    delete_log = apply(delete_plan, write_client, document_id)
    outcomes = [e.outcome for e in delete_log.entries]
    evidence["restore_outcomes"] = outcomes
    assert outcomes == ["deleted"] * len(roots), [
        e.to_dict() for e in delete_log.entries if e.outcome != "deleted"]

    md_restored, tree_restored, revision_restored = download(document_id)
    evidence["restored_byte_identical"] = md_restored == md_baseline
    assert md_restored == md_baseline, (
        "the by-id restore did not return the document to its baseline "
        f"byte-identically.\n--- baseline ---\n{md_baseline}--- restored ---\n{md_restored}")

    # 5) THE CONCURRENCY ARM (AC3b / D9). The tree + revision come from the read that just
    #    verified the restore — one read, exactly as a consumer would re-plan.
    armed = dry_run([_insert_the_fragment()], tree_restored,
                    document_revision_id=revision_restored)
    assert not armed.refusals, f"the armed plan refused at dry-run: {armed.refusals!r}"
    evidence["armed_revision_guard"] = armed.revision_guard
    assert armed.revision_guard == "active"
    anchor_block_id = armed.resolved[0].block_id

    # …the out-of-band edit, AFTER the dry-run (the exact race D9 targets), from a SECOND
    # client path, at index 0 — ABOVE the anchor, deliberately not touching the anchored
    # block, which is precisely the drift STALE_ANCHOR is structurally blind to.
    second_write_client.create_children(
        document_id, document_id, [text_block(OUT_OF_BAND_LINE)], index=0)
    md_drifted, _, revision_drifted = download(document_id)
    evidence["out_of_band_landed"] = OUT_OF_BAND_LINE in md_drifted
    evidence["revision_advanced"] = revision_drifted != revision_restored
    evidence["revisions"] = {"planned": revision_restored, "live": revision_drifted}
    assert evidence["out_of_band_landed"], "the out-of-band edit did not land"
    assert evidence["revision_advanced"], (
        f"the out-of-band write did not advance the document revision "
        f"({revision_restored!r} → {revision_drifted!r}) — there is no drift to refuse")

    refusal_spy = CallSpy(write_client)
    # LD-458 — the default is a RAISE: a batch the document guard refuses no longer comes
    # back as a return value a caller can discard. The whole log rides on the exception.
    try:
        apply(armed, refusal_spy, document_id)
        raise AssertionError(
            "a stale-document batch must RAISE LarkApplyRefusedError, not return a log")
    except LarkApplyRefusedError as refused:
        refused_log = refused.log
        evidence["refusal_raised"] = type(refused).__name__
        evidence["refusal_message"] = str(refused)
    evidence["refused_writes"] = refusal_spy.writes
    evidence["refused_calls"] = refusal_spy.calls
    (refused_entry,) = refused_log.entries
    assert refused_entry.outcome == "refused", refused_entry.to_dict()
    assert refused_entry.refusal.reason is RefusalReason.STALE_DOCUMENT, (
        refused_entry.to_dict())
    evidence["stale_document_reason"] = refused_entry.refusal.reason.value
    evidence["stale_document_detail"] = refused_entry.refusal.detail
    evidence["refused_log_revision_guard"] = refused_log.revision_guard
    assert str(revision_restored) in refused_entry.refusal.detail
    assert str(revision_drifted) in refused_entry.refusal.detail, (
        "the mandatory detail must name BOTH revisions so a consumer can log the drift")
    # ZERO writes, measured: a refusal costs exactly ONE call, the document-meta read.
    assert refusal_spy.writes == [], (
        f"a STALE_DOCUMENT refusal issued writes: {refusal_spy.writes}")
    assert refusal_spy.calls == ["read_document_revision"], (
        f"a refused batch must cost exactly one call (the document meta read); got "
        f"{refusal_spy.calls}")

    # …and the document is byte-unchanged BY THE REFUSED BATCH: the only difference from the
    # pre-arm download is the out-of-band line itself.
    md_after_refusal, tree_after_refusal, revision_after_refusal = download(document_id)
    added_after, removed_after = full_document_diff(md_drifted, md_after_refusal)
    evidence["byte_unchanged_by_the_refused_batch"] = md_after_refusal == md_drifted
    assert md_after_refusal == md_drifted, (
        "the refused batch CHANGED the document — zero writes did not hold")
    assert (added_after, removed_after) == ([], [])
    assert authored_region(md_after_refusal) == "", (
        "the refused batch landed authored content — the whole-batch refusal did not hold")

    # …the refusal is attributable to the DOCUMENT guard alone: the anchored block still
    # matches its own precondition, so STALE_ANCHOR would have let this batch through.
    live_anchor = write_client.get_block(document_id, anchor_block_id)
    live_text = "".join(
        element["text_run"].get("content", "")
        for value in live_anchor.values()
        if isinstance(value, dict) and isinstance(value.get("elements"), list)
        for element in value["elements"] if element.get("text_run") is not None)
    evidence["anchor_still_matched_at_refusal"] = live_text == ANCHOR_LINE
    assert live_text == ANCHOR_LINE, (
        f"the out-of-band edit touched the anchored block ({live_text!r}) — then "
        f"STALE_ANCHOR could have caused the refusal and the arm proves nothing about "
        f"STALE_DOCUMENT")

    # …RE-PLAN: the refusal is RECOVERABLE, not a dead end.
    replan = dry_run([_insert_the_fragment()], tree_after_refusal,
                     document_revision_id=revision_after_refusal)
    assert not replan.refusals, f"the re-plan refused at dry-run: {replan.refusals!r}"
    replan_log = apply(replan, write_client, document_id)
    (replan_entry,) = replan_log.entries
    evidence["replan_outcome"] = replan_entry.outcome
    evidence["replan_revision_guard"] = replan_log.revision_guard
    assert replan_entry.outcome == "inserted", replan_entry.to_dict()

    md_replanned, _, _ = download(document_id)
    replanned_region = authored_region(md_replanned)
    evidence["replan_round_trip_equal"] = replanned_region == FRAGMENT
    assert replanned_region == FRAGMENT, (
        "the re-planned apply did not round-trip to the same Markdown")
    _, removed_replan = full_document_diff(md_drifted, md_replanned)
    assert removed_replan == [], (
        f"the re-planned apply was not purely additive; lost: {removed_replan}")

    return evidence


def authoring_teardown(write_client, download, document_id) -> dict:
    """Empty the document's top level and verify NOTHING the gate authored survives.

    Idempotent by construction — the child range comes off the **live** root rather than a
    count held in the test, so a second call finds zero children and issues no write at all
    (the amplifier's idempotent-teardown assertion). Trashing the document itself is
    best-effort and only attempted when the backend has ``delete_document`` (a fake-Lark
    double has no document to trash), so the one teardown implementation covers both
    backends and the live gate's ``finally``.
    """
    result: dict = {"children_removed": 0, "emptied": False, "deleted": None}
    children = write_client.get_block(document_id, document_id).get("children") or []
    if children:
        write_client.batch_delete(document_id, document_id, 0, len(children))
        result["children_removed"] = len(children)

    markdown = download(document_id)[0]
    result["emptied"] = not any(
        token in markdown for token in (SUFFIX, ANCHOR_LINE, OUT_OF_BAND_LINE))

    trash = getattr(write_client, "delete_document", None)
    if trash is None:
        result["deleted"] = "unsupported by this backend"
    else:
        try:
            response = trash(document_id)
            result["deleted"] = (response.get("code") if isinstance(response, dict)
                                 else "ok")
        except Exception as exc:      # noqa: BLE001 — teardown is best-effort by design
            result["deleted"] = f"skipped ({exc})"
    return result
