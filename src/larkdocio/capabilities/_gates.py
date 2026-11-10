"""Gate coverage — where each contract is proved LIVE against the real API.

LD-244: the verbatim pre-split slice, lines 1955-2243 of the
2,770-line ``capabilities.py``. Nothing in it was rewritten.

LD-260 adds the two Base rings; each function below says what its ring proves and why the
surfaces without one claim nothing.
"""
from larkdocio.common.auth import READ_ENV, WRITE_ENV

from ._contracts import APPLY_LOG_COMPLETE
from ._models import GateCoverage, GateMember


def _docx_write_gate_coverage() -> GateCoverage:
    """The docx-write **live gate ring** (LD-140 AC6) — one member per gate module.

    Hand-authored where no registry exists (a test tree is not importable from the package),
    but **not unguarded**: ``tests/test_capabilities.py`` joins this list to the test tree
    bidirectionally — every module named here must exist and carry the ``live_write`` marker,
    and every marked ``tests/test_live_write_*`` module must appear here exactly once. So a
    gate cannot ship undiscoverable (an orphan), a row cannot outlive its gate, and every
    safety contract this surface claims must be named by at least one member.
    """
    return GateCoverage(
        marker="live_write",
        command="LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-NNN pytest -m live_write",
        credentials_env=list(WRITE_ENV),
        target_policy=(
            "Every member that WRITES self-provisions the document it writes to via "
            "create_document and trashes it in a finally — never the read canary, never the "
            "block-zoo doc, never a real document. Deselected by default; skips LOUDLY (never "
            "silently passes) when the WRITE credentials are absent. ONE member writes nothing "
            "and carries its own marker: the reviewer-anchor arm needs a document that already "
            "has inline comment anchors, which no disposable can be given (Lark has no "
            "anchored-comment create), so it READS such a document and proves the plan-time "
            "refusal with a transport that raises on contact. It needs read credentials only "
            "and touches nothing it did not read."
        ),
        members=[
            GateMember(
                id="w0-harness",
                module="tests/test_live_write_harness.py",
                summary=(
                    "The transport round-trip below the plan gate: prove the destination rule "
                    "on the live client (a create naming no destination refuses locally and "
                    "sends nothing), then create a baseline (incl. a bold sentinel) in the "
                    "caller-supplied folder, download twice for the byte-identity determinism "
                    "control, one surgical get_block/_patch_block mutation, re-download and "
                    "diff, teardown."
                ),
                proves_contracts=["caller-supplied-destination"],
            ),
            GateMember(
                id="w1-narrative",
                module="tests/test_live_write_w1_gate.py",
                summary=(
                    "The narrative apply engine end to end — EditRequest → resolve → dry_run → "
                    "apply against a live paragraph; the diff proves exactly one Markdown line "
                    "changed and the paragraph kept its bold style."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory"],
            ),
            GateMember(
                id="w2-table-cell",
                module="tests/test_live_write_w2_gate.py",
                summary=(
                    "The table-cell round-trip: a TableLocator EditRequest through the same "
                    "pipeline (via the double re-validation); only the target cell's row line "
                    "changed and the row identity held."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory"],
            ),
            GateMember(
                id="w3-insert-delete-subspan",
                module="tests/test_live_write_w3_gate.py",
                summary=(
                    "Insert / delete / sub-span, whose surgical proof needs a whole-document "
                    "diff (the block count changes): only the inserted block appeared, only the "
                    "deleted one disappeared (with its removed payload captured), only the "
                    "span's line changed with surrounding run styles preserved."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory"],
            ),
            GateMember(
                id="roundtrip-verb",
                module="tests/test_live_write_roundtrip_verb_gate.py",
                summary=(
                    "The file-first round trip AS THE SHIPPED VERB, across a real process "
                    "boundary: pull a live document to two files, edit the Markdown ON DISK, "
                    "push it back. A push without --apply is proved to write NOTHING (writes "
                    "counted at the client boundary AND the document re-read against its "
                    "baseline); the applied push is proved surgical by an independent diff, "
                    "and the verb's OWN compose-equivalence read-back is proved to have "
                    "verified something rather than nothing. The disposable is created into "
                    "the caller-supplied disposables folder, named explicitly."
                ),
                proves_contracts=[
                    "plan-gated", "dry-run-mandatory", "caller-supplied-destination",
                ],
            ),
            GateMember(
                id="table-create",
                module="tests/test_live_write_table_create_gate.py",
                summary=(
                    "Table CREATION live: an R×C grid authored through the two-step "
                    "create — Lark auto-provisions the cell family from the grid property and "
                    "the engine fills each authored cell — then read back as a Markdown table "
                    "and immediately edited as a first-class target."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory"],
            ),
            GateMember(
                id="table-growth",
                module="tests/test_live_write_table_growth_gate.py",
                summary=(
                    "A table PAST the create endpoint's per-axis grid ceiling, authored from "
                    "Markdown: two grids that each exceed it on a different axis are composed, "
                    "planned and applied, then re-downloaded through the reader — the round "
                    "trip is the verdict, and the live row_size / column_size are asserted so "
                    "a grid created short cannot pass on Markdown alone. The write is proved "
                    "purely additive. AND, in the same module, a SECOND live arm for the "
                    "shipped grow operation: a GrowTableRequest appends a row through "
                    "the plan gate on a disposable this arm creates and destroys, every "
                    "pre-existing cell id is re-read and asserted still present in the same "
                    "order with the table's own block id unchanged, and a mid-table insertion "
                    "is asserted to refuse typed (table-grow-unsupported). So the newest "
                    "docx-write op carries live coverage here, not only in the create path."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory"],
            ),
            GateMember(
                id="table-batched-fill",
                module="tests/test_live_write_batched_table_fill_gate.py",
                summary=(
                    "A 216-cell table (6 columns × 36 rows) authored from Markdown, with "
                    "every HTTP request the write client issues COUNTED on the wire: the "
                    "run is bounded at 60 API calls and 21 MUTATING calls for those 216 "
                    "cells, where the per-cell fill spent 463. The bound is on the COST, not "
                    "on which endpoint family carries the cells — the one-call descendant "
                    "route's shape is the table-one-call gate's own claim. The verdict is a "
                    "fresh read-back — live row_size / "
                    "column_size, 216 cells, and ROW-MAJOR cell order at four fixed probe "
                    "points, so a transposed fill cannot pass on cell count alone. Elapsed "
                    "time is recorded as evidence and gates nothing. The write is proved "
                    "purely additive."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory"],
            ),
            GateMember(
                id="table-one-call",
                module="tests/test_live_write_one_call_table_gate.py",
                summary=(
                    "The same 216-cell table authored as ONE atomic subtree call, inside a "
                    "MIXED batch: the paragraph insert and the table insert each land beside "
                    "their OWN anchor, read off the live child order rather than the rendered "
                    "Markdown, and the table costs exactly one call with no grow or fill "
                    "PATCH behind it. The verdict is a fresh read-back — live row_size / "
                    "column_size, 216 cells, ROW-MAJOR order at the same four probe points — "
                    "and a second leg proves atomicity: a subtree ONE cell past the measured "
                    "envelope is refused and the document is read back to show nothing was "
                    "created, with a passing control one cell inside it. The write is proved "
                    "purely additive."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory"],
            ),
            GateMember(
                id="anchor-by-id",
                module="tests/test_live_write_anchor_by_id_gate.py",
                summary=(
                    "By-id anchoring live: author, take created_block_ids back, insert "
                    "AFTER a returned id, delete by id (removed payload captured), plus the two "
                    "staleness arms only a real document can prove — a concurrent rewrite of "
                    "the anchored block, and a plan applied after that block was deleted. Plus "
                    "the ONE-TREE-ONE-BATCH arm: a two-request batch that queues an insert and "
                    "then anchors on the text that insert would create refuses not-found on a "
                    "REAL tree, with the intra-batch cause and the commit-then-anchor recovery "
                    "in the detail — the shape whose 'commit, then anchor by created_block_ids' "
                    "recovery the rest of this member proves live."
                ),
                proves_contracts=[
                    "plan-gated", "dry-run-mandatory", "STALE_ANCHOR",
                    "exactly-one-or-refuse", "one-tree-one-batch",
                ],
                arms=["by-id-insert", "by-id-delete", "compare-and-swap", "stale-race",
                      "vanished-id", "intra-batch-refusal"],
            ),
            GateMember(
                id="authoring-round-trip",
                module="tests/test_live_write_authoring_gate.py",
                summary=(
                    "THE AUTHORING GATE. Round-trip arm: a multi-block Markdown fragment "
                    "covering EVERY creatable kind (heading, paragraph, nested bullet / ordered "
                    "/ todo lists, code, quote, table) plus escaped metacharacters is composed, "
                    "applied, and re-downloaded through the shipped reader as BYTE-IDENTICALLY "
                    "the same Markdown (the round-trip property, live), the whole-document "
                    "diff proves "
                    "only the authored lines appeared, and the blocks are then deleted by the "
                    "ids apply returned until the document is byte-identical to its baseline. "
                    "Concurrency arm: an armed plan, a real out-of-band edit from a SECOND "
                    "client that deliberately does not touch the anchored block (so STALE_ANCHOR "
                    "is blind to it), then apply → STALE_DOCUMENT with ZERO writes measured at "
                    "the client boundary, the document byte-unchanged, and a re-plan that "
                    "applies — a recoverable refusal, not a dead end."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory", "STALE_DOCUMENT"],
                arms=["authoring-round-trip", "STALE_DOCUMENT-concurrency"],
            ),
            GateMember(
                id="comment-anchor-zoo-arm",
                module="tests/test_live_comment_anchor_zoo_arm.py",
                marker="live",
                summary=(
                    "THE REVIEWER-ANCHOR ARM — live and READ-ONLY, and the strongest arm this "
                    "contract admits. Lark has no anchored-comment create on either surface "
                    "(proved across 18 candidate routes, re-confirmed by a later run), so a "
                    "self-provisioned disposable CANNOT be given an inline anchor and no write "
                    "gate can set up its own subject. This member instead reads a document that "
                    "already carries real ones and drives the plan-time half against it: a "
                    "whole-block edit of a really-anchored block refuses "
                    "comment-anchors-present naming the real ids, and the apply engine is wired "
                    "to a transport that RAISES ON CONTACT — so the zero-write proof is "
                    "structural rather than trusted, and a refusal that failed to fire errors "
                    "instead of writing. It needs read credentials only and writes nothing, "
                    "which is why it runs under the read marker rather than the ring's."
                ),
                proves_contracts=["comment-anchors-honored-or-refused",
                                  "exactly-one-or-refuse"],
                arms=["whole-block-refusal-live", "zero-write-structural"],
            ),
            GateMember(
                id="comment-op-round-trip",
                module="tests/test_live_write_comment_op_gate.py",
                summary=(
                    "THE COMMENT WRITE OPS, end to end on a self-provisioned disposable, "
                    "twice: create a document, plan and apply a whole-document comment, then "
                    "READ IT BACK through the shipped comments reader and assert what was "
                    "actually made rather than inferring success from code 0 — the listing "
                    "reports is_whole=True and quote=None, and the author id matches the one "
                    "the apply-log disclosed. Then remove it through the shipped op and prove "
                    "it is GONE by re-reading (the comment absent from the listing), not by "
                    "trusting a return code. Two arms run without writing anything: an "
                    "anchored create and a spreadsheet create are both refused at plan time "
                    "with a client wired to a transport that RAISES ON CONTACT, so "
                    "zero-API-calls is structural. Closes out by trashing the disposable and "
                    "verifying by re-fetch that it is really gone."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory",
                                  "comment-create-whole-document-only",
                                  "comment-removal-sole-author-or-refuse"],
                arms=["create-and-read-back", "cascade-removal-verified-gone",
                      "anchored-refused-zero-calls", "sheets-refused-zero-calls",
                      "zero-orphan-close-out"],
            ),
            # LD-236 — THE ROUND-TRIP RING. Four members rather than one,
            # because each proves a different invariant and a failure should name it.
            GateMember(
                id="round-trip-surgical",
                module="tests/test_live_write_round_trip_surgical_gate.py",
                summary=(
                    "THE ROUND TRIP, SURGICAL. Download → project the document to Markdown "
                    "carrying one identity marker per block → edit one block's text in the "
                    "projection → reconcile → compile → apply → re-download and diff: only the "
                    "target region changed and every other line is byte-identical, measured as "
                    "ONE patch at the client boundary. The same chain in reverse then restores "
                    "the document to a byte-identical baseline — the claim 'surgical' actually "
                    "makes, which is that the trip leaves no residue."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory"],
                arms=["surgical-diff", "restore-to-baseline"],
            ),
            GateMember(
                id="round-trip-conservation",
                module="tests/test_live_write_round_trip_conservation_gate.py",
                summary=(
                    "CONSERVATION, LIVE — the arm that catches the catastrophe the projection's "
                    "design exists to prevent. A block the dialect cannot express (a TABLE: "
                    "opaque to the projection AND creatable by compose(), so both omission "
                    "shapes reach the reconciler) is omitted from the edited projection two "
                    "ways. Marker AND content omitted: the block is conserved — never edited, "
                    "never deleted, never re-created — and comes back byte-identical beside an "
                    "edit that did land. Marker omitted with the CONTENT KEPT: the whole batch "
                    "refuses conserved-block-re-created with zero writes, so a plan that would "
                    "have left the document holding the block twice is refused rather than "
                    "applied, and the live document is byte-unchanged."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory"],
                arms=["marker-and-content-omitted", "marker-omitted-content-kept"],
            ),
            GateMember(
                id="round-trip-stale-document",
                module="tests/test_live_write_round_trip_stale_document_gate.py",
                summary=(
                    "STALE_DOCUMENT ON THE RECONCILIATION PATH, live and RECOVERABLE. A "
                    "reconciliation planned against the document as read, a real out-of-band "
                    "edit from a SECOND client that deliberately leaves the planned block "
                    "alone (so STALE_ANCHOR is blind to it), then apply → the whole batch "
                    "refuses with zero writes MEASURED at the client boundary and the document "
                    "byte-unchanged — followed by a re-download, re-project, re-plan that "
                    "applies. Only a real document can prove it: the guard compares a "
                    "revision_id Lark itself advances."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory", "STALE_DOCUMENT"],
                arms=["whole-batch-refusal-zero-writes", "re-plan-proceeds"],
            ),
            GateMember(
                id="round-trip-no-marker",
                module="tests/test_live_write_round_trip_no_marker_gate.py",
                summary=(
                    "NO MARKER REACHES LARK — the invariant with no natural barrier, since "
                    "Lark stores marker-shaped text verbatim (measured live against a "
                    "disposable before this ring was written). "
                    "After a reconciliation the WHOLE re-read document is scanned in BOTH "
                    "representations — the raw stored block payload and the reader's "
                    "re-rendered Markdown — for every identifier the projection emitted, and "
                    "finds zero. An adversarial control whose legitimate prose is "
                    "marker-shaped (a non-emitted identifier, mid-line) survives the round "
                    "trip unchanged, which is what makes the zero a statement about the strip "
                    "rather than about the platform."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory"],
                arms=["two-representation-scan", "adversarial-control-survives"],
            ),
            GateMember(
                id="round-trip-escape-identity",
                module="tests/test_live_write_round_trip_escape_identity_gate.py",
                summary=(
                    "ESCAPE IDENTITY ON AN UNTOUCHED LINE. The projection escapes literal "
                    "text so a document's own marker-shaped prose cannot forge a marker, and "
                    "a fenced code block's body is the one place the authoring dialect will "
                    "NOT decode that again — a backslash inside a fence is a backslash to "
                    "CommonMark itself. A two-line code block is seeded, ONE line is edited "
                    "through the shipped chain, and the document is read back in both "
                    "representations (the reader's Markdown and the raw block payload): the "
                    "line the caller never touched is byte-identical, carrying none of the "
                    "projection's backslashes. The arm carries its own teeth — the PRE-FIX "
                    "compile is re-created in place from the same plan, applied, and asserted "
                    "to really corrupt the untouched line, then repaired through the shipped "
                    "chain and the repair verified. A gate never shown failing on the defect "
                    "it guards is not known to detect it."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory"],
                arms=["untouched-line-byte-identical", "forced-defect-control",
                      "repair-verified"],
            ),
            GateMember(
                id="anchor-soft-return",
                module="tests/test_live_write_anchor_whitespace_gate.py",
                summary=(
                    "THE SOFT RETURN, AND THE TWO THINGS IT BREAKS. Lark stores a literal "
                    "newline INSIDE one text run and the Markdown shows it as an ordinary "
                    "line wrap — an API fact this arm proves on the wire (author it, read the "
                    "block back, assert the newline survived inside ONE block) before "
                    "claiming anything built on it. Then both behaviours: a whole sentence "
                    "copied off the wrapped paragraph refuses not-found with a detail that "
                    "NAMES the block, quotes its stored spelling and offers a fragment that "
                    "does match, with ZERO writes measured at the client boundary; and the "
                    "recipe's OLD line-splice idiom is re-created in place, applied, and "
                    "asserted to really come back with the sentence's ending written twice "
                    "while the plan reported ok — then the same block is repaired through the "
                    "block-safe splice and read back verbatim. A gate never shown failing on "
                    "the defect it guards is not known to detect it, and the whole finding "
                    "here is that the plan was already clean over the garbled one."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory"],
                arms=["soft-return-really-stored", "near-miss-named-zero-writes",
                      "forced-garble-control", "block-safe-repair-verified"],
            ),
            GateMember(
                id="refusal-policy",
                module="tests/test_live_write_refusal_policy_gate.py",
                summary=(
                    "THE REFUSAL POLICY, PROVED OVER THE SAME WRITES. A batch holding one "
                    "entry that refuses — an ambiguous quote, the measured consumer shape — "
                    "is applied TWICE, on two documents this arm creates itself and empties "
                    "in a finally: once by default, where it raises LarkApplyRefusedError "
                    "carrying the whole log, what applied and every refusal's reason and "
                    "detail; and once with allow_partial=True, where it returns that same "
                    "log. Both documents are read back and compared, because the claim the "
                    "ruling rests on is that NOTHING about the writes changed — the applied "
                    "entry landed and stayed landed under the raise (a report, never a "
                    "rollback), the refused one wrote nothing, and the two read-backs are "
                    "identical. An offline suite can prove the raise fires; only a round trip "
                    "can prove it did not move which entries land."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory",
                                  "exactly-one-or-refuse"],
                arms=["raises-by-default", "opt-in-returns-the-same-log",
                      "same-writes-read-back", "applied-entry-not-rolled-back"],
            ),
            GateMember(
                id="todo-done-edit",
                module="tests/test_live_write_todo_done_edit_gate.py",
                summary=(
                    "THE CHECKBOX MOVES, AND ONLY THE CHECKBOX MOVES. A nested todo tree is "
                    "seeded through the plan gate, one parent checkbox is flipped in the "
                    "projection and nothing else, and the RAW block payload is read back and "
                    "compared property by property against the payload taken before the "
                    "write: done moved; the target's own text, align, folded and child list "
                    "did not; the nested child's id, text and state did not. The flip is "
                    "measured at ONE write call, which is what proves a pure flip does not "
                    "rewrite the block's text and flatten a styled item's runs. The reverse "
                    "flip restores the document to a byte-identical baseline. Only a real "
                    "document can prove it: the field mask this op sends was measured "
                    "elsewhere and cited, and a citation is not this library proving its own "
                    "shipped operation."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory"],
                arms=["read-back-of-the-raw-payload", "untouched-properties-by-name",
                      "one-write-no-text-rewrite", "restore-to-baseline"],
            ),
        ],
    )


def _comments_read_gate_coverage() -> GateCoverage:
    """The comments-read surface's live gate — the one ring member that proves this read
    against real Lark.

    Hand-authored for the same reason the write ring's list is (a test tree is not importable
    from the package) and guarded the same way, bidirectionally, against the marked modules on
    disk. The target policy is the strict one: the gate creates the file it comments on and
    destroys it again, so it never touches a document anyone owns.
    """
    return GateCoverage(
        marker="live_write",
        command="LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-NNN pytest -m live_write",
        credentials_env=list(WRITE_ENV),
        target_policy=(
            "The gate self-provisions the document it reads comments from — it creates a "
            "disposable file, puts one comment on it as test scaffolding, reads that comment "
            "back through the shipped surface, removes the comment, and trashes the file in a "
            "finally. It never reads the canary document, never the block zoo, never a "
            "standing scratch file, and never anything it did not create. Deselected by "
            "default; skips LOUDLY (never silently passes) when the credentials are absent. "
            "Note the marker: this is a READ surface, but proving it needs a comment to "
            "exist, and creating one is a write — so it rides the write ring's credentials "
            "and its disposables-only discipline. The comment it creates and removes is made "
            "with the SHIPPED comment calls on the docx-write surface (they were hand-rolled "
            "test scaffolding while comment creation was not a capability; it is one now, so "
            "there is one implementation and this gate exercises it)."
        ),
        members=[
            GateMember(
                id="comments-read-round-trip",
                module="tests/test_live_comments_read_gate.py",
                summary=(
                    "The comments read end to end on a self-provisioned disposable: create "
                    "the file, create one whole-file comment on it, read it back through the "
                    "shipped surface and assert the projection matches what was written "
                    "(author id raw, thread text exact), assert the whole-file scope is "
                    "reported as such by the listing endpoint while the create response did "
                    "not report it at all — the shape asymmetry, live — then remove the "
                    "comment by deleting its only reply, confirm it is gone from the listing, "
                    "and trash the file. Runs twice on two fresh disposables so a clean "
                    "close-out is structural rather than lucky."
                ),
                arms=["read-round-trip", "shape-asymmetry-live", "cascade-removal",
                      "zero-orphan-close-out"],
            ),
        ],
    )


def _base_read_gate_coverage() -> GateCoverage:
    """The Base READ ring — every member landed, every member read-only.

    Declared here for the first time (LD-260 / O6′). LD-251 published this surface and
    deliberately claimed **no** coverage, because the only honest ring at the time was a story
    that had not landed. It has, so the claim is made from real files and bounded to what the
    arms really prove: this is a READ ring, and nothing in it writes. The narrowing parameters'
    ``view_id`` half is deliberately **not** here — proving it needs a view with a saved filter,
    which needs a write, so that arm lives in a write ring and self-provisions its target.

    The target policy is the strict read one, and it is the mirror image of every write ring's:
    the arms read the configured Base and re-read ``table.revision`` afterwards as the proof
    they changed nothing. That Base carries **hand-authored specimens no API route can
    recreate** — a Flow column, a Lookup, an Email — which is why the ring reads a configured
    target instead of self-provisioning one, and why nothing in this ring may ever write to it.
    """
    return GateCoverage(
        marker="live",
        command="pytest -m live",
        credentials_env=list(READ_ENV),
        target_policy=(
            "READ-ONLY, and the read target is the configured Base named by "
            "LARKDOCIO_SCRATCH_BASE. It is read rather than self-provisioned on purpose: it "
            "holds hand-authored specimens the API cannot recreate — a Flow column whose "
            "values no read route returns, a Lookup, an Email — so a disposable could not "
            "stand in for it. Nothing in this ring writes: every op it calls declares that it "
            "does not mutate, each arm asserts that before its first call, and each re-reads "
            "table.revision at the end and requires it to be unmoved. Deselected by default; "
            "skips LOUDLY (never silently passes) when the read credentials or the URL are "
            "absent. Because a human hand-authors those specimens, the canary pins SAME-RUN "
            "byte-identity between two back-to-back reads and commits no cross-time baseline."
        ),
        members=[
            GateMember(
                id="base-read-arm",
                module="tests/test_live_base_read_arm.py",
                summary=(
                    "The whole read client against the real Base: the five read families run "
                    "end to end on live payloads, so the shapes the offline captures pinned "
                    "are re-confirmed against what Lark returns today, and table.revision is "
                    "re-read afterwards as the no-write proof."
                ),
                arms=["five-family-read", "revision-unmoved"],
            ),
            GateMember(
                id="base-canary",
                module="tests/test_live_base_canary.py",
                summary=(
                    "THE L1 GATE for the Base surface: two back-to-back reads of the "
                    "configured Base through the shipped entry points, asserting the Markdown "
                    "is byte-identical across them (same-run determinism), that the Flow "
                    "column renders its absent-with-reason marker rather than a blank, that a "
                    "column the renderer registry does not know is characterized rather than "
                    "guessed at, and that table.revision did not move — a read that changed "
                    "nothing, measured rather than intended."
                ),
                arms=["same-run-byte-identity", "opaque-column-marker",
                      "unregistered-column-characterization", "revision-unmoved"],
            ),
            GateMember(
                id="base-read-raw-values",
                module="tests/test_live_base_read_raw_values.py",
                summary=(
                    "The opt-in raw value view against the real Base: one read with retention "
                    "on, asserting that every retained value is what the transport received "
                    "on that very call (compared against the client's own records, not "
                    "against a fixture), that the compound types — person, link, attachment, "
                    "date, email — arrive as the structures Lark sent rather than as "
                    "anything this library shaped, that the rendered Markdown is unchanged by "
                    "the flag being on, and that table.revision did not move."
                ),
                arms=["raw-is-what-the-transport-received", "render-unchanged-by-the-flag",
                      "revision-unmoved"],
            ),
            GateMember(
                id="base-read-filter",
                module="tests/test_live_base_read_filter.py",
                summary=(
                    "THE DIFFERENTIAL for the narrowing parameters: records/search silently "
                    "ignores a body key it does not recognise, so this arm never reads a "
                    "response code. It compares reads of the same table in the same run — a "
                    "filtered read returning a strict subset with the filter's own predicate "
                    "holding on every row, a filter that can match nothing returning nothing "
                    "rather than the whole table, `or` over two values returning both rows "
                    "where `and` returns none, and a descending sort returning exactly the "
                    "reverse of the ascending one, which is the only order statement that "
                    "holds under any collation. Lark's own 1254016 for a sort on a field that "
                    "does not exist is asserted too: a key the server validates is a key the "
                    "server reads. And table.revision did not move."
                ),
                arms=["filtered-read-is-a-strict-subset", "match-nothing-returns-nothing",
                      "conjunction-changes-the-answer", "sort-desc-reverses-asc",
                      "sort-refusal-1254016", "revision-unmoved"],
            ),
        ],
    )


def _base_write_gate_coverage() -> GateCoverage:
    """The Base record-WRITE ring — the transport arm and the engine gate.

    Two members rather than one, because they prove different things and a failure should name
    which. The transport arm proves the six record families reach a real Base and that their
    bodies **changed something**; the gate proves the engine above them — surgical, refusing on
    a real out-of-band change, and never sending what it refused.
    """
    return GateCoverage(
        marker="live_write",
        command="LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-NNN pytest -m live_write",
        credentials_env=list(WRITE_ENV),
        target_policy=(
            "Every member self-provisions the Base it writes, through the shared harness, and "
            "deletes it in a finally; the harness names no configured target at all, which is "
            "a static guarantee rather than a promise. It never writes the Base named by "
            "LARKDOCIO_SCRATCH_BASE — that one holds hand-authored specimens no API route can "
            "recreate, so writing it would destroy evidence rather than merely be impolite — "
            "and never any Base it did not create. A Base is a drive file, and on this tenant "
            "a freshly created one is not reliably addressable as one for many minutes, so the "
            "teardown spends a short budget and a persistent ledger keeps whatever it could "
            "not land: the last test sweeps the ledger and reports every survivor by token and "
            "title, so a leftover Base is a name in a report rather than a silence. Deselected "
            "by default; skips LOUDLY (never silently passes) when the write credentials are "
            "absent."
        ),
        members=[
            GateMember(
                id="base-write-arm",
                module="tests/test_live_base_write_arm.py",
                summary=(
                    "The transport round-trip below the plan gate: all six record families — "
                    "create, update and delete, each singly and in batch — against a "
                    "self-provisioned Base, every one of them verified by READING THE TABLE "
                    "BACK through the shipped reader rather than by trusting a success code. "
                    "A created record reads back with the value that was sent, an update "
                    "changes it, a batch changes both rows, and both deletes make the rows "
                    "unfetchable."
                ),
                arms=["six-family-round-trip", "call-budget", "ledger-sweep"],
            ),
            GateMember(
                id="base-write-gate",
                module="tests/test_live_base_write_gate.py",
                summary=(
                    "THE ENGINE GATE, three arms. SURGICAL: snapshot a table, edit ONE cell, "
                    "preview, apply, re-read — only that cell moved, and every other cell of "
                    "every other record is byte-identical, measured cell by cell rather than "
                    "asserted; the edit is then reversed and the table is byte-identical to "
                    "its baseline again. STALENESS AGAINST A REAL RACE: a plan is built, a "
                    "SECOND client really writes to the table out of band, and the apply "
                    "refuses stale-base with ZERO writes measured at the client boundary and "
                    "the target cell provably unchanged — followed by a re-read, re-plan and "
                    "re-apply that lands, so the refusal is recoverable rather than a dead "
                    "end. NOTHING REFUSED IS EVER SENT: a plan whose entry the engine refuses "
                    "locally is applied against a write client wired to a transport that "
                    "raises on contact, so zero calls is structural, and the live positive "
                    "control on the same table shows a known-good write DOES move "
                    "table.revision — which is what makes the write-effect oracle's negative "
                    "reading mean anything."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory", "STALE_BASE",
                                  APPLY_LOG_COMPLETE],
                arms=["surgical-diff", "restore-to-baseline", "stale-base-real-race",
                      "re-plan-proceeds", "refused-never-sent", "oracle-positive-control"],
            ),
            GateMember(
                id="base-relational-gate",
                module="tests/test_live_base_relational_gate.py",
                summary=(
                    "THE RELATIONAL GATE, four arms on one self-provisioned Base, in time "
                    "order because each phase needs the one before it. HASH-VERIFIED MEDIA: "
                    "one file is uploaded, attached through the shipped encoder, read back "
                    "and downloaded to an IDENTICAL sha256 — the bytes are compared by "
                    "digest and never inspected, and the token is ledgered because nothing "
                    "purges it. A DELETED TARGET RECORD: a one-way link is proved to keep "
                    "pointing at the record that is gone, rendering the dangling marker "
                    "rather than an id that looks like data, while a two-way link SELF-HEALS "
                    "without anybody writing to it — and the read completes normally, so "
                    "'the record is missing' really is a typed outcome rather than an error. "
                    "A DELETED TARGET TABLE: the source column survives pointing at a table "
                    "that no longer exists, a record search still answers success, and the "
                    "column-level reading of that state is shown to cost ZERO extra calls, "
                    "measured at the client's own counter. RESOLUTION OFF IS BYTE-IDENTICAL: "
                    "two back-to-back reads with resolution off match byte for byte and the "
                    "one with it on differs in the link cells and nowhere else, compared "
                    "cell by cell rather than by looking for a substring."
                ),
                arms=["hash-verified-media", "record-delete-dangling",
                      "table-delete-detector", "resolution-off-byte-identity"],
            ),
        ],
    )


#: The three safety-contract ids this rung is the first to need, imported by the surface
#: assembly so the ring and the surface cannot spell them differently.
DESTRUCTIVE_CONSENT_REQUIRED = "destructive-consent-required"
CROSS_TABLE_LOSS_PREVIEW = "cross-table-loss-preview"
REVISION_GUARD_FIELD_SCOPED_ONLY = "revision-guard-field-scoped-only"


def _base_schema_write_gate_coverage() -> GateCoverage:
    """The Base SCHEMA-write ring — five members, and the only ring whose verbs destroy data.

    The shape every ring here takes, with one difference that is the whole reason this ring
    exists as its own: **a schema arm can delete a column, a table, or the mirror of a link in
    a table nobody named.** So the target policy is not politeness, and the ring's own gate
    member exists to prove the four claims a passing engine test cannot: that a field write is
    surgical, that a cross-table loss really happens and was really predicted first, that a
    read-back verification is known to detect a swallowed write because it has been shown
    detecting one, and that a refused column authoring reaches the transport not at all.
    """
    return GateCoverage(
        marker="live_write",
        command="LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-NNN pytest -m live_write",
        credentials_env=list(WRITE_ENV),
        target_policy=(
            "Every member self-provisions the Base it changes, through the shared harness, and "
            "deletes it in a finally; the harness names no configured target at all, which is "
            "a static guarantee rather than a promise. It never changes the Base named by "
            "LARKDOCIO_SCRATCH_BASE, and on this ring that fence is the sharpest in the suite: "
            "the verbs here include deleting a column, deleting a table and converting a "
            "column's kind, and that Base holds hand-authored columns — a lookup, an email, a "
            "stage — that no API route can recreate, so a misdirected token would destroy "
            "evidence rather than merely be impolite. Calls are spaced at least 1.2 seconds "
            "apart and rate limits are never probed. Deselected by default; skips LOUDLY "
            "(never silently passes) when the write credentials are absent."
        ),
        members=[
            GateMember(
                id="base-schema-app-table-arm",
                module="tests/test_live_base_schema_arm.py",
                summary=(
                    "The app and table lifecycle against a real Base: create a Base, rename "
                    "it, copy it, create and batch-create and rename tables — each verified by "
                    "READING THE OBJECT BACK rather than by trusting a success code, because "
                    "no anchor on this scope can be compared. The copy is asynchronous and is "
                    "settled by the shipped bounded settle rather than by sleeping. A copy "
                    "given a folder is read back FROM THAT FOLDER'S OWN LISTING, beside the "
                    "control that a folder-shaped token naming nothing is refused "
                    "by this copy route (1254702) and copies nothing — the pair that tells "
                    "a key that is read "
                    "from one that is decoration."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory",
                                  REVISION_GUARD_FIELD_SCOPED_ONLY,
                                  "caller-supplied-destination"],
                arms=["app-lifecycle", "table-lifecycle", "async-copy-settle",
                      "copy-placed-in-a-folder", "destination-required",
                      "read-back-verified"],
            ),
            GateMember(
                id="base-schema-field-arm",
                module="tests/test_live_base_schema_fields.py",
                summary=(
                    "Column authoring against a real table: a create and a non-type edit, each "
                    "read back and each moving the table's own revision by one; a kind "
                    "conversion run over a POPULATED cell and the value read back afterwards, "
                    "because a conversion of an empty column proves nothing about loss; and "
                    "the allow-list biting on the create route and the convert route alike."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory",
                                  REVISION_GUARD_FIELD_SCOPED_ONLY, APPLY_LOG_COMPLETE],
                arms=["field-lifecycle", "conversion-over-a-populated-cell",
                      "allow-list-refusal", "anchor-moves-by-one"],
            ),
            GateMember(
                id="base-guided-field-migration-arm",
                module="tests/test_live_base_field_migration.py",
                summary=(
                    "The guided column-type migration against a real table: a populated Text "
                    "column really becomes a populated Number column — values in, values out, "
                    "the old column gone, the new one carrying the old name and no staging "
                    "column left. Beside it, the arm that matters more: the copy is FORCED to "
                    "write the wrong values, through a wrapper over the shipped write client, "
                    "and the delete must never be attempted with the source column left "
                    "standing and its values intact. Plus the plan-time refusal, live: a "
                    "column of prose asked to become a number refuses before any call."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory",
                                  DESTRUCTIVE_CONSENT_REQUIRED, CROSS_TABLE_LOSS_PREVIEW,
                                  APPLY_LOG_COMPLETE],
                arms=["migration-end-to-end", "forced-mismatch-halts-before-the-delete",
                      "plan-time-refusal-costs-nothing"],
            ),
            GateMember(
                id="base-schema-view-arm",
                module="tests/test_live_base_views.py",
                summary=(
                    "The view lifecycle and the filter that has to stick: create a view, set a "
                    "filter, READ IT BACK, replace the filter, read back the replacement "
                    "rather than a merge, delete the view. Beside it, on the same view, the "
                    "control that gives the read-back its meaning — a sibling property key "
                    "that answers success and persists nothing at all."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory",
                                  REVISION_GUARD_FIELD_SCOPED_ONLY],
                arms=["view-lifecycle", "filter-read-back", "filter-replaced-not-merged",
                      "swallow-control"],
            ),
            GateMember(
                id="base-schema-destructive-arm",
                module="tests/test_live_base_destructive.py",
                summary=(
                    "The only arm in the suite whose verbs destroy data. Every leg reads its "
                    "loss preview BEFORE it applies, in that order, because a preview read "
                    "afterwards proves nothing about what a caller could have known. The "
                    "two-table link delete asserts the mirror's disappearance in the OTHER "
                    "table; a table delete previews an inbound link in a third table and the "
                    "dangling that follows it; a plan whose target vanished underneath it "
                    "refuses rather than applying half of itself; and the last table of a Base "
                    "is refused by the server while the batch continues past it. IT ALSO "
                    "PROVES THE ONE DESTRUCTIVE VERB HERE THAT NO PLAN GATE COVERS — the "
                    "whole-Base delete: a Base the arm created is readable, is deleted, and is "
                    "then proved GONE by a re-read rather than by the delete's own success "
                    "code, a second delete raises with the other endpoint's code instead of "
                    "faking success, and the one predicate that spans both is held equal to "
                    "the same object-gone codes the harness's zero-orphan check uses. Beside "
                    "it, the payoff: a try/finally disposable-Base block whose body raises ON "
                    "PURPOSE still deletes, and the tenant is left as it was found."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory",
                                  DESTRUCTIVE_CONSENT_REQUIRED, CROSS_TABLE_LOSS_PREVIEW,
                                  APPLY_LOG_COMPLETE],
                arms=["cross-table-mirror-delete", "inbound-link-dangle",
                      "out-of-band-refusal", "protected-last-table", "consent-from-own-plan",
                      "whole-base-delete-proved-gone", "disposable-base-leaves-no-residue"],
            ),
            GateMember(
                id="base-schema-write-gate",
                module="tests/test_live_base_schema_gate.py",
                summary=(
                    "THE SCHEMA GATE, four arms, each one carrying a claim that would "
                    "otherwise be asserted rather than proved. SURGICAL: a column is added to "
                    "a real table and the table is read back — only that column appeared, "
                    "every other column is identical field by field, and every existing row's "
                    "every existing cell is byte-identical; the column is then removed and the "
                    "table is its old shape again, measured as a set difference rather than "
                    "spot-checked. A REAL CROSS-TABLE LOSS: a two-way link is built between "
                    "two tables, the preview is read and must name the mirror IN THE OTHER "
                    "TABLE, the delete is applied under consent minted from that same plan, "
                    "and BOTH columns are then gone — which is what makes the safety claim "
                    "true rather than stated, and is the reason the preview is scoped to the "
                    "whole Base. A READ-BACK-VERIFIED FILTER WITH ITS CONTROL: a filter is set "
                    "and re-read, and the comparison is semantic and says so, because the "
                    "server adds a condition id and a field type of its own; then a sibling "
                    "property key is written on the SAME view, answers success, reads back "
                    "empty, and is reported not persisted — the positive result is what makes "
                    "the negative one mean anything. AND A REFUSAL THAT MAKES NO CALL: a "
                    "column kind outside the allow-list is attempted against a transport that "
                    "raises on contact, so zero calls is structural rather than counted, with "
                    "an allow-listed create beside it on the same table proving the path "
                    "reaches the API and moves the table's revision."
                ),
                proves_contracts=["plan-gated", "dry-run-mandatory",
                                  DESTRUCTIVE_CONSENT_REQUIRED, CROSS_TABLE_LOSS_PREVIEW,
                                  REVISION_GUARD_FIELD_SCOPED_ONLY, APPLY_LOG_COMPLETE],
                arms=["surgical-field-write", "restore-to-baseline",
                      "real-cross-table-loss", "preview-predicted-it",
                      "filter-read-back-verified", "swallow-control",
                      "allow-list-zero-call-refusal", "live-positive-control"],
            ),
        ],
    )
