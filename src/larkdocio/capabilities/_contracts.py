"""The safety contracts — what the engine promises, per surface.

LD-244: the verbatim pre-split slice, lines 1658-1954 of the
2,770-line ``capabilities.py``. Nothing in it was rewritten.

LD-254: the apply-log completeness contract is a HOUSE INVARIANT, authored once in the
constants below (guard: ``tests/test_apply_log_complete_house_invariant.py``).
"""
from larkdocio.common import destination as _destination
from larkdocio.read.history import HISTORICAL_READ_CONTRACT
from larkdocio.snapshot import SNAPSHOT_INTEGRITY_CONTRACT

from ._models import SafetyContract

# ---------------------------------------------------------------------------- #
# LD-254 — THE HOUSE INVARIANT, AUTHORED ONCE.                                   #
#                                                                               #
# The contract was born surface-shaped: it was written for the sheets engine,    #
# because that is the engine whose per-entry loop once let a raw API error       #
# escape mid-batch. So a consumer asking ONE question — can I recover from a     #
# half-applied batch? — had to ask it per surface and infer the docx answer      #
# from silence. These constants are the one authoring: the id, the              #
# surface-independent promise, and the stated docx position. Every declaration   #
# site references them; nothing restates them, and the guard holds that the id   #
# appears in exactly one line of this package's Python and the promise's         #
# wording in exactly one module — and that a surface may declare the invariant   #
# only where the disposition boundary that makes it true actually exists.        #
# ---------------------------------------------------------------------------- #

#: The contract id — spelled ONCE in this package's Python. Declaration sites import it.
APPLY_LOG_COMPLETE = "apply-log-complete"

#: The invariant itself, surface-independent: it names no surface, and every surface that
#: declares it declares *this*, unweakened. Where a surface needs a caveat, the caveat is
#: stated next to the promise rather than shaved off it.
APPLY_LOG_COMPLETE_INVARIANT = (
    "A HOUSE INVARIANT, one definition wherever it is declared: THE APPLY-LOG IS 1:1 WITH "
    "THE PLAN AND EVERY ENTRY ENDS IN A TYPED DISPOSITION, WHATEVER HAPPENED. No Lark error, "
    "rate limit, transport failure or library bug escapes apply() — each becomes a typed "
    "entry rather than a traceback; len(log.entries) == len(plan.entries), in plan order, on "
    "every run; a partially-applied batch with no record of what happened is not a reachable "
    "state. The ONE exception that does leave apply() is deliberate and carries this same "
    "complete log: LarkApplyRefusedError, raised when the finished log holds entries that did "
    "not land, so a caller who discards the log cannot read a half-applied batch as a clean "
    "run — pass allow_partial=True to receive that log as a return value instead. It is "
    "declared only where it is enforced — applies_to is the list — and each declaring "
    "surface states its own per-entry vocabulary."
)

#: The lead-in that introduces the one declaring surface's per-entry text. Named so the
#: sheets half can be isolated (and digest-pinned) without parsing prose.
APPLY_LOG_COMPLETE_SHEETS_LEAD_IN = "ON sheets-write: "

#: The lead-in that introduces the docx position, kept out of the position's own words so the
#: guide can carry those words verbatim under its own heading.
APPLY_LOG_COMPLETE_DOCX_LEAD_IN = "AND THE docx-write POSITION, STATED: "

#: The docx position, STATED rather than implied — and stated without weakening the promise
#: above to fit docx, and without implying docx offers a declaring surface's per-entry
#: account. Deliberately label-free and markup-free: the shipped guide carries these same
#: plain words verbatim under its own heading, so a consumer meets one wording wherever they
#: ask the question.
#:
#: **SCOPED, not rewritten.** The whole-batch-zero-writes claim below is unchanged and still
#: binds — it is about a batch the whole-document compare-and-swap REFUSED, where no write is
#: issued at all. The closing sentence names the other scope, because a later change shipped
#: the opposite half of the truth on the same surface: an ACCEPTED batch's per-entry story,
#: authored once in :data:`larkdocio.write.model.applylog.INSERT_COST_CONTRACT` (the
#: ``mutating_write_calls`` measurement and the ``atomic`` consequence derived from it). Read
#: together with no scope marker the two read as a contradiction, and a consumer could
#: reasonably conclude docx never leaves partial content. The sentence POINTS AT that contract
#: by naming its two keys rather than restating it: that promise has one authoring, and a
#: second wording of it here would be a second thing to keep true.
#:
#: **CORRECTED IN PART, and the correction is paid here rather than deferred.** This text used
#: to say docx *"runs no per-entry disposition boundary of the kind this invariant names"*.
#: That was true when it was written and is not true now: the docx engine binds the shared
#: boundary and every plan entry ends in a typed, logged outcome. The sentence is replaced
#: rather than struck, because the CONCLUSION it supported — that docx does not declare —
#: still holds, on a different and narrower reason: the whole-document compare-and-swap runs
#: BEFORE the batch and deliberately re-raises a rate-limit error, so exactly one failure
#: still leaves apply() with no log. A surface may declare this invariant only where it holds
#: without a rider, and that rider is real.
APPLY_LOG_COMPLETE_DOCX_POSITION = (
    "docx-write does not declare this invariant, which "
    "is a position rather than an omission. The docx apply path is WHOLE-BATCH-ZERO-WRITES — "
    "a batch refused by the whole-document compare-and-swap issues zero writes and never "
    "partially applies, so there is nothing to enumerate. Each entry of an ACCEPTED batch is "
    "dispatched inside a disposition boundary, so a Lark error, a transport failure or a "
    "library bug raised while applying an entry becomes a typed, logged entry and the "
    "batch's record survives it. What keeps this surface from declaring the invariant is one "
    "deliberate escape that happens BEFORE the batch: the whole-document compare-and-swap "
    "re-raises a rate-limit error rather than treating throttling as drift, so that one "
    "failure leaves apply() with no log. Nothing here promises docx the unqualified "
    "whatever-happened guarantee a declaring surface gives you. "
    "THAT IS A CLAIM ABOUT A REFUSED BATCH, AND IT IS NOT THE WHOLE STORY OF AN ACCEPTED "
    "ONE: once a batch is accepted, each inserted apply-log entry states its own measured "
    "cost and the consequence derived from it in mutating_write_calls and atomic, and the "
    "stability contract on those two keys — not this position — is what says whether that "
    "entry's content landed whole."
)


#: The lead-in that introduces the SECOND declaring surface's per-entry text (LD-260). Named
#: for the same reason the sheets one is: so each half can be isolated without parsing prose.
APPLY_LOG_COMPLETE_BASE_LEAD_IN = "ON base-write: "

#: What the invariant buys on the Base record-write engine. It is the same promise — this text
#: adds the surface's own per-entry vocabulary, and takes nothing off the shared sentence.
#: The lead-in that introduces the THIRD declaring surface's per-entry text — the Base SCHEMA
#: engine. Named for the same reason the other two are: so each half can be isolated without
#: parsing prose.
APPLY_LOG_COMPLETE_BASE_SCHEMA_LEAD_IN = "ON base-schema-write: "

#: What the invariant buys on the Base schema engine. The same promise, with the two scope
#: facts a caller has to plan around stated rather than left to be inferred.
APPLY_LOG_COMPLETE_BASE_SCHEMA_POSITION = (
    "the same per-entry account over structural work, with two differences that follow from "
    "what the API offers. First, a structural entry is verified by READ-BACK rather than by "
    "an anchor comparison wherever no anchor exists, so its log entry carries what the "
    "read-back saw — the new name, the created id, the persisted property, the absence of a "
    "deleted object — and an entry whose read-back could not confirm the change is never "
    "logged applied. Second, a refusal here is entry-scoped wherever the server's answer is "
    "about one object: a Base refusing to delete its last table refuses THAT entry and the "
    "batch continues past it, while a scope denial, a rate limit or a transport failure halts "
    "the batch and every remaining entry is logged not-attempted, naming where and why. "
    "Nothing structural is retried and nothing is half-applied silently: a plan that could not "
    "enumerate what a delete would take refuses the entry before any call."
)

APPLY_LOG_COMPLETE_BASE_POSITION = (
    "the same per-entry account, with one scope difference a caller has to plan around: the "
    "compare-and-swap anchor is isolated PER TABLE, so a table whose anchor moved has ITS "
    "entries logged stale with zero writes for that table while every other table is still "
    "judged against its own anchor. A systemic answer — a scope denial, a rate limit, a "
    "transport failure, or an answer about the table or the Base rather than about one "
    "record — halts the whole batch and every remaining entry is logged not-attempted, naming "
    "where and why. One outcome is unique to this surface: a call that returned success while "
    "the table's revision did not move is logged dropped, never applied, because success is "
    "not evidence a write happened here."
)


def _safety_contracts() -> dict:
    _WRITE = ["docx-write", "sheets-write"]
    _PLAN_GATED = _WRITE + ["base-write", "base-schema-write"]
    return {
        "destructive-consent-required": SafetyContract(
            id="destructive-consent-required",
            summary=(
                "Base schema write: a plan that would DELETE something is applied only under a "
                "consent token minted from THAT PLAN, and from no other. Building the plan "
                "shows you the loss; applying it costs a second, deliberate act, so a delete "
                "cannot be reached by a caller who never saw what it would take. Consent is "
                "not a flag and not a keyword a caller can spell for themselves: it is minted "
                "from its own plan and refuses to be minted at all when the plan could not "
                "enumerate the loss. A plan applied without it raises rather than deleting, "
                "and consent minted from one plan does not travel to another. WHAT IT DOES "
                "NOT COVER, stated rather than implied: the Base surface loses data in THREE "
                "TIERS and this contract is one of them. A record delete destroys rows "
                "through the ordinary dry-run/apply path, carrying a per-row before and a "
                "value precondition but NO CONSENT TOKEN. A view delete carries neither - its "
                "loss preview is None and no token is required, because it destroys a "
                "presentation and not a cell. A schema delete that destroys cells carries "
                "both, and it is the only tier this contract speaks for."
            ),
            applies_to=["base-schema-write"],
        ),
        "cross-table-loss-preview": SafetyContract(
            id="cross-table-loss-preview",
            summary=(
                "Base schema write: the loss a delete would cause is ENUMERATED before it "
                "happens, and the enumeration is app-scoped — it covers the whole Base rather "
                "than the table you named, because on a Base the loss leaves that table. "
                "Deleting a "
                "two-way link column removes its mirror in another table, and the preview "
                "names that mirror, its table and how many of its cells hold data. Deleting a "
                "table destroys every link pointing at it, in whatever table those links "
                "live in, and the preview names them too — a one-way link survives the delete "
                "and dangles, a two-way link is removed outright along with its twin inside the "
                "table being deleted, and both losses are silent — and so are the Lookup columns that "
                "mirror it, which carry no link at all and yet go blank on every row once the "
                "table they mirror is gone. A loss the engine cannot fully "
                "enumerate is a refusal, never a warning: if the scan cannot see everything it "
                "would take, the delete does not proceed."
            ),
            applies_to=["base-schema-write"],
        ),
        "revision-guard-field-scoped-only": SafetyContract(
            id="revision-guard-field-scoped-only",
            summary=(
                "Base schema write: THE COMPARE-AND-SWAP COVERS FIELD OPS AND NOTHING ELSE, "
                "and the asymmetry is disclosed rather than smoothed. A column op rides the "
                "same client-side table.revision guard the record engine calls 'stale-base' — "
                "the plan carries the anchor it was built on, apply re-reads it immediately "
                "before the write, and a table that moved refuses with zero writes. An "
                "app-scoped op (creating, renaming or copying a Base; creating, renaming or "
                "deleting a table) has NO REVISION GUARD AT ALL, and neither does a view-scoped "
                "one: the Base-level counter exists and moves, but three probe packs disagree "
                "about what it counts, so a guard built on it would refuse valid plans and pass "
                "invalid ones while reading to a caller exactly like the guard the column ops "
                "really have. Those ops are verified by READ-BACK instead — the renamed Base "
                "re-reads with its new name, the created table appears in the listing, the "
                "filter re-reads with the conditions that were sent — and a success code is "
                "never accepted as evidence on its own. Every plan entry states which of the "
                "two it is, so the absence is something a caller reads rather than infers."
            ),
            applies_to=["base-schema-write"],
        ),
        "plan-gated": SafetyContract(
            id="plan-gated",
            summary=(
                "apply() accepts ONLY a non-forgeable Plan produced by dry_run — there is no "
                "direct-apply path (a bag of raw requests is a TypeError)."
            ),
            applies_to=list(_PLAN_GATED),
        ),
        "dry-run-mandatory": SafetyContract(
            id="dry-run-mandatory",
            summary=(
                "Every write is previewed by a mandatory dry_run (zero writes) that builds the "
                "Plan; nothing is applied that was not previewed. THE PLAN TELLS YOU "
                "EVERYTHING (sheets): anything knowable before any call is decided "
                "pre-I/O and costs no read — a values matrix whose arity does not match its "
                "target range refuses 'shape-mismatch' naming both shapes, and a range that is "
                "not an addressable rectangle (reversed, sub-1, past the 100-column notation "
                "ceiling) refuses 'malformed-range' naming the valid form. Anything "
                "destructive is ENUMERATED, not summarized: a merge previews every covered "
                "value it discards, a dimension delete previews the removed cells (trimmed to "
                "the used extent, with the trim itself disclosed) plus the merges it "
                "intersects, and a write or clear over a LIVE FORMULA carries an "
                "'overwrites-live-formula' note listing each cell, its expression and its "
                "current computed value — because the precondition read is UnformattedValue, "
                "under which a formula answers its result and is indistinguishable from data. "
                "A write that will do NOTHING says so ('no-merge-at-range' on an unmerge that "
                "intersects no merge; 'out-of-bounds-dimension' on a delete span past the "
                "row/column count). Notes COMPOSE — an entry earning several carries a "
                "'multiple' envelope and preview_notes flattens either shape — so no "
                "disclosure can displace another. Malformed input raises a typed, EXAMPLED "
                "error rather than a bare one (A1RangeError, DimensionSpanError, "
                "FormulaExpressionError), and every id-anchored docx family — edit, insert, "
                "delete AND sub-span — discloses the precondition_text its compare-and-swap "
                "will use. ON base-write the same rule holds with a sharper edge, because the "
                "diff is computed offline against a snapshot the caller already holds: a "
                "computed or opaque cell (a formula, a lookup, a stage, an auto-number, a "
                "record-metadata field) and a value that is not its field's write shape are "
                "BOTH refused at plan time, so they cost no call at all, and the plan shows "
                "exactly which records ride in which batch call."
            ),
            applies_to=list(_PLAN_GATED),
        ),
        "STALE_SHEET": SafetyContract(
            id="STALE_SHEET",
            summary=(
                "Sheets staleness, TWO TIERS. Tier 1 — the compare-and-swap: the "
                "spreadsheet revision is cached at plan time and re-read immediately before "
                "EACH write; a bump refuses 'stale-sheet' (no write) and resyncs the anchor so "
                "the rest of the batch still applies. Tier 1 is NEVER silently off: some "
                "spreadsheets report a constant 0 (or no) revision, so every plan / dry-run "
                "output carries revision_guard 'active' or 'unavailable' (with the WHY). "
                "Tier 2 — the value precondition, always: a value / rich-cell entry re-reads "
                "its target's raw value before its write and refuses precondition-mismatch on "
                "drift; a FORMULA entry re-reads and compares its target's EXPRESSION "
                "(valueRenderOption=Formula) instead, because a computed value drifts whenever "
                "the referenced data changes and comparing it would refuse writes nobody made. "
                "Each plan entry's value_precondition says whether tier 2 covers it "
                "— a dropdown-rule / structural / merge / tab entry has no cell-value "
                "precondition. Any nonzero advance still refuses 'stale-sheet' even from a "
                "0 anchor, and the next plan on a nonzero anchor self-activates tier 1. "
                "STALENESS IS NEVER A CATCH-ALL: a range whose sheet_id is "
                "not a tab of this spreadsheet refuses 'unknown-tab' with a did-you-mean, a "
                "range Lark rejects as malformed (code 90202) refuses 'malformed-range' with "
                "the valid form, and 'tab-vanished' is RESERVED for a range that really was "
                "readable at plan time and is not now — so a wrong-but-confident diagnosis "
                "never sends you to re-plan something that was never stale."
            ),
            applies_to=["sheets-write"],
        ),
        "STALE_ANCHOR": SafetyContract(
            id="STALE_ANCHOR",
            summary=(
                "docx write: the anchored block is re-read right before each write and "
                "re-validated with the ANCHOR'S OWN precondition; drift refuses stale-anchor "
                "(no write, the rest of the batch still applies). A quote+breadcrumb Anchor "
                "requires its quote to still be a substring of the live block. An AnchorById "
                "(a bare block_id) has no quote, and an id cannot come to mean a different "
                "block, so instead the "
                "plan captures the block's live-basis text and the write is a "
                "COMPARE-AND-SWAP: any change to that block since the preview refuses rather "
                "than overwrite it. A table-cell TableLocator edit is stricter still — a "
                "DOUBLE re-validation (the row's key cell AND the target cell). A block that "
                "cannot be re-read at all (deleted between plan and apply) refuses "
                "stale-anchor with Lark's own code/msg in the detail, never an aborted batch."
            ),
            applies_to=["docx-write"],
        ),
        "STALE_BASE": SafetyContract(
            id="STALE_BASE",
            summary=(
                "Base record write: a CLIENT-SIDE read-compare-write on table.revision, and "
                "the registry says so rather than letting the name suggest more. There is no "
                "If-Match on this API and no server-side compare-and-swap: a record write "
                "carrying a revision or last_modified_time body key answered success AND "
                "applied the write, so no precondition key is ever sent — sending one would "
                "be a lie that reads like safety. Instead the engine READS table.revision, "
                "compares it to the value the plan was built on, and only then writes. What "
                "that buys: the window between the plan and the write is closed. What it does "
                "NOT buy: the last microsecond between the compare and the write. THE HALT "
                "SCOPE IS PER-TABLE, because table.revision is isolated per table — a moved "
                "anchor refuses that table's entries with ZERO writes for it and every other "
                "table is still judged against its own anchor. The refusal is recoverable, "
                "never a dead end: re-read the table, re-plan, re-apply. A SECOND TIER runs "
                "underneath it for every entry that has a before: the cells an update writes "
                "(or the record a delete removes) are re-read immediately before the batch "
                "and any drift refuses precondition-mismatch for that entry alone, which is "
                "what covers a table whose anchor cannot arm tier 1. And because success is "
                "not evidence a write happened on this API, every call is followed by a "
                "second anchor read: a call that answered success without moving the anchor "
                "is reported dropped rather than applied. The engine reports it; it does not "
                "retry, because re-sending would be a guess about why the value was "
                "discarded."
            ),
            applies_to=["base-write"],
        ),
        "STALE_DOCUMENT": SafetyContract(
            id="STALE_DOCUMENT",
            summary=(
                "docx write: the WHOLE-DOCUMENT compare-and-swap. A "
                "plan may carry the document's revision_id (dry_run(..., "
                "document_revision_id=…) — the reader returns it as document.revision_id); "
                "apply re-reads it ONCE immediately before the batch and, on ANY difference, "
                "refuses the ENTIRE batch with stale-document and ZERO writes issued. "
                "Partial application is not an outcome, and there is NO auto-mapping: the "
                "engine never re-locates anchors or re-indexes positions to accommodate a "
                "document that changed under a plan — the refusal detail says so and tells "
                "you to re-download and re-plan. This is what catches drift AROUND an "
                "anchor, which STALE_ANCHOR is structurally blind to (an insertion above a "
                "still-matching anchor moves where content lands). A revision that cannot be "
                "read at all refuses conservatively — unconfirmable is treated as changed. "
                "NEVER silently off: every plan carries revision_guard 'active' or "
                "'unavailable' (with the WHY, and how to activate it) and the apply-log "
                "carries the batch's status; with no anchor the guard is marked unavailable, "
                "costs no call, and the per-entry STALE_ANCHOR re-validation still runs. It "
                "self-activates on the next plan that carries a revision."
            ),
            applies_to=["docx-write"],
        ),
        APPLY_LOG_COMPLETE: SafetyContract(
            id=APPLY_LOG_COMPLETE,
            summary=(
                APPLY_LOG_COMPLETE_INVARIANT + " " + APPLY_LOG_COMPLETE_SHEETS_LEAD_IN +
                "Each per-entry step runs inside a "
                "disposition boundary that classifies any exception it raises: an "
                "ENTRY-SCOPED error (Lark answered about that entry — the 90204 "
                "id-not-found class) refuses it 'api-error' (or 'invalid-request' for a "
                "local pre-wire error) and the batch CONTINUES, per the sheets per-entry "
                "doctrine; a SYSTEMIC error HALTS the batch — 'permission-denied' (the app "
                "lacks a required SCOPE: nothing landed, and a missing grant would refuse "
                "every remaining entry identically, so the batch stops rather than spending "
                "one throttled call per entry on a condition that cannot clear between them; "
                "the detail relays Lark's own missing scope, verbatim code/msg, console link "
                "when Lark sends one, and which credential pair made the call, and the repair "
                "is a console grant then a re-plan), 'rate-limited' (nothing "
                "landed), 'transport-failure' / 'unexpected-error' (whether it landed is "
                "INDETERMINATE, outcome 'failed', never mislabelled a refusal) — and every "
                "remaining entry is logged 'not-attempted', never silently dropped. A "
                "failure AFTER the write op returned is logged 'applied-unverified' (the "
                "change IS on the sheet, its verification record is not) and halts, because "
                "the compare-and-swap anchor is then unknown. ApplyLog.halt discloses "
                "whether the batch stopped early and why. Paired with the plan-time @mention "
                "check: dry_run proves mention open_ids exist in ONE read call and refuses "
                "'unknown-mention' at plan time; a check that cannot run is DISCLOSED as "
                "mention_validation 'unavailable' with the WHY, never silently skipped. "
                "THE LOG CARRIES THE PLAN'S WARNINGS: every log entry retains the "
                "plan entry's preview_note (stamped at the one apply() seam, for every "
                "disposition — read them with entry.preview_notes), because the log used to "
                "build a fresh record on success and the loud inert-'='-string warning died "
                "at that boundary: a warning that only reaches an interactive operator is not "
                "a disclosure. ApplyLog.inert_formula_strings names every entry that LANDED "
                "having stored a '='-prefixed plain string, so the one-line CI assertion is "
                "'assert not log.formula_not_evaluated and not log.inert_formula_strings' — "
                "formula_not_evaluated alone sees only the formula family and came back green "
                "on exactly the trap the dry-run had shouted about. " +
                APPLY_LOG_COMPLETE_DOCX_LEAD_IN + APPLY_LOG_COMPLETE_DOCX_POSITION + " " +
                APPLY_LOG_COMPLETE_BASE_LEAD_IN + APPLY_LOG_COMPLETE_BASE_POSITION + " " +
                APPLY_LOG_COMPLETE_BASE_SCHEMA_LEAD_IN +
                APPLY_LOG_COMPLETE_BASE_SCHEMA_POSITION
            ),
            applies_to=["sheets-write", "base-write", "base-schema-write"],
        ),
        "permission-denial-is-never-an-absence": SafetyContract(
            id="permission-denial-is-never-an-absence",
            summary=(
                "EVERY surface: when Lark refuses a call because the app lacks a SCOPE, the "
                "failure is a distinct typed permission error (LarkPermissionError, a "
                "LarkAPIError subclass so existing handling is unaffected) carrying the exact "
                "missing scope(s), Lark's verbatim code/msg, the console deep link WHEN the "
                "body supplies one (never synthesized — an absent link is stated as absent, "
                "not filled with a placeholder), which credential pair made the call, and the "
                "fallback that still works where one does. It is NEVER folded into not-found, "
                "unavailable or a generic error, because a scope gap presented as an absent "
                "thing is how a missing FIELD-LEVEL grant reads as missing data: the call "
                "SUCCEEDS and the fields that grant governs come back empty. That third case "
                "is classified too — a success whose governed fields are all empty is reported "
                "as a suspected permission gap naming the grant, and conservatively, so a "
                "PARTIAL answer stays an ordinary absence. Uniform by construction rather than "
                "by repetition: every surface's non-zero Lark code is classified in the ONE "
                "shared error factory. An OPTIONAL, ADVISORY preflight "
                "(larkdocio.preflight.check_permissions) can check before starting; it is "
                "never mandatory, never mutates (every probe is a GET against a deliberately "
                "nonexistent id, so nothing is created), never requests or widens a scope, "
                "discloses its own API-call cost up front, and states per scope HOW it knows "
                "— probed, derived, or unknown. It is blind to write scopes and to field-level "
                "grants, and says so in its own result."
            ),
            applies_to=[
                "docx-read", "docx-comments-read", "sheets-read",
                "sheets-embedded-deep-read", "docx-write", "sheets-write",
            ],
        ),
        "exactly-one-or-refuse": SafetyContract(
            id="exactly-one-or-refuse",
            summary=(
                "Resolution returns EXACTLY ONE target or a typed refusal — never a guess: an "
                "anchor on the write surfaces (ambiguous / not-found / write-hostile are typed "
                "refusals), a display name on contacts-read (not-found / ambiguous / "
                "could-not-look)."
            ),
            applies_to=list(_WRITE) + ["contacts-read"],
        ),
        "caller-supplied-destination": SafetyContract(
            id="caller-supplied-destination",
            summary=(
                # PROJECTED, never re-typed. Everything below that states the RULE is
                # larkdocio.common.destination's own bytes — the mechanism _assembly.py
                # already uses for the sibling drive-upload sentence. The hand-written
                # restatement that used to live here was a fourth authoring of one rule and
                # drifted twice: past the remedy ORDER (the route with no permanent
                # consequence leads, and the other one's cost is stated before it is taken)
                # and past the typed-root refusal AND the limit that ships with it. Its
                # "CREATES NO FOLDER" clause had also become readable as a denial that a
                # folder-creating verb ships, which one has since 2026-08-14 — the same defect
                # the Drive capability matrix carried (DRIVE.md, in the source repository), in a
                # different costume. Only the connective scaffold here is hand-written, and the
                # destination suite (tests/test_caller_supplied_destination.py, in the source repository)
                # asserts the summary IS that scaffold woven with these five constants and
                # nothing else.
                "Every verb that creates a NEW TOP-LEVEL OBJECT — a document, a spreadsheet, "
                "a Base, a copy of a Base, a folder, an uploaded file — requires a destination "
                "the caller supplies, and refuses LOCALLY, before any call, when none is "
                "given. THE RULE, IN THE WORDS THE REFUSAL ITSELF CARRIES: "
                + _destination.DESTINATION_RULE +
                ". Every spelling of none is refused alike, including the EMPTY STRING, which "
                "Lark itself accepts and files in the calling application's own root. ONE "
                "REAL TOKEN IS REFUSED TOO, AND BY TYPE RATHER THAN BY PROSE — with the "
                "guarantee's own limit in the same breath: "
                + _destination.ROOT_IS_NOT_A_DESTINATION +
                ". WHAT THIS FENCE IS: a refusal, not a folder factory. It picks no default "
                "place for you and makes no folder of its own to put things in — which is a "
                "statement about the fence, NOT a claim that no folder-creating verb ships, "
                "because one does and the remedy below names it. There is no opt-out and no "
                "flag restoring the old default. THE REMEDY, IN THE ORDER THE REFUSAL STATES "
                "IT: "
                + _destination.WHAT_TO_SUPPLY + "; "
                + _destination.HOW_TO_GET_A_DESTINATION + "; "
                + _destination.WHAT_A_FOLDER_COSTS +
                ". A create INSIDE an object the caller already named — a block, a table, a "
                "column, a row, a view, an anchored image, a version, a comment — is not in "
                "scope: the parent is the destination and it was already supplied."
            ),
            applies_to=[
                "docx-write", "sheets-write", "base-schema-write",
                "drive-folders-write", "drive-files-write",
            ],
        ),
        "read-back-is-the-verdict": SafetyContract(
            id="read-back-is-the-verdict",
            summary=(
                "Drive access management: an operation reports what an INDEPENDENT read found, "
                "never what the write echoed. code 0 proves ACCEPTANCE and nothing else, and "
                "this exact endpoint family produced a measured SWALLOW — a member re-add "
                "answered code 0 with a complete member echo and was absent from the read-back "
                "a moment later — so a grant, an update and a revoke each follow their write "
                "with a member read, and the copy-lever call follows its one-key-per-call "
                "PATCHes with a settings read. An op that was accepted and did not store "
                "reports stored=False rather than success."
            ),
            applies_to=["drive-access-write"],
        ),
        # LD-645 — the two contracts that stop the OTHER non-plan-gated Drive legs from
        # answering the verification question with silence. The census used to declare
        # nothing for either, which read as "no promise" on the leg with the STRONGEST
        # verification in the package and as "no promise" on the leg with none — the same
        # answer for two opposite facts.
        "bytes-verified-round-trip": SafetyContract(
            id="bytes-verified-round-trip",
            summary=(
                "Drive file upload: THE VERDICT IS THE RE-DOWNLOAD, NOT THE code 0. With "
                "verify_bytes (the default) put_file_in_folder downloads the object it just "
                "uploaded and compares it to what went up BY sha256 AND LENGTH — the shared "
                "larkdocio.base.media.verify_round_trip, the same check the Base attachment "
                "leg uses — and publishes that verdict as LinkedFile.bytes_verified. The "
                "bytes are never inspected. This holds for the chunked route too: above "
                "SINGLE_SHOT_MAX_BYTES the same op sends server-partitioned blocks and the "
                "verification is unchanged. TWO LIMITS, STATED RATHER THAN LEFT TO BE FOUND: "
                "verify_bytes=False turns the check off and bytes_verified then reports "
                "False, which is an absence of a verdict and not a negative one; and a "
                "failure AFTER the upload — including a failed verification — leaves a real "
                "file behind, so the exception carries orphan_file_token and nothing here "
                "issues an unrequested delete."
            ),
            applies_to=["drive-files-write"],
        ),
        "version-pairing-is-not-a-verdict": SafetyContract(
            id="version-pairing-is-not-a-verdict",
            summary=(
                "Drive named versions: THE REVISION READ HAPPENS BEFORE THE WRITE, AND IT IS "
                "A PAIRING RATHER THAN A VERDICT. create_version reads the head docx revision "
                "immediately BEFORE the create so a ledger can record (name, token, revision) "
                "as one row; it never lists the new version back, and NOTHING IN THE SHIPPED "
                "CALL PATH VERIFIES THAT THE VERSION EXISTS — the read-back that would exists "
                "only in the credential-gated live gate. What the response's code 0 and "
                "version token prove is ACCEPTANCE. The pairing is exact absent a concurrent "
                "edit (the create was measured revision-inert: the head revision was "
                "identical immediately before and immediately after it), and where the "
                "revision is unavailable — the read failed, or obj_type is not docx — the "
                "field is honestly None with the reason in revision_note, never synthesized "
                "and never zero. This contract is declared to say what the read IS; it "
                "promises no read-back and adds none."
            ),
            applies_to=["drive-versions-write"],
        ),
        "one-tree-one-batch": SafetyContract(
            id="one-tree-one-batch",
            summary=(
                "docx write: ONE TREE, ONE BATCH. Every request in a batch is resolved against "
                "a SINGLE CONSISTENT SNAPSHOT of the document tree — which is exactly what "
                "makes STALE_ANCHOR and STALE_DOCUMENT mean anything — so A BATCH CANNOT DEPEND "
                "ON ITS OWN WRITES: every queued request must target content that exists at "
                "commit time; commit the insert, then anchor follow-ups by created_block_ids. "
                "This is a DELIBERATE limitation, not a gap: intra-batch dependencies would "
                "require sequential re-planning inside apply(), dissolving the snapshot "
                "guarantee and the whole-batch-zero-writes contract with it, so an approved "
                "plan would no longer describe what will happen. And it is DISCLOSED rather "
                "than left to be discovered — the commonest shape is 'insert a section, then "
                "refine what you just inserted', so when a not-found anchor's text appears in "
                "the SAME batch's queued INSERT content the refusal's detail names that cause "
                "and the recovery that works, instead of the re-read that cannot succeed. "
                "Detected at plan time by scanning the batch's own queued content: ZERO extra "
                "I/O, the reason is still not-found, the ordinary detail survives verbatim as "
                "the prefix, and an edit's replacement or a delete's target never triggers the "
                "insert-specific clause."
            ),
            applies_to=["docx-write"],
        ),
        "comment-anchors-honored-or-refused": SafetyContract(
            id="comment-anchors-honored-or-refused",
            summary=(
                "docx write: a reviewer's INLINE comment anchors are honored on the path that "
                "can honor them, and every path that cannot REFUSES. THREE PATHS, all three "
                "answered. (1) A SUB-SPAN edit proceeds: it splits the block's runs at the span "
                "boundaries and each rebuilt run re-emits the anchor ids of the text it "
                "replaces, so an anchor rides back to Lark on the words it was left on — and a "
                "span crossing runs whose anchors DIFFER refuses span-not-splittable rather "
                "than pick one reviewer's comment to stretch over text they never commented on. "
                "(2) A WHOLE-BLOCK edit refuses comment-anchors-present: the rebuild collapses "
                "the block to one run, leaving per-passage anchors nowhere to attach; the "
                "refusal detail names the ids and the sub-span edit as the recovery. (3) A "
                "WHOLE-CELL (TableLocator) edit refuses on the same collapse, judged on the "
                "inline anchors of the cell's inner text block — the one block the patch "
                "rewrites — with a detail naming the row and column and, as the recovery, a "
                "sub-span edit anchored by that inner block's id, since a "
                "row-key-and-column locator cannot name a span. No flag overrides either "
                "refusal, and a BLOCK-LEVEL comment (on the block as a whole rather than on "
                "words inside it) triggers neither: a run split does not touch it. "
                "AND THE PLAN SAYS SO ON THE PATH THAT PROCEEDS: a resolved sub-span entry "
                "whose target carries inline anchors carries a comment-anchors-present-on-target "
                "preview_note listing the ids, so a human approving the preview can see "
                "reviewers are involved and read what they said first — decided from the tree "
                "the plan already resolved against, at ZERO extra API cost, and composing with "
                "any other disclosure rather than displacing it. Anchors themselves are never "
                "creatable: Lark has no anchored-comment create on either surface, which is "
                "also why this contract's live proof is a READ-ONLY arm against a document that "
                "already has real anchors rather than a self-provisioned disposable."
            ),
            applies_to=["docx-write"],
        ),
        "comment-create-whole-document-only": SafetyContract(
            id="comment-create-whole-document-only",
            summary=(
                "docx write: a comment can be CREATED, and only in the one shape Lark's API "
                "actually produces — attached to the WHOLE DOCUMENT, appearing in the "
                "document's comments panel, highlighting no passage. Asking for an ANCHORED "
                "comment is REFUSED (comment-anchor-not-creatable) rather than quietly "
                "downgraded, and that refusal is the point of the whole op: the create route "
                "ACCEPTS an anchor, a quote and is_whole:false, answers code 0, and silently "
                "creates a plain whole-document comment — six shapes were tried, including a "
                "bogus block id and a quote that does not occur in the document, and every "
                "one was accepted and dropped. So a pass-through would report an anchored "
                "comment that was never created; the refusal names the field that was "
                "supplied, that evidence, and the two things that do work (a whole-document "
                "comment, or READING the anchors that already exist). A SPREADSHEET target is "
                "refused too (comment-surface-unsupported): comment creation is enum-limited "
                "to [doc,docx] at every granularity, whole-file attempt included, while "
                "comment READING on a spreadsheet works — so the refusal points at the read. "
                "Both refusals are decided at PLAN time, so they cost ZERO API calls. AND "
                "AUTHORSHIP IS DISCLOSED, NOT DISCOVERED: every resolved create carries a "
                "preview_note stating that the comment lands as your application's own BOT "
                "identity — a bare open_id with no resolvable display name, because the "
                "directory answers 41050 for it and the payload carries no "
                "human-vs-application flag — and the apply-log reports that author id, which "
                "is the id a later removal must state."
            ),
            applies_to=["docx-write"],
        ),
        "comment-removal-sole-author-or-refuse": SafetyContract(
            id="comment-removal-sole-author-or-refuse",
            summary=(
                "docx write: a comment thread is removed only when your application AUTHORED "
                "it and is ALONE in it, and it is removed WHOLE or not at all. There is no "
                "delete-a-comment endpoint — that route answers a gateway-level, non-JSON 404 "
                "— so a comment is removed by deleting every reply, which the API permits only "
                "for replies the caller wrote (anything else is HTTP 403 / code 1069303 "
                "\"forbidden\", a refusal about who is asking rather than about the file). The "
                "engine therefore READS the live thread and JUDGES it BEFORE issuing the first "
                "delete: a thread carrying anyone else's reply refuses "
                "comment-thread-not-solely-authored with the foreign author named and NOTHING "
                "deleted, and a thread that is already gone or empty refuses not-found rather "
                "than reporting a removal this run did not perform. Because the decision "
                "precedes every delete — and because a thread that passes has one author, so "
                "the API judges every one of its deletes identically — there is no code path "
                "that deletes some replies and stops. A server failure partway through is the "
                "one thing no pre-check can prevent; it cannot be undone, so it is RECORDED: "
                "the refusal carries the ids that did go, because silence about a partial "
                "removal would be the real failure. A half-deleted thread misrepresents the "
                "conversation with no way back, which is worse than refusing."
            ),
            applies_to=["docx-write"],
        ),
        HISTORICAL_READ_CONTRACT: SafetyContract(
            id=HISTORICAL_READ_CONTRACT,
            summary=(
                "docx read: A HISTORICAL READ RIDES THE ROUTE THE PIN WAS MEASURED ON, AND "
                "NO OTHER. get_docx_content(token, document_revision_id=<n>) reads the "
                "document as of revision n through the FLAT BLOCKS LIST "
                "(GET …/docx/v1/documents/{id}/blocks) — the one route measured to honour "
                "the parameter, falsifiably: an earlier revision returned an earlier body "
                "while head returned head's in the same instant. Being MODELLED is not being "
                "HONOURED, and this contract exists because two neighbouring routes accept "
                "document_revision_id and discard it: raw_content answers head "
                "byte-identically to the plain call, and the document meta route answers "
                "head's revision_id. So a pinned read never goes through either, and it "
                "carries no revision_id or title of its own rather than handing back head's "
                "wearing the pinned revision's name — the pin you asked for is on the result "
                "as document_revision_id, and the title as of that revision is the page "
                "block's own text. THE ONE THING IT CANNOT DO, said plainly: an out-of-range "
                "revision is answered code 0 with HEAD's body and no marker, so over-range is "
                "UNDETECTABLE here and a caller who pins a bad number is silently reading "
                "head. A pin of 0 or below, or anything that is not an int, is refused "
                "LOCALLY in Lark's own words before a call is spent; -1 is Lark's head "
                "sentinel and is refused by naming the spelling that works, which is None. "
                "Reading at a NAMED EDITION is a measured refusal — no route maps an edition "
                "token to content and none maps one to a revision — so the pairing is "
                "recorded at creation time instead, by create_version."
            ),
            applies_to=["docx-read"],
        ),
        SNAPSHOT_INTEGRITY_CONTRACT: SafetyContract(
            id=SNAPSHOT_INTEGRITY_CONTRACT,
            summary=(
                "docx read: A PERSISTED READ IS REHYDRATED EXACTLY OR REFUSED TYPED — NEVER "
                "REPAIRED. larkdocio.snapshot.snapshot() writes the lossless read (the raw "
                "block payloads, the document token, the document_revision_id and the "
                "api_domain the read was taken against) as one "
                "versioned, checksummed file, and load() brings it back offline with one "
                "guarantee: a load-then-project is BYTE-IDENTICAL to the projection the "
                "snapshot was taken from. A checksum mismatch, a truncated or unreadable "
                "file, an unrecognized format_version, or malformed content each raise "
                "LarkSnapshotIntegrityError naming what failed and naming the fix — "
                "RE-DOWNLOAD the document. Exactly-one-or-refuse: no repair, no salvage, no "
                "best-effort load, and NEVER a partially-rehydrated tree. THE CHECKSUM IS "
                "FOR INTEGRITY AND NOTHING ELSE: no security boundary exists between a local "
                "library and the caller, so what it answers is accidental corruption — a "
                "truncated write, a half-synced cloud folder, a corrupted disk, a "
                "hand-edited file. There is no encryption and no key material, and the "
                "digest is not a signature. THE SNAPSHOT IS OURS AND IMMUTABLE, the Markdown "
                "draft is theirs and editable, and the boundary between them is reconcile(): "
                "no mutable tree API ships and nothing accepts a caller-mutated tree. The "
                "persisted document_revision_id is what arms dry_run's STALE_DOCUMENT "
                "compare-and-swap, so a snapshot goes stale the moment somebody edits the "
                "document and the guard refusing the batch is the correct outcome; a "
                "snapshot is NOT a lock and reserves nothing. AND THE ANCHOR CAN BE ABSENT: "
                "a snapshot taken without a revision persists None, the plan's revision_guard "
                "then reads unavailable rather than active, and the compare-and-swap is not "
                "armed at all — so a caller who wants the guard takes the snapshot with the "
                "revision the read handed back. THE API DOMAIN TRAVELS TOO, inside the same "
                "digest, because it is the one fact a successor process cannot derive from "
                "the token, the revision or the blocks: a token does not say larksuite.com "
                "from feishu.cn. It is a routing fact and NOT a credential, and no app id, "
                "secret or access token is ever written into a snapshot. An artefact "
                "carrying no domain (taken without one, or written by a release older than "
                "the field) still loads and reports api_domain None rather than a guessed "
                "default, and the format_version did not move for it, so an older release "
                "still reads an artefact this one writes. Offline end to end: it reaches no "
                "endpoint and needs no credentials."
            ),
            applies_to=["docx-read"],
        ),
    }

