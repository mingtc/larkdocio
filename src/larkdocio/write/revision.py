"""larkdocio.write.revision — the whole-document staleness guard vocabulary (LD-139 / D9).

**The gap this closes.** Per-anchor ``STALE_ANCHOR`` (Decision (e)) re-validates
*the anchor* immediately before each write — and is **structurally blind to drift AROUND
it**. A human inserting three paragraphs above a still-matching anchor leaves the quote
present (and a by-id block's text byte-identical), so every per-anchor precondition passes
while the **position** the plan computed has moved: the batch lands mispositioned content
and reports success. Positioning is a property of the **document**, so only a
whole-document check can see it.

**The contract (D9, maintainer-settled — "warn then fail instead of trying to accommodate
disastrous results").** The plan caches the document's ``revision_id`` at plan time; the
apply engine **re-reads it immediately before the batch**; **any** difference refuses the
**ENTIRE** batch — ``STALE_DOCUMENT``, **zero writes issued** — with an actionable
``detail`` naming the drift and instructing *re-download and re-plan*. There is **no partial
application** and **no auto-mapping**: the engine never re-locates an anchor, re-indexes a
position, or otherwise accommodates a document that changed under it. That was rejected as
"messy"; exactly-one-or-refuse extends to the whole document. **Accepted cost (recorded):**
a busy document refuses more often — a re-plan costs a read, a mispositioned write costs a
corrupted document.

**Never silently off (the LD-132 pattern, mirrored from sheets' ``STALE_SHEET``).** A guard
a consumer cannot see is worse than no guard: sheets shipped a compare-and-swap that
compared ``0 == 0`` and no-op'd invisibly (dogfood F7). So the availability of the anchor is
stated explicitly — :func:`revision_guard_status` / :func:`revision_guard_semantics`,
surfaced as ``Plan.revision_guard`` + the WHY in ``Plan.revision_guard_detail`` and carried
into the apply-log. The status is **derived from the revision** wherever it is read, so
there is no writable slot a future code path could leave blank or stamp with a lying
``"active"``.

**The availability finding (LD-139 AC1, characterized live 2026-07-28 on a
harness-self-provisioned disposable doc).** ``GET /open-apis/docx/v1/documents/{id}`` →
``data.document`` carries ``revision_id`` (int; keys ``display_setting`` / ``document_id`` /
``revision_id`` / ``title``). It is **1** on a fresh document, **advances one per write**
(create → 1, after ``create_children`` → 2, after ``_patch_block`` → 3), and is **stable
across reads** — exactly the monotonic, read-inert anchor a compare-and-swap needs. It also
comes back from the **reader's own** ``GetDocumentRequest`` leg
(:meth:`larkdocio.read.client.Client.get_docx_content` → ``document.revision_id``), so the
plan-time anchor costs **zero extra calls** on the read that builds the tree.

**Capture ordering matters (and is deliberately conservative).** Capture the revision from —
or *before* — the read that builds the node tree, never after: if an edit lands between the
tree read and the capture, an *after* capture would anchor on the drifted revision and the
CAS would pass over a stale tree. Anchoring on the earlier value can only make the guard
refuse a document that did change, which is the safe direction.

Dumb, dependency-free vocabulary (standard library only, plus the shared marker leaf) so both
the previewer and the apply engine can share one source for the marker, the WHY, and the
refusal wording.

**The two markers and the classifier now live in :mod:`larkdocio.common.staleness`** (LD-143 /
T1) — ONE core shared with the sheets surface, which carried a drifted copy of the same
vocabulary. This module **re-exports** them unchanged, so every existing import path
(``larkdocio.write.revision``, ``larkdocio.write``) still resolves; the classification docx
already applied — a **negative** anchor is not an anchor — is the rule the shared core adopted.
What stays here is the docx-specific half: :func:`revision_guard_semantics` (this surface's
disclosure wording) and the two refusal-``detail`` builders.
"""

from larkdocio.common.staleness import (  # noqa: F401 — re-exported: this IS the public path
    REVISION_GUARD_ACTIVE,
    REVISION_GUARD_UNAVAILABLE,
    revision_guard_status,
)

#: The consumer-facing concurrency doctrine, in the **guide's own words** (LD-138 shipped the
#: prose, LD-139 the mechanism). One source, so the refusal a consumer reads at 2am says
#: exactly what the shipped guide says.
CONCURRENCY_WARNING = (
    "Do not edit the document concurrently."
)

#: The recovery, verbatim in every ``STALE_DOCUMENT`` detail — a refusal exists to be
#: recovered from (the LD-131 mandatory-detail contract).
REPLAN_GUIDANCE = (
    "re-download the document, rebuild the node tree, and re-plan against it"
)

#: The guard's WINDOW, stated where a consumer meets the guard (LD-566 / F18). DERIVED, not
#: asserted: the plan's anchor is captured at the read that builds the tree
#: (:func:`larkdocio.write.preview.dry_run`) and apply compares that cached value against ONE
#: live read taken immediately before the batch (:func:`larkdocio.write.apply.apply`) — so text
#: that landed before the plan is already inside ``cached`` and the comparison is
#: ``cached == cached``. Present tense: this is what the guard does, not a promise.
GUARD_WINDOW = (
    "This guard's window is plan-to-apply: it compares the revision the plan was built on "
    "against the revision read immediately before the batch, so it sees an edit that lands "
    "inside that window and nothing else. Text that arrived before the plan is already part "
    "of the tree the plan was computed from, the two revisions it compares are the same one, "
    "and no refusal is raised for it."
)

#: What following the recovery COSTS the other writer, beside the recovery itself (LD-566 /
#: F17): a correct re-plan is computed against a tree that now contains somebody else's words.
#: The surgical route is named WITH its four limits (``model/requests.py`` —
#: :class:`~larkdocio.write.model.requests.SubSpanEditRequest`), and the clause stays actionable
#: for the caller that route turns away.
REPLAN_CARRIES_FOREIGN_TEXT = (
    "Read the block before you re-plan it: the re-downloaded tree already contains the other "
    "writer's words, and a whole-block edit re-planned against it replaces the block entire, "
    "carrying those words away with no further refusal. A sub-span edit preserves them where "
    "it applies — it rewrites only the quoted span and leaves every surrounding run "
    "byte-identical — and it is bounded: narrative blocks only (a span inside a table cell is "
    "out of scope), the span must occur exactly once in the block, and a span crossing runs of "
    "differing style or overlapping a non-text inline refuses span_not_splittable. Where it "
    "does not apply or refuses, the whole-block edit is still yours to make: build its "
    "replacement text out of the block you just re-read, so it carries the other writer's "
    "words instead of dropping them."
)

#: Why the engine refuses instead of adjusting — repeated in the detail so nobody goes
#: looking for a flag that would "just make it work".
_NO_AUTO_MAPPING = (
    "The engine never re-locates anchors, re-indexes positions, or otherwise accommodates a "
    "document that changed under a plan: it refuses, because a mispositioned write is worse "
    "than a refusal. A re-plan costs one read"
)


def revision_guard_semantics(revision) -> dict:
    """The complete, JSON-serializable staleness disclosure for a plan-time document
    ``revision`` — ``{"status", "detail"}``.

    ONE source for the marker and its WHY, so the plan, its JSON, the apply-log and the docs
    cannot drift apart. **Both** statuses carry a non-empty ``detail`` (the
    mandatory-detail discipline: a marker with no WHY is a riddle), and the unavailable one
    names the knob that activates the guard rather than merely reporting bad news.
    """
    status = revision_guard_status(revision)
    if status == REVISION_GUARD_UNAVAILABLE:
        detail = (
            f"the whole-document compare-and-swap (STALE_DOCUMENT) is UNAVAILABLE on this "
            f"plan: the plan-time document revision is {revision!r}, which cannot anchor a "
            f"comparison. Pass document_revision_id=<the revision_id of the document you "
            f"read> to dry_run(...) to activate it — the reader hands it to you for free as "
            f"document.revision_id from get_docx_content(...), and note that -1 is the "
            f"'against latest' request pin, not a revision. Until then this batch is guarded "
            f"only by the per-entry STALE_ANCHOR re-validation, which re-checks each "
            f"anchored block but CANNOT see drift around it (an insertion above a "
            f"still-matching anchor moves where your content lands). The guard "
            f"self-activates on the next plan that carries a revision."
        )
    else:
        # ARMED IS NOT FIRED (LD-561). This detail rides a plan that has refused nothing, so
        # the two halves are lexically separated: first the guard's STATE, then — marked as a
        # conditional and in the conditional mood — what firing WOULD do. Every load-bearing
        # phrase of the original survives (the five pinned by the suite's consumer-dialect
        # guard, in the source repository); what changed is that the second clause can no longer be read
        # as a report of this batch's outcome.
        detail = (
            f"the whole-document compare-and-swap (STALE_DOCUMENT) is ARMED on the "
            f"plan-time document revision {revision!r}. That is the guard's state, not a "
            f"report about this batch: nothing has been refused. IF IT EVER FIRES, this is "
            f"what it would do: apply re-reads the document's revision_id immediately "
            f"before the batch and, if it differs at all, it would refuse the ENTIRE batch "
            f"with ZERO writes issued. The per-entry STALE_ANCHOR re-validation still "
            f"applies on top of it."
        )
    return {"status": status, "detail": detail}


def stale_document_detail(*, document_id, cached, live) -> str:
    """The mandatory ``detail`` for a drift refusal — what changed, what was NOT done, and
    the recovery (LD-131). Named values on both sides so a consumer can log the drift."""
    return (
        f"document {document_id} changed under the plan: its revision_id was {cached!r} when "
        f"the plan was built and is {live!r} now. The ENTIRE batch was refused and ZERO "
        f"writes were issued — nothing in this document was modified. {CONCURRENCY_WARNING} "
        f"An edit that lands between the plan and the apply can move where your content "
        f"goes even when every anchor still matches, so the whole batch refuses rather than "
        f"land content in a position that has moved. {GUARD_WINDOW} To recover, "
        f"{REPLAN_GUIDANCE}. {REPLAN_CARRIES_FOREIGN_TEXT} {_NO_AUTO_MAPPING}."
    )


def unconfirmable_document_detail(*, document_id, cached, why) -> str:
    """The mandatory ``detail`` for the **conservative** refusal: the plan had an anchor but
    the live revision could not be established, so the document cannot be *confirmed*
    unchanged. Refusing an unverifiable batch is the whole posture of D9."""
    return (
        f"document {document_id}'s current revision_id could not be read immediately before "
        f"the batch, so what the plan previewed (revision {cached!r}) cannot be confirmed "
        f"still current: {why}. The ENTIRE batch was refused and ZERO writes were issued — "
        f"nothing in this document was modified. {CONCURRENCY_WARNING} {GUARD_WINDOW} "
        f"To recover, {REPLAN_GUIDANCE}. {REPLAN_CARRIES_FOREIGN_TEXT} {_NO_AUTO_MAPPING}."
    )
