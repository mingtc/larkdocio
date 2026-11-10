"""THE LIVE-GATE REGISTRY (LD-222 / refactor audit 2026-08-01 § T5a) — one row per
``tests/test_live_*.py``, so the *absence* of discipline is data instead of silence.

The house invariant is **"a live gate never silently passes"** (PROJECT.md § The binding QA
gate). Every credential-gated gate is deselected by default, so nothing about it runs on an
ordinary ``pytest -q`` — which is exactly why most of them grew an **offline companion**: a
sibling ``*_offline.py`` that checks statically what the gate's safety rules claim (it
self-provisions a disposable, it deletes in a ``finally``, it never addresses the canary or a
real document, it really is credential-gated).

That habit was hand-grown and, by the 2026-08-01 audit, **the gap was outrunning the
scaffolding**: 27 gates, 14 companions, **13 gates with no companion file at all** — and all
four gaps the v1.24.0 arc created were the arc's own new gates. Absence looks exactly like
"nothing to do here", so it never reddened anything.

**What happened next is the point of having the data.** The 2026-08-03 audit re-priced the
list off these rows, and the human maintainer split it (MORNING RULINGS): **buy the four v1.24.0-arc
companions** — the only four whose absence was a discipline failure rather than a pre-pattern
artifact — and **ratify the other nine** as reasoned, parked in ``dev/downtime-queue.md`` for
downtime re-assessment. LD-245 bought them; the four rows below flipped ``DECLARED_NONE`` →
``HAS_COMPANION`` in the same change, and the published table shrank 14 → 10 on its own. The
nine ratified gaps keep their reasons **verbatim** — a ratified gap is a decision, not an
oversight, and rewriting its reason would erase the decision.

This module turns that absence into **data**. Every discovered ``tests/test_live_*.py`` gets
exactly one :class:`GateRow`, classified into one of six :class:`Kind` values and carrying a
**written reason**. ``tests/test_gate_registry.py`` then holds the mapping **exhaustive
in both directions over a globbed file set**, so a new live gate cannot enter the tree without
somebody making — and recording — a decision about its offline mirror.

The six kinds
-------------

``HAS_COMPANION``
    A live gate with a separate ``*_offline.py`` companion file. 24 of these.
``COMPANION``
    The companion file itself, pointing back at its gate. 24 of these; the pairing is checked
    bidirectionally.
``IN_FILE_MIRROR``
    The other spelling of the invariant: the gate keeps its always-on discipline self-check
    **inside the gate file**, below the ``live_write``-marked round-trip. One of these
    (``test_live_write_mermaid_create_gate``); the marker is grepped out of the gate's text,
    so deleting the self-check reddens the guard.
``DECLARED_NONE``
    A live gate with **no** offline mirror of any kind. 9 of these — the nine the maintainer ratified
    on 2026-08-03. The ``reason`` field says what is therefore unverified offline.
``HARNESS``
    A live *provisioning* harness rather than a gate over shipped behavior. 3 of these; the
    audit's 27-gate arithmetic excludes them, and they are excluded **per file, with a
    reason**, never by a name pattern.
``OFFLINE_SUPPORT``
    Offline, but not one of the gate companions:
    ``test_live_write_offline.py`` covers the W0 *harness* scaffolding and
    ``test_live_base_disposable_harness_offline.py`` the Base one — each subject is a
    ``HARNESS`` row, not a gate, which is why neither is counted a companion.

What is deliberately NOT here
-----------------------------

* **The nine remaining companions (the ratified rest of T5c).** A coverage-*scope* call the maintainer
  has already made: ratified as reasoned, parked in ``dev/downtime-queue.md``. This registry is
  the artifact that prices them; it writes none of them. (It priced the four LD-245 did buy the
  same way.)
* **T5b — extracting ``tests/gate_discipline.py``** and normalizing the spellings.
  Dropped for this tranche; the registry is what will tell us whether the carriers actually
  want one shape. Four fresh companions may LOOK like the moment to extract one — LD-245
  deliberately did not, and repeating one small local ``_src()`` helper per file is the house's
  own precedent, not an oversight.
* **Any change to what a gate asserts, skips or provisions.** Purely additive.
* ``test_live_comments_read_gate_offline.py`` (module-scoped fixture + forbidden-env sweep)
  is **classified and flagged** ``first_pass_excluded``, not restructured — both audits made
  the identical call, and the flag is how that call survives into T5b.

The published gap list
----------------------

The 10 gates with no separate companion **file**, rendered from the rows below by
:func:`render_gap_table` and held byte-identical to it by the guard — so it can be read
without running anything. ``*`` marks a gap created by the v1.24.0 arc; **no row carries one
any more**, because the arc's four were the four LD-245 bought.

.. BEGIN GENERATED GAP TABLE
|  # | live gate (no separate offline companion file) | kind           | added by |
|---:|------------------------------------------------|----------------|----------|
|  1 | test_live_canary                               | DECLARED_NONE  | —        |
|  2 | test_live_comment_anchor_zoo_arm               | DECLARED_NONE  | —        |
|  3 | test_live_contacts_lookup                      | DECLARED_NONE  | —        |
|  4 | test_live_sheets_dimension_write_gate          | DECLARED_NONE  | —        |
|  5 | test_live_sheets_dropdown_write_gate           | DECLARED_NONE  | —        |
|  6 | test_live_sheets_formula_write_gate            | DECLARED_NONE  | —        |
|  7 | test_live_sheets_merge_tab_write_gate          | DECLARED_NONE  | —        |
|  8 | test_live_sheets_rich_write_gate               | DECLARED_NONE  | —        |
|  9 | test_live_sheets_structural_write_gate         | DECLARED_NONE  | —        |
| 10 | test_live_write_mermaid_create_gate            | IN_FILE_MIRROR | —        |
.. END GENERATED GAP TABLE

Read it as: **9 gates have no offline mirror at all** — the nine the maintainer ratified on 2026-08-03
as reasoned rather than neglected (six legacy sheets write arms and three read-only arms, all
pre-pattern artifacts) — and a 10th has a mirror but keeps it in-file rather than in a
companion file. **None of the nine is a v1.24.0-arc gate**: the arc's own four, which were the
discipline failure rather than the artifact, were bought by LD-245 and are now
``HAS_COMPANION`` rows. The cohort is still nameable as :data:`ARC_V1_24_0_COHORT` so the
history does not evaporate with the gap.

The published media price list (LD-505)
-------------------------------------

The **other** cost of a run: which of these files UPLOAD BYTES, and what that upload leaves
behind. Rendered from :data:`MEDIA_VERDICTS` by :func:`render_media_mint_table` and held
byte-identical to it by ``tests/test_media_minting_guardrail.py``, so the price can be read
without running anything. Everything not listed mints nothing, **with a written reason** -
141 files, each named literally.

.. BEGIN GENERATED MEDIA TABLE
|  # | live file whose run UPLOADS BYTES     | verdict                |
|---:|---------------------------------------|------------------------|
|  1 | test_live_base_media_gate             | PERMANENT_MEDIA        |
|  2 | test_live_base_relational_gate        | PERMANENT_MEDIA        |
|  3 | test_live_docx_image_authoring_gate   | PERMANENT_MEDIA        |
|  4 | test_live_docx_media_placement_gate   | PERMANENT_MEDIA        |
|  5 | test_live_drive_file_link_gate        | PERMANENT_MEDIA        |
|  6 | test_live_sheets_float_image_gate     | PERMANENT_MEDIA        |
|  7 | test_live_sheets_in_cell_image_gate   | PERMANENT_MEDIA        |
|  8 | test_live_sheets_ld472_doc_truth_gate | PERMANENT_MEDIA        |
|  9 | test_live_drive_bytes_leg_gate        | SWEEPABLE_DRIVE_OBJECT |
| 10 | test_live_drive_chunked_upload_gate   | SWEEPABLE_DRIVE_OBJECT |
| 11 | test_live_drive_folder_create_gate    | SWEEPABLE_DRIVE_OBJECT |
| 12 | test_live_drive_upload_identity_gate  | SWEEPABLE_DRIVE_OBJECT |
.. END GENERATED MEDIA TABLE

``PERMANENT_MEDIA`` is what the guardrail gates: those eight rings are loud-skipped unless
``LARKDOCIO_MEDIA_MINT_AUTHORIZED_BY`` names the issue that authorized the spend (the
mechanism is :mod:`media_guardrail`; the doctrine is ``requirements/DECISIONS.md`` D-97; what
already exists, for reuse instead of a fresh mint, is ``dev/media-token-ledger.md``).
``SWEEPABLE_DRIVE_OBJECT`` is **not** gated and that is deliberate - a drive file object is
removed by a shipped delete, media is not, and the library authors that distinction itself.

The registry is pure data plus derivations: it imports nothing beyond the standard library
and never imports, executes or reflects over a gate module.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

GAP_TABLE_BEGIN = ".. BEGIN GENERATED GAP TABLE"
GAP_TABLE_END = ".. END GENERATED GAP TABLE"


class Kind(enum.Enum):
    """How a discovered ``tests/test_live_*.py`` file relates to the offline invariant."""

    HAS_COMPANION = "live gate with a separate *_offline.py companion file"
    COMPANION = "the offline companion file of a live gate"
    IN_FILE_MIRROR = "live gate whose discipline self-check lives inside the gate file"
    DECLARED_NONE = "live gate with no offline mirror — reason recorded"
    HARNESS = "live provisioning harness, not a gate over shipped behavior"
    OFFLINE_SUPPORT = "offline file that is not one of the 14 gate companions"


@dataclass(frozen=True)
class GateRow:
    """One classified file. ``reason`` is required for every row — that is what keeps a
    classification from being a silent skip."""

    filename: str
    kind: Kind
    reason: str
    companion: str | None = None
    """For ``HAS_COMPANION``: the companion file that mirrors this gate offline."""
    subject: str | None = None
    """For ``COMPANION`` / ``OFFLINE_SUPPORT``: the live file this one mirrors."""
    mirror_marker: str | None = None
    """For ``IN_FILE_MIRROR``: text that must be present in the gate file itself."""
    arc_v1_24_0: bool = False
    """True for a gate the v1.24.0 arc created (the audit's ``*`` rows).

    Originally "a *gap* the arc created" — all four were unmirrored. LD-245 bought their
    companions, so the flag now means what it says: the **cohort** stays nameable in the data
    (:data:`ARC_V1_24_0_COHORT`) after it stops being a gap list. The gap table's ``added by``
    column renders it only for rows that are still gaps, which is why the four no longer carry
    a ``*`` there — they are no longer in the table at all."""
    first_pass_excluded: bool = False
    """True for the one file both audits keep out of the first normalization pass."""


# AC7 — authored, per file: the companion(s) both the 2026-07 and the 2026-08 audit keep out
# of any normalization pass. Classified here so a later T5b inherits the call instead of
# rediscovering it; the flag changes nothing about the file itself.
_FIRST_PASS_EXCLUDED_COMPANIONS: dict[str, str] = {
    "test_live_comments_read_gate_offline.py": (
        " FIRST-PASS EXCLUDED: its module-scoped fixture and forbidden-env sweep make it the "
        "one carrier both audits keep out of any normalization pass — classify it, do not "
        "restructure it (LD-222 AC7)."
    ),
}


#: The four gates the v1.24.0 arc shipped. Every one of them shipped WITHOUT its offline
#: mirror — the only four gaps in the 2026-08-03 audit that were a discipline failure rather
#: than a pre-pattern artifact — and LD-245 (T5c at the maintainer-bought scope) bought all four
#: companions. Kept as data so the cohort stays nameable now that it is no longer a gap list.
ARC_V1_24_0_COHORT: frozenset[str] = frozenset({
    "test_live_sheets_border_write_gate.py",
    "test_live_sheets_freeze_write_gate.py",
    "test_live_sheets_style_write_gate.py",
    "test_live_sheets_tab_presentation_gate.py",
})


def _pair(gate: str, *, why: str) -> tuple[GateRow, GateRow]:
    """A gate and its ``*_offline.py`` companion, wired to each other."""
    companion = f"{gate.removesuffix('.py')}_offline.py"
    note = _FIRST_PASS_EXCLUDED_COMPANIONS.get(companion, "")
    return (
        GateRow(
            filename=gate,
            kind=Kind.HAS_COMPANION,
            reason=why,
            companion=companion,
            arc_v1_24_0=gate in ARC_V1_24_0_COHORT,
        ),
        GateRow(
            filename=companion,
            kind=Kind.COMPANION,
            reason=f"the always-on offline half of {gate.removesuffix('.py')}.{note}",
            subject=gate,
            first_pass_excluded=bool(note),
        ),
    )


_PAIRED: tuple[GateRow, ...] = tuple(
    row
    for gate, why in (
        # LD-245 / T5c at the maintainer-bought scope — the four v1.24.0-arc gates. Each shipped
        # WITHOUT its mirror (the arrears the 2026-08-03 morning ruling bought); each now has
        # one, and the `why` says what the companion pins rather than what used to be missing.
        (
            "test_live_sheets_border_write_gate.py",
            "the LD-189 border arm's companion pins the two the registry named as unpinned — "
            "the disposables-only invariant and the finally-delete close-out — plus the arm's "
            "shape: the shipped apply engine in, and the raw xl/styles.xml border read beside "
            "the shipped reader's own bold/fill verification, with the not-verifiable "
            "disclosure pinned in BOTH directions.",
        ),
        (
            "test_live_comments_read_gate.py",
            "the comments-read gate's safety rules (comments only on a file it created "
            "itself, both destroyed) are pinned statically by its companion.",
        ),
        (
            "test_live_sheets_disposition_gate.py",
            "the LD-148 disposition arm's disposables-only invariant (D7) is proven offline "
            "by its companion.",
        ),
        (
            "test_live_sheets_final_gate.py",
            "the arc's final gate ships both shape guards and the differ's own teeth in its "
            "companion.",
        ),
        (
            "test_live_sheets_ghost_tab_gate.py",
            "LD-383's read-only ghost-tab arm: its companion pins the two rules a READ gate "
            "against a spreadsheet it does not own lives by — that it writes nothing, and "
            "that the only workbook it addresses is the designated disposable (never the "
            "consumer's, which is evidence and not a target) — plus the arm's shape: a "
            "synthetic ghost id, the live 90215 skip, AND the clean control read without "
            "which a skip-only arm proves half of what it claims.",
        ),
        (
            "test_live_sheets_freeze_write_gate.py",
            "the LD-186 freeze arm shipped its write and its own read leg together, so its "
            "companion pins BOTH: the gated FreezePanes chain with the live PATCH invariant "
            "and the typed out-of-range refusal proven inert, and the shipped graceful read "
            "leg in both resolved states — plus the disposables-only provisioning the registry "
            "recorded as unmirrored.",
        ),
        (
            "test_live_sheets_lifecycle_gate.py",
            "the LD-176 lifecycle arm's self-provision / zero-orphan close-out is pinned by "
            "its companion.",
        ),
        (
            "test_live_base_read_arm.py",
            "LD-247's single Base read arm ships WITH its mirror rather than adding an "
            "eleventh gap — the 2026-08-03 ruling's direction, applied to a new arm instead "
            "of only to arrears. The companion pins what the arm's posture claims and a live "
            "run cannot: that it is READ-ONLY by construction (every registered op declares "
            "`mutates: False`, and the arm asserts that before its first call), that it never "
            "names a write credential or a write verb, that it targets the Scratch Base env "
            "var and never the canary doc or a real document, that it skips LOUDLY when the "
            "URL or the read grant is absent, and that it re-reads `table.revision` as its "
            "no-write proof.",
        ),
        (
            "test_live_base_read_raw_values.py",
            "LD-293's opt-in RAW value arm ships WITH its mirror, the direction every Base "
            "arm has taken since LD-247. The companion pins what the arm's posture claims and "
            "a live run cannot: that it is READ-ONLY by construction (every registered op "
            "declares `mutates: False`, asserted before the first call), that it names no "
            "write credential and no write verb, and — the one this arm adds to the pattern — "
            "that it PROVISIONS NOTHING and UPLOADS NOTHING, because retention keeps a "
            "payload the read already received and an arm that had to create a Base, a record "
            "or a file to prove it would be proving a different surface. Beside that the "
            "usual: the Scratch Base env var and no other target, a LOUD skip when the URL or "
            "the read grant is absent, `table.revision` re-read as the no-write proof, and "
            "the surface's own gate coverage asserted to NAME this module — a live arm "
            "outside the registry that prices live coverage is coverage nobody can price.",
        ),
        (
            "test_live_base_field_migration.py",
            "LD-291's guided column-type migration arm ships WITH its mirror, the direction "
            "every Base arm has taken since LD-247 — and on this one the mirror carries more "
            "weight than usual, because the arm's central claim is a NEGATIVE: that a copy "
            "which did not round-trip leaves the source column standing. The companion pins "
            "what a credential-less run cannot: that the forced defect is REAL (a wrapper over "
            "the shipped write client which changes the values it writes, not a stand-in that "
            "produces a refusal on request), that the mismatch arm asserts BOTH halves of the "
            "fence (the column still LISTED and its VALUES unchanged — a presence check alone "
            "would pass over an emptied column), that the delete and the rename are asserted "
            "never-attempted, and that each of the three arms opens its OWN disposable Base. "
            "Beside them the usual: disposables only with no configured target reachable from "
            "any code path — sharpest here, since the verb under test deletes a populated "
            "column — a LOUD skip, no sleep, and a committed capture.",
        ),
        (
            "test_live_base_write_arm.py",
            "LD-255's single Base WRITE arm ships WITH its mirror, the same direction the two "
            "Base read arms took. Its companion carries the posture the live run cannot "
            "verify by not running, and one thing neither Base arm before it needed: that the "
            "arm writes ONLY a Base it self-provisioned through `base_write_harness`, which "
            "names no configured target at all, and that the provisioner deletes in a "
            "`finally`. Beside that the usual: MUTATING by construction asserted before the "
            "first call (with the read registry still proven read-only in the same breath, "
            "which is the whole reason there are two registries), the WRITE credential pair "
            "and never the read one, a LOUD skip when the grant is absent, and a call budget "
            "asserted rather than intended.",
        ),
        (
            "test_live_base_canary.py",
            "LD-252's Base canary — THE L1 GATE for the Base surface — ships WITH its mirror "
            "for the same reason LD-247's arm did, and its companion carries more than the "
            "usual posture checks because three of the story's obligations are only checkable "
            "offline: that D3's liveness definition really is in the gate's docstring in plain "
            "words AND agrees with `BASE.md` register rows 8/9/10; that `capabilities()`'s "
            "gate coverage for any Base surface names live modules that exist and are "
            "classified here (written order-independently, so it holds both before and after "
            "LD-251 registers the surface); and that the register survived the gate. Beside "
            "them the posture: READ-ONLY by construction asserted before the first call, no "
            "write credential or verb, the Scratch Base env var and no other target, a LOUD "
            "skip, `table.revision` re-read as the no-write proof, and — the one this gate "
            "adds to the pattern — that it pins SAME-RUN byte-identity and commits no "
            "cross-time baseline, because a human hand-authors the specimens on that Base.",
        ),
        (
            "test_live_sheets_revision_guard_gate.py",
            "the LD-132 revision-guard arm's disposables-only invariant (AC7) is pinned by "
            "its companion.",
        ),
        (
            "test_live_sheets_style_gate.py",
            "the L2 style-leg gate's shape and credential-gating are pinned by its companion.",
        ),
        (
            "test_live_sheets_style_write_gate.py",
            "the LD-188 cell-style arm's companion pins the arm's SHAPE — typed request → "
            "dry_run → apply, verified through the shipped export reader rather than the "
            "write's own echo, surgical against a guard neighbour and inert on the typed "
            "unknown-tab refusal — and its disposables-only invariant.",
        ),
        (
            "test_live_sheets_tab_presentation_gate.py",
            "the LD-187 presentation arm's companion gives the MULTI-TAB provisioning — the "
            "most intricate in the set — its own tests: the extra tabs added through the "
            "shipped gated AddTab, the three-tab shape asserted before anything depends on it, "
            "and every tab hidden along the way shown again; around them the three ops' "
            "independent read-back, the three typed refusals proven inert, and the "
            "disposables-only invariant.",
        ),
        (
            "test_live_sheets_write_gate.py",
            "the Sheets value-write gate's shape is pinned by its companion, which also "
            "carries the values-leg differ's own guards.",
        ),
        (
            "test_live_write_anchor_by_id_gate.py",
            "the S4 by-id anchoring gate's discipline is the automatable half of LD-137 AC6, "
            "carried by its companion.",
        ),
        (
            "test_live_write_authoring_gate.py",
            "the authoring gate's companion is the deepest of the set — shape guards plus "
            "modelled concurrency layers.",
        ),
        (
            "test_live_write_comment_op_gate.py",
            "the comment-op gate's safety rules are checked statically by its companion "
            "(the 14th carrier, added after the previous audit).",
        ),
        (
            "test_live_write_table_create_gate.py",
            "the S2 table-creation gate's discipline is the automatable half of LD-135 AC6, "
            "carried by its companion.",
        ),
        (
            "test_live_write_batched_table_fill_gate.py",
            "LD-481's BATCHED-FILL arm ships with its companion. The fill's call shape is "
            "already pinned offline against an injected transport "
            "(tests/test_batched_table_fill.py), so what this companion pins is what only a "
            "shape check can keep honest about the LIVE arm: that the grid stays the "
            "CONSUMER'S (6×36 = 216 cells — above the superseded 200-cell cap and above the "
            "create endpoint's per-axis ceiling, so a grid that quietly shrank under either "
            "would pass while testing nothing), that the PIN is the API CALL COUNT and never "
            "the clock (a wall-clock assertion anywhere in the gate reddens this companion, "
            "because elapsed seconds are evidence for the Activity log and a timing threshold "
            "in a suite is a flake generator), that the pin is the COST CLASS and stays "
            "FAMILY-AGNOSTIC (LD-578: the original ⌈cells/48⌉ batch_update pin went stale the "
            "day LD-482 lifted this grid into one /descendant call, so the companion now pins "
            "that the arm counts MUTATING calls of any family, keeps the 463-call reason, and "
            "does not restate the LD-482 arm's SHAPE claim), and that the verdict is "
            "a fresh read-back in ROW-MAJOR order at the spike's own four probe points.",
        ),
        (
            "test_live_write_table_growth_gate.py",
            "the LD-431 gate authors grids past the create endpoint's per-axis ceiling on "
            "BOTH axes; its companion pins that shape offline, because a gate whose grids "
            "quietly shrank inside the ceiling would pass while testing nothing.",
        ),
        (
            "test_live_write_w1_gate.py",
            "the W1 gate's shape is pinned by the original companion of the pattern.",
        ),
        (
            "test_live_write_w2_gate.py",
            "the W2 table-cell gate's shape is pinned by its companion.",
        ),
        (
            "test_live_write_w3_gate.py",
            "the W3 create/delete/sub-span gate's shape is pinned by its two-part companion.",
        ),
        # LD-236 — the four round-trip arms. Every one of them was given a
        # companion DELIBERATELY rather than declared unmirrored: the load-bearing claim of
        # this ring is the disposables discipline (self-provisioned only, restored, trashed in
        # a finally, ledgered, re-queried at close), and that is precisely what a
        # credential-gated file cannot prove on an ordinary run. Declaring four fresh gates
        # DECLARED_NONE would have re-created, in one tranche, the exact absence LD-222 turned
        # into data — and the four companions keep the published gap table byte-identical.
        # LD-492 — the round-trip VERB's arm. Paired for the same reason the four arms above
        # are: the discipline it has to keep is the disposables discipline plus LD-493's
        # caller-supplied destination, and a credential-gated file proves neither on an
        # ordinary run. Its companion carries one thing the others do not — the proof that the
        # SKIP PATH fires and names its variable — because this gate's live half was parked at
        # landing for a missing precondition, and a parked gate that cannot be shown to skip
        # loudly is indistinguishable from one that passed.
        (
            "test_live_write_roundtrip_verb_gate.py",
            "the round-trip verb's arm runs the SHIPPED verb (not the engine under it), and "
            "its companion pins that: the rehearsal writes nothing, the applied push is "
            "surgical, the verb's own compose-equivalence read-back verified something, the "
            "disposable is created into the caller-supplied folder, and the skip path fires "
            "by name when that folder is unset.",
        ),
        # LD-482 — the ONE-CALL table subtree's arm. Paired, and for a reason this registry
        # has not carried before: the gate's binding claim is POSITIONAL, and the offline
        # half of a positional claim can only ever be the engine's own arithmetic against its
        # own double. So the companion pins the things that make the live half worth running —
        # that the batch is MIXED (a table alone in its batch cannot show the same-parent
        # drift the positional repair exists for), that the grid stays inside the one-call
        # envelope (outside it the gate would silently exercise the other route), and that the
        # atomicity leg reads back that a refused subtree left NOTHING rather than inferring
        # it from the error.
        (
            "test_live_write_one_call_table_gate.py",
            "the one-call table arm authors a whole 216-cell subtree in a single "
            "`/descendant` call inside a MIXED batch, and its companion pins what an offline "
            "run cannot judge: the grid is inside the measured one-call envelope, the batch "
            "carries two entries with two anchors and asserts each landed beside its OWN, the "
            "verdict is a fresh read-back of the live child order plus row-major cells, and "
            "the atomicity leg provokes the refusal ONE cell past the envelope with a passing "
            "control and reads the document back to prove nothing was created.",
        ),
        (
            "test_live_write_round_trip_surgical_gate.py",
            "the surgical round-trip arm's discipline (self-provisioned disposable, shipped "
            "chain, restore-to-baseline, zero-orphan close-out) is pinned by its companion.",
        ),
        (
            "test_live_write_round_trip_conservation_gate.py",
            "the conservation arm's companion pins the two things the maintainer ruling made "
            "non-negotiable: an opaque subject compose() can create, and BOTH omission shapes.",
        ),
        (
            "test_live_write_round_trip_stale_document_gate.py",
            "the live STALE_DOCUMENT arm's companion pins the second client, the armed "
            "revision guard, the measured zero writes and the recovery leg.",
        ),
        (
            "test_live_write_todo_done_edit_gate.py",
            "the todo-checkbox arm's companion pins the four things that make it a proof of "
            "the SHIPPED op rather than a restatement of the round-5 measurement the builder "
            "cites: the read-back is of the RAW block payload (align / folded / a nested "
            "child's identity are not all projected into Markdown, so a Markdown-only "
            "read-back cannot see what the field mask is claimed to leave alone), the "
            "untouched properties are compared BY NAME against their own pre-images, the flip "
            "is measured at ONE write (a second would mean the block's own text was rewritten "
            "and a styled item flattened for the sake of a boolean), and the arm restores — "
            "which is also the only way it exercises the mask writing False.",
        ),
        (
            "test_live_write_round_trip_no_marker_gate.py",
            "the no-marker arm's companion pins the two-representation scan and the "
            "adversarial control's scoping (non-emitted id, mid-line — the LD-239 fence).",
        ),
        (
            "test_live_write_round_trip_escape_identity_gate.py",
            "LD-454's fifth round-trip arm — the ESCAPE-IDENTITY one — ships with its "
            "companion like the four before it. The companion pins the ring discipline and "
            "three things this arm is the first to need. FIRST: that the arm asserts the "
            "projection REALLY escaped the untouched line before it claims anything about "
            "decoding it again — a subject that cannot exhibit the defect would pass green. "
            "SECOND: that the verdict is read back in BOTH representations, the reader's "
            "Markdown and the raw block payload, because the reader's own escaping is what "
            "hid this corruption for a release. THIRD: that the arm carries a FORCED-DEFECT "
            "control — the pre-fix compile re-created in place from the same plan, applied, "
            "and asserted to corrupt — and then repairs what the control broke, because a "
            "gate never shown failing on its own defect is not known to detect it and "
            "reverting the fix by hand is not something a later run will do.",
        ),
        (
            "test_live_write_anchor_whitespace_gate.py",
            "LD-455's ANCHOR SOFT-RETURN arm — the sixth round-trip member — ships "
            "with its companion like the five before it. The companion pins the ring "
            "discipline and three things this arm is the first to need. FIRST: that the arm "
            "proves its own PREMISE on the wire — that Lark really keeps a literal newline "
            "INSIDE one text run — before claiming either behaviour built on it, because an "
            "arm that assumed it would be asserting its author's belief and would pass green "
            "on a tenant that split the newline into two blocks. SECOND: that the refusal leg "
            "measures ZERO WRITES at the client boundary, since 'a near-miss refuses' means "
            "nothing was written and a later diff cannot prove that. THIRD: that the arm "
            "carries a FORCED-DEFECT control — the recipe's OLD line-splice idiom re-created "
            "in place, applied, and asserted to garble the sentence with plan.ok True — and "
            "then repairs the same block through the block-safe splice and reads it back, "
            "because the whole finding is that plan.ok was already True for the garbled one.",
        ),
        (
            "test_live_base_write_gate.py",
            "LD-260's BASE WRITE GATE — the Base record-write ENGINE, ships WITH its mirror, the "
            "direction every Base arm has taken. Its companion pins what a live run cannot "
            "verify by passing: that all three arms are present by name, that BOTH refusal "
            "arms prove zero calls STRUCTURALLY (apply is driven against a transport that "
            "raises on contact, so a refusal that failed to fire errors instead of writing), "
            "that the surgical claim is a per-cell set difference rather than a spot check, "
            "that the race arm uses a SECOND client and measures writes at the client "
            "boundary, that the oracle arm carries its positive control, that every write "
            "target comes from the harness and no configured target is read, that the "
            "provisioner deletes in a `finally`, that the skip is LOUD even though the shipped "
            "write-credential getter raises rather than answering with empties, and that the "
            "one arm which steps outside the disposables-only shape — the Stage refusal over a "
            "captured schema, because larkdocio ships no field authoring to create a Stage "
            "column with — says so in writing.",
        ),
        (
            "test_live_base_schema_arm.py",
            "LD-263's single Base SCHEMA arm — the app and table lifecycle — ships WITH its "
            "mirror, the direction every Base arm has taken. Its companion carries the usual "
            "posture (MUTATING by construction asserted before the first call with the read "
            "registry still proven read-only in the same breath, the WRITE pair and never the "
            "read one, a LOUD skip, a budget asserted rather than intended) and three things "
            "no earlier Base arm needed. FIRST: this arm's verbs include RENAME A BASE and "
            "COPY A BASE, so the disposables-only check is not politeness — the configured "
            "Scratch Base holds the only hand-authored Lookup / Email / Stage fields in "
            "existence and the API cannot recreate them. SECOND: the arm creates a Base the "
            "harness did not — the COPY — so the companion pins that the copy's token is "
            "written into the harness ledger on the statement after it exists, and that its "
            "title carries the greppable disposable prefix, because an unrecorded disposable "
            "is a lost one. THIRD: it pins that the arm uses the SHIPPED bounded settle "
            "rather than sleeping, which is the one defect the async-copy contract exists to "
            "forbid — and that register row 9's trash-not-purge fact is in the arm's own "
            "docstring, in agreement with the row, because a copy trashes exactly the way its "
            "parent does.",
        ),
        (
            "test_live_base_schema_fields.py",
            "LD-262's Base FIELD-authoring arm, shipped WITH its mirror like every Base arm "
            "before it. The companion carries the usual posture (MUTATING by construction "
            "asserted before the first call with the read registry still proven read-only in "
            "the same breath, the WRITE pair and never the read one, a LOUD skip, a budget "
            "asserted rather than intended, no destructive verb of its own) and three things "
            "this rung is the first to need. FIRST: the arm's verbs include CONVERT A "
            "COLUMN'S KIND, which rewrites every value in the column server-side and cannot "
            "be undone — so the disposables-only scan is the sharpest fence in the suite, and "
            "the companion additionally requires the arm's own docstring to name the "
            "conversion as the REASON the configured Scratch Base is off limits. SECOND: the "
            "companion pins that the conversion probe runs over a POPULATED cell and reads "
            "the value back, because an empty-column conversion answering code:0 is exactly "
            "the evidence the pack already had and exactly the evidence that does not settle "
            "whether a pair is lossless. THIRD: it pins that the Formula authoring probe "
            "records BOTH outcomes — success and refusal — since a probe that asserts only on "
            "success reports silence as a pass, and that a successful Formula field create is "
            "still not a licence to write a Formula CELL.",
        ),
        (
            "test_live_base_views.py",
            "LD-264's single Base VIEW arm — the view lifecycle and the maintainer's top functional "
            "ask, a filter that verifiably sticks. Its companion carries the usual posture "
            "(self-provisioned disposables only with no configured target named anywhere, the "
            "WRITE pair and never the read one, a LOUD skip, the harness's own sweep as "
            "teardown) and two things no earlier Base arm needed. FIRST: this arm's whole "
            "point is that a `code:0` is not evidence, so the companion pins that the arm "
            "carries a NEGATIVE CONTROL — a `property.group_info` PATCH that answers `code:0` "
            "and persists nothing — beside the positive result, on the SAME view, because a "
            "read-back verification that has never been shown detecting a swallow is not "
            "known to detect one. SECOND: the arm makes two RAW calls the shipped client "
            "cannot express, and the companion pins that they live in tests/ and reach only "
            "the view route — the typed dialect boundary is the feature, so a probe that "
            "needed a hole cut in the client would have been the defect.",
        ),
        (
            "test_live_base_read_filter.py",
            "the Base READ-FILTER arm — the differential proof that `filter` and `sort` are "
            "HONOURED by records/search, not merely accepted. Its companion pins the two "
            "things a credential-less run cannot see. FIRST: this is a READ arm against the "
            "configured Scratch Base, which is legitimate only while it stays a read — so the "
            "companion greps the arm for every write verb and write client and pins that the "
            "arm proves its own read-onlyness by COMPARING the app + table revisions across "
            "its run rather than by asserting the obvious. SECOND: the arm's whole value is "
            "the shape of its evidence, because on this endpoint an ignored body key answers "
            "code:0 with the whole table — so the companion pins that the arm compares two "
            "reads (a strict subset, a match-nothing filter returning nothing, and a desc "
            "sort that exactly reverses its asc, which is the one order statement that holds "
            "under any collation) and never reads a response code.",
        ),
        (
            "test_live_base_view_scoped_read.py",
            "the Base VIEW-SCOPED read arm — the `view_id` half of the same signature "
            "decision, and the only leg of it that has to WRITE. The companion pins why and "
            "where. WHY: the claim cannot be made against a view with no saved filter, since "
            "a filterless view returns the whole table exactly as an IGNORED view_id does — "
            "the shape of an earlier capture that was mistaken for evidence — so the arm "
            "builds a view whose filter admits some rows and not others, and the companion "
            "pins that the rows are checked against the filter the SERVER stored (read back "
            "through get_view) with that filterless-view control run beside it. WHERE: every "
            "token comes from the harness's own disposable_base, and the companion pins that "
            "the arm names no configured target at all — the Base holding the hand-authored "
            "specimens is a read fixture and is never a write target.",
        ),
        (
            "test_live_base_row_hierarchy.py",
            "LD-296's Base ROW-HIERARCHY arm — sub-items end to end, shipped with its mirror "
            "like every Base arm before it. The companion carries the usual posture (MUTATING "
            "by construction asserted before the first call with the read registry still "
            "proven read-only in the same breath, the WRITE pair and never the read one, a "
            "LOUD skip, the harness's own sweep as teardown, no destructive verb of its own) "
            "and three things this rung is the first to need. FIRST: this is the one route in "
            "the suite where a `code:0` is worth LESS than nothing — an unrecognised key "
            "inside `property.hierarchy_config` answers `code:0` and changes the view not at "
            "all — so the companion pins that the arm carries BOTH halves of the pairing on "
            "the SAME view: two patches whose read-back must be asserted to have MOVED, and "
            "the bogus-key control whose read-back must be asserted to have stayed put. "
            "SECOND: it pins that the DELIBERATE DEFECT is written ON THE WIRE — a cycle "
            "closed by a live record update — because a fixture cycle proves the traversal "
            "terminates and says nothing about whether Lark accepts one, which is the fact "
            "the whole disclose-never-refuse ruling rests on. THIRD: it pins that the arm "
            "names NO configured target at all, not even inside a fence: this rung reads no "
            "hand-authored specimen, so there is nothing to excuse, and it also pins that the "
            "shipped hierarchy module imports no transport — which is what makes 'the tree "
            "read costs no call' a claim the live arm never has to spend a call proving.",
        ),
        (
            "test_live_contacts_resolve_colleague.py",
            "the EMAIL -> open_id arm, shipped with its mirror on the terms every arm since "
            "the 2026-08-03 ruling has used: a new gate no longer means a new gap. What the "
            "companion carries is unusual for a READ arm and is the reason it earns one. The "
            "usual posture is there (READ-ONLY and reaching exactly one route, no write "
            "surface and no chat family, a LOUD skip per absent precondition rather than a "
            "silent pass). Added to it is the half no other companion needs: a REDACTION "
            "guard. This arm's second question can only be asked with a real user's live "
            "address, which is supplied from the environment and must never enter the "
            "repository -- and the copy of that assertion INSIDE the gate only runs with "
            "credentials, which is exactly the run a contributor without them never makes. So "
            "the always-on copy lives here. The companion also pins that the control arm "
            "reads the user_id OMISSION off the raw body rather than through the reader that "
            "already interprets it, and that the shipped dual-truth and measured-reach "
            "sentences are asserted by IDENTITY, so a paraphrase in the refusal reddens. The "
            "BEHAVIOUR the arm exercises is separately pinned offline against the committed "
            "probe bytes by tests/test_contacts_resolve_colleague.py.",
        ),
        (
            "test_live_base_minimal_form.py",
            "LD-317's MINIMAL-FORM SWEEP — one property-less create per FIELD_PROPERTY_SHAPES "
            "row, shipped with its mirror like every Base arm before it. The companion carries "
            "the usual posture (self-provisioned disposables only with no configured target "
            "named anywhere, the WRITE pair and never the read one, a LOUD skip, no "
            "destructive verb of its own) and three things this rung is the first to need. "
            "FIRST: it pins that the sweep is EXHAUSTIVE over the registry rather than a "
            "hand-picked subset — the defect it answers was a row nobody had looked at, so an "
            "arm that probed only the two reported suspects would have reproduced the defect's "
            "own shape one rung up. SECOND: it pins that an answer which is not a verdict "
            "about the BODY is retried before it is believed — the first run saw a transport "
            "9499 on two kinds that answer code:0 on the retry, and a hiccup written into a "
            "shipped registry flag is the same class of defect as the one being fixed. THIRD, "
            "and this is the half no other companion has: it pins that the SHIPPED registry "
            "agrees with the capture this arm writes — FieldPropertyShape.required is now "
            "DERIVED from it, so the companion re-derives every row offline and pins that no "
            "code path fills a missing property in on the caller's behalf.",
        ),
        (
            "test_live_base_destructive.py",
            "LD-265's Base DESTRUCTIVE arm — the only live gate in the suite whose verbs can "
            "DESTROY DATA, and it ships with its mirror like every Base arm before it. The "
            "companion carries the usual posture (MUTATING by construction asserted before "
            "the first call with the read registry still proven read-only in the same breath, "
            "the WRITE pair and never the read one, a LOUD skip, the harness's own sweep as "
            "teardown, no configured target named anywhere except in the fence that refuses "
            "it) and four things this rung is the first to need. FIRST: the arm's verbs are a "
            "column delete, a table delete and a table batch_delete, so the disposables-only "
            "scan is not politeness — the configured Scratch Base holds the only "
            "hand-authored Lookup / Email / Stage columns in existence and the API cannot "
            "recreate any of them. SECOND: the companion pins that every destructive leg "
            "reads its LOSS PREVIEW BEFORE it applies, in the source order, because a preview "
            "asserted after the delete proves nothing about what a caller could have known "
            "beforehand. THIRD: it pins that the DuplexLink leg asserts the mirror's "
            "disappearance IN THE OTHER TABLE — the blast radius leaving the table the caller "
            "named is the whole reason the preview is app-scoped, so an arm that checked only "
            "the named table would be testing the wrong claim — and that the table-delete leg "
            "asserts both halves of the silent dangle (table_id kept, table_name dropped, and "
            "the surviving table still reading with no error). FOURTH: it pins that no apply "
            "in the arm reaches a delete without consent minted from ITS OWN plan, and that "
            "the out-of-band leg asserts a REFUSAL and applies nothing at all — a refusal leg "
            "that then wrote something would be proving the opposite of its own claim.",
        ),
        (
            "test_live_base_schema_gate.py",
            "LD-266 — THE BASE SCHEMA GATE, the point at which the whole Base SCHEMA surface is "
            "proved against the real API and described honestly at the same time. It ships "
            "WITH its mirror, the direction every Base arm has taken, and the companion pins "
            "the four things a live run cannot verify by passing. FIRST: that the SURGICAL "
            "claim is a set difference over BOTH columns and cells — every column compared by "
            "identity and every existing cell of every existing row compared byte for byte — "
            "rather than a spot check, and that the restore leg compares against the baseline "
            "the arm captured before it touched anything. SECOND: that the cross-table arm "
            "reads its LOSS PREVIEW BEFORE it applies, in the source order, that the preview "
            "names BOTH tables by identity, and that the mirror's disappearance is asserted in "
            "the table the caller never named — the arm exists to make the safety claim TRUE "
            "rather than stated, so an assertion made after the fact would be proving nothing. "
            "THIRD: that the swallow control sits on the SAME view as the positive result "
            "(a control on a second view is a difference between two views), that it rides the "
            "library's own raw core from tests/ because nothing in the shipped view surface can "
            "build a group_info body at all, and that the not-persisted reading comes from the "
            "SHIPPED classifier rather than from the test's own opinion. FOURTH: that the "
            "allow-list refusal is driven through the shipped apply seam against a transport "
            "that RAISES ON CONTACT, so zero calls is structural rather than counted, that all "
            "four unauthorable kinds are covered, and that the live positive control is present "
            "— without it, zero calls could equally mean the path is broken. The credential "
            "aliasing rider is pinned as a sentence in the gate's own docstring, because a gate "
            "that quietly dropped it would invite exactly the over-read it exists to prevent.",
        ),
        (
            "test_live_base_media_gate.py",
            "LD-268's attachment OUT-OF-BAND leg — the first gate in the suite that mints "
            "PERMANENT, UNSWEEPABLE tenant residue, and it ships WITH its mirror like every "
            "Base arm before it. The live half proves the round trip is real by HASH (upload "
            "on both parent types → attach through the shipped encoder → read back → download "
            "→ identical sha256); the companion pins the four things a passing run cannot. "
            "FIRST: that parent_node — which is NOT a write target, so a guard watching write "
            "targets alone would miss it — can only ever be a Base the run created, driven "
            "against a transport that RAISES ON CONTACT so the refusal is structural rather "
            "than counted, and that neither the gate nor the harness reads any environment "
            "variable naming a Base. An upload's residue cannot be undone by deleting the "
            "Base, which is why this one is asserted twice. SECOND: that url / tmp_url — "
            "short-lived SIGNED links, credential-class — reach no assertion, no capture and "
            "no committed file, with the raw cell read exactly twice (once to scrub, once to "
            "prove the keys are really there) and a link-literal sweep over both the gate and "
            "the shipped module. THIRD: that the residue is DISCLOSED rather than swept — "
            "every minted token ledgered beside the call, no media delete leg anywhere "
            "(there is no verb that would back one), a legacy ledger entry still reading as a "
            "Base entry, and the orphans() == [] claim stated against the bitable liveness "
            "definition with media named as explicitly outside it. FOURTH: that this leg did "
            "not become a THIRD definition of 'download a Lark media token' — it builds the "
            "same pinned-SDK request class the reader's docx image leg builds, and the module "
            "records why it did not open a raw-HTTP media leg instead.",
        ),
        (
            "test_live_base_link_resolution.py",
            "LD-269's opt-in link resolver ships WITH its mirror, like every Base arm before "
            "it, and it exists for ONE thing an offline fixture cannot supply: proof that "
            "`records/batch_get` HONOURS its `record_ids` body key. R12 is the standing hazard "
            "on this family — `records/search` treats an unrecognised body key exactly like "
            "the bogus control — so a code:0 is not evidence a parameter did anything, and the "
            "arm therefore sends the parameter AND the parameter-free control at the same "
            "endpoint on the same table and asserts the answers differ. It also proves live "
            "that a missing record id is reported PER ID inside a successful body (the shape "
            "the whole `1254043 is normal` policy rests on) and that the resolver's disclosed "
            "call count equals the observed one. The companion pins what a credential-less run "
            "cannot: that the arm is READ-ONLY by construction (every registered op declares "
            "`mutates: False`, including the POST read this story added, asserted before the "
            "first call and proven again by re-reading `table.revision`), that the R12 control "
            "is really present rather than only claimed, that no write credential or write "
            "verb appears anywhere in it, that it targets the Scratch Base env var and never "
            "the canary doc, the scratch sheet, the block zoo or a self-provisioned "
            "disposable, and that BOTH its skip paths are loud — the credential one and the "
            "nothing-to-resolve one, because an arm that passes on a Base with no link cell "
            "proves nothing.",
        ),
        (
            "test_live_base_computed_provenance.py",
            "LD-270's computed-column provenance ships WITH its mirror, and it exists for ONE "
            "thing no offline fixture can supply: proof that a LIVE Lookup still behaves the "
            "way the one committed specimen did. The field API cannot author a Lookup at all, "
            "so the only route to one is COPYING a Base that already has it — which makes this "
            "the first arm whose subject is a column no disposable can be built with. It "
            "proves live that the cell wrapper still carries the TARGET field's type rather "
            "than 19, that filter_info.target_table still SURVIVES the pinned SDK's typed "
            "field bridge (the one key the whole reading rests on), that target_field / "
            "roll_up / formula still do NOT — the gap the surface discloses, which a client "
            "upgrade could close silently and turn the disclosure into a lie — and that a live "
            "LISTCOMBINE cell still arrives with its separators INSIDE the segment stream, so "
            "the empty-string join is right for a reason rather than by coincidence. The "
            "companion pins what a credential-less run cannot: that the configured Base is "
            "used as a COPY TEMPLATE and never as a write target, driven against a transport "
            "that RAISES ON CONTACT so the refusal is structural rather than counted; that no "
            "parent_node or folder token is passed anywhere, which is the OTHER way a real "
            "Base gets touched and which a guard watching write targets alone would miss; that "
            "the copy is ledgered before anything else can fail and deleted in a finally; that "
            "the arm consumes the shipped bounded settle rather than sleeping; and that BOTH "
            "its skip paths are loud — the credential one and the no-template one, because an "
            "arm that passes with no Lookup to read proves nothing.",
        ),
        (
            "test_live_base_relational_gate.py",
            "LD-272 — THE BASE RELATIONAL GATE, the point at which the Base RELATIONAL surface stops "
            "being asserted and gets watched, and the last planned rung of the Base ladder. It "
            "ships WITH its mirror, the direction every Base arm has taken. The live half runs "
            "four arms on ONE self-provisioned disposable, in time order because the phases "
            "depend on each other: a two-table link is built and populated and read with "
            "resolution off twice and on once; one file is uploaded, attached through the "
            "shipped encoder, read back and downloaded to an IDENTICAL sha256; a TARGET RECORD "
            "is deleted and the source table re-read, proving live that a one-way link keeps "
            "pointing at the dead id while a two-way link SELF-HEALS and that 1254043 never "
            "raises; then the TARGET TABLE is deleted and the free column-level detector reads "
            "the aftermath off a schema already in hand. The companion pins the five things a "
            "passing run cannot. FIRST: that neither a write target NOR a parent_node can come "
            "from configuration — both refused by one allow-list against a transport that "
            "RAISES ON CONTACT, so zero calls is structural rather than counted — and that the "
            "gate says out loud that READING the configured Base is legitimate while writing it "
            "is not, because a sibling arm does exactly that. SECOND: that EXACTLY ONE file is "
            "uploaded, since every upload is permanent unsweepable residue and a payload table "
            "here would invite a second. THIRD: that the byte-identity arm reads OFF TWICE and "
            "ON ONCE — an arm comparing one off-read against itself would prove determinism and "
            "nothing about the flag — and that the comparison is CELL-LEVEL, naming the "
            "differing column, rather than a substring check that could not tell a resolved "
            "link from a neighbouring cell that moved. FOURTH: that the zero-extra-call claim is "
            "MEASURED at the client's own counter rather than asserted, and that the detector it "
            "calls is the shipped free one whose module imports no client at all. FIFTH: that "
            "the arm POINTS AT the loss preview's inbound-dangle warning and does not restate "
            "it — one rule, one owner, checked by refusing any long run of the owner's own prose "
            "in the gate's text. The credential aliasing rider is pinned as a sentence in the "
            "gate's own docstring, because a green write run on a tenant whose pairs alias one "
            "app says nothing whatever about the read path lacking write scope.",
        ),
        (
            "test_live_drive_enumeration_arm.py",
            "LD-324's single Drive enumeration arm ships WITH its mirror, the direction every "
            "new arm has taken since LD-247. The companion pins what the arm's posture claims "
            "and a live run cannot: that it is READ-ONLY by construction (every registered "
            "Drive op declares `mutates: False`, asserted before the first call, and the "
            "declared verb set is GET plus exactly one query POST), that it names no write "
            "credential and no write verb, that its SUBJECT is the caller's OWN root folder "
            "DISCOVERED LIVE rather than any hard-coded token or maintainer-supplied tree — the arm "
            "is checked for a hard-coded `fldr…`/`nodl…` token in both directions — that it "
            "does NOT recurse (a live walk of a real tree of unknown depth is not what a "
            "two-call budget buys), that its live budget is an assertion rather than a hope, "
            "and that it skips LOUDLY, naming the missing credential variables. The canary "
            "doc is used only as a tenant-domain hint and the companion proves that hint "
            "DEGRADES rather than failing, because the arm's subject is not the canary doc.",
        ),
        (
            "test_live_drive_assets_gate.py",
            "LD-386's folder asset arm ships WITH its mirror, the direction every new arm has "
            "taken since LD-247. The companion pins what the arm's posture claims and a live "
            "run cannot: that it is READ-ONLY and names no write credential and no Drive write "
            "verb outside the one docstring sentence that has to say `create_folder`; that it "
            "hard-codes NO document or folder token and resolves every subject live or through "
            "canary_support; that it skips LOUDLY three ways — no credentials, no zoo document, "
            "and (the one that matters) a subject folder holding no asset-bearing document, "
            "which is an EXPLICIT skip naming the count rather than a fetch assertion passing "
            "vacuously on an empty set. It also records the honest limit of AC8 — a disposable "
            "folder cannot be self-provisioned because create_folder is a PERMANENT Drive write "
            "with no purge verb, so the ideal subject is a console action and the arm says so "
            "instead of glossing it. And it drives the LAYOUT ruling against fakes rather than "
            "reading it as text: the pool is flat and token-named (never a per-document "
            "subdirectory, the rejected fork) and the collision leg would really catch a "
            "double fetch.",
        ),
        (
            "test_live_drive_versions_gate.py",
            "LD-409's named-version gate — the FIRST live gate for a MUTATING Drive op — ships "
            "WITH its mirror, the direction every new arm has taken since LD-247. The "
            "companion carries what a live run cannot show you by not running: that the gate "
            "names NO standing fixture anywhere in its body (not the read canary, not either "
            "scratch surface, not either zoo) and hard-codes no token-shaped literal; that "
            "BOTH of its subjects are self-created and BOTH are torn down in a `finally`, with "
            "gone-ness proved by an INDEPENDENT re-query rather than by the delete's own "
            "return code — the one mistake that leaves an orphan behind a green run; that it "
            "skips LOUDLY without write credentials; and that the read-only claim it leans on "
            "is the RE-SCOPED one (D-24) — the R1 enumeration legs are still read-only, the "
            "registry as a whole no longer is, and EXACTLY ONE op mutates, which is the "
            "assertion that stops a second write op arriving on this path unnoticed. The "
            "ordering is pinned too: that assertion must come first in file order, because "
            "that is the order pytest runs them in.",
        ),
        (
            "test_live_drive_access_gate.py",
            "LD-432's docx ACCESS gate — the Drive family's second mutating gate, and the first "
            "whose subject is WHO may use a document — ships WITH its mirror, the direction "
            "every new arm has taken since LD-247. The companion carries what a live run cannot "
            "show you by not running. The disposables posture first: no standing fixture named, "
            "no token-shaped literal, the subject self-created INSIDE the try whose finally "
            "trashes, the teardown iterating a ledger appended to as each create returns, and "
            "gone-ness proved by an INDEPENDENT re-query rather than by the delete's own code. "
            "Then the one this surface exists for: that the gate asserts THE READ-BACK — the "
            "grant's own stored flag, the empty member list at birth, the empty list after the "
            "revoke, each copy-lever key against what the settings read returned, and the owner "
            "the member list structurally cannot show — because this endpoint family was "
            "measured ACCEPTING a member write and not storing it, and a gate that asserted "
            "only the absence of an exception would sail straight past that. It also pins what "
            "the gate must NOT reach for: transfer_owner, a department member type, "
            "remove_old_owner, and the two settings keys that are read-only or refused on that "
            "route — an unshipped capability is not something a live gate gets to try on the "
            "way past. And it pins that LD-420's LIVING FIXTURE is never addressed: that "
            "document is left alive on purpose for a human's copy/paste attempt, so targeting "
            "or deleting it here would either destroy a standing artifact or make this gate's "
            "result depend on one.",
        ),
        (
            "test_live_docx_historical_read_gate.py",
            "LD-410's historical-read gate — a WRITE gate for a READ capability, and the "
            "companion is where that inversion is justified rather than assumed. A read-only "
            "canary cannot produce two states, and a pinned read that cannot be distinguished "
            "from a head read proves nothing (D-05): 'it returned blocks' is exactly what a "
            "SILENTLY IGNORED parameter does. So the companion pins the falsification "
            "STATICALLY — TWO `create_children` calls and an INEQUALITY assertion between the "
            "pinned body and the head body, plus the state-two line being absent from the "
            "pinned read and present in the head one — and it pins the re-measurement of all "
            "three shipped traps (over-range silently returns head, the meta route ignores the "
            "pin, and raw_content is fenced by not existing on this surface at all, which is "
            "why the gate must not name it). It carries the usual disposables posture too: no "
            "standing fixture named, no token-shaped literal, the subject self-created and "
            "deleted in a `finally` with gone-ness proved by an independent re-query — and a "
            "LOUD skip for BOTH credential pairs, because the pinned read is a READ and "
            "borrowing the write pair for it would prove the wrong thing.",
        ),
        (
            "test_live_drive_canary.py",
            "LD-328's Drive canary — THE R1 GATE for the Drive surface — ships WITH its mirror, "
            "the direction every arm has taken since LD-247. Its companion carries the posture "
            "a live run cannot verify by not running, and the two obligations that are only "
            "checkable offline. The posture: READ-ONLY BY CONSTRUCTION asserted before the "
            "first call (every Drive op declares `mutates: False`, verbs are GET plus exactly "
            "one query POST), no write credential and no write verb anywhere, the READ pair "
            "only, a LOUD skip naming the missing credential, a committed capture of NOTHING "
            "(AC9's simplest-compliant answer: no file is written from what it read), and "
            "SAME-RUN byte-identity with no cross-time baseline because a folder's contents "
            "legitimately change between runs. The two only-offline obligations, both driven "
            "against fakes rather than read as text: the THREE subject branches — unset falls "
            "back to the bot's OWN root folder discovered live (a self-provisioned folder is "
            "unavailable because create_folder is a PERMANENT write with no purge verb), a set "
            "override replaces the subject without spending a root call, and a set-but-"
            "unreachable override SKIPS LOUDLY naming LARKDOCIO_CANARY_FOLDER rather than "
            "failing — and the budget's ENFORCEMENT, a RateLimiter subclass that raises BEFORE "
            "the over-budget call reaches the wire, proven in-situ through the real client's "
            "own send path so the ceiling cannot be bypassed at a call site.",
        ),
        (
            "test_live_sheets_float_image_gate.py",
            "LD-448's FLOAT IMAGE gate — the OTHER way a picture reaches a spreadsheet, and "
            "a different product from the in-cell arm above: this one anchors a picture OVER "
            "a range. It ships WITH its mirror, the direction every new arm has taken since "
            "LD-247. The disposables posture first: no standing fixture named, no "
            "token-shaped literal, the workbook self-created and trashed in a finally, with "
            "gone-ness proved by an INDEPENDENT re-query rather than by the delete's own "
            "code. Then the four this route exists for. ONE: EVERY verdict is a fresh "
            "float_images/query — for the bind and for the removal alike — and the companion "
            "pins that the gate demonstrates the hazard rather than reciting it, by making "
            "an upload of its own and asserting the tab is STILL EMPTY afterwards. TWO: the "
            "bind is sent EXACTLY ONCE and no retry construct may appear, because this "
            "route's refusal arrives wearing a server error's clothes and a client that "
            "believed the message would loop forever against a call that can never succeed. "
            "THREE: parent_node is asserted to be the WORKBOOK, never the tab — the one "
            "place a docx habit misleads, held live rather than only in prose. FOUR: the "
            "residue is LEDGERED, not cleaned, and this arm mints TWO tokens a run (the "
            "deliberately unbound one as well as the bound one), so the companion counts "
            "them both and refuses any fake purge leg; it also pins that the gate MEASURES "
            "the bytes surviving the removal rather than assuming it. Plus the standing "
            "three: the shipped hash check reused, no binary fixture committed, and no Lark "
            "refusal number asserted anywhere — the invented-token control records whatever "
            "code comes back and asserts only that it FAILED and that no phantom appeared.",
        ),
        (
            "test_live_sheets_in_cell_image_gate.py",
            "LD-447's IN-CELL IMAGE gate — the sheets twin of the docx image arm, and the "
            "first arm that writes BYTES into a spreadsheet — ships WITH its mirror, the "
            "direction every new arm has taken since LD-247. The companion carries what a "
            "live run cannot show you by not running. The disposables posture first: no "
            "standing fixture named, no token-shaped literal, the workbook self-created and "
            "trashed in a finally, with gone-ness proved by an INDEPENDENT re-query rather "
            "than by the delete's own code. Then the three this route exists for. ONE: the "
            "residue is DISCLOSED, not cleaned — and on this route LARK mints the token, "
            "nobody uploads it, so the companion pins that the gate prints what was minted "
            "and that no fake purge leg ever appears. TWO: the verdict is an INDEPENDENT "
            "read-back of the CELL, because values_image answers code:0 whether or not "
            "anything was stored, and an arm asserting only the absence of an exception "
            "would sail past the failure it exists to catch. THREE: the CLEAR is exercised "
            "as what it is — an ordinary empty-string value write — and the companion "
            "refuses any invented delete-image verb, because inventing one is exactly how "
            "this surface would start lying. It also pins that the gate reuses the shipped "
            "hash check rather than reaching for hashlib, that no binary fixture is "
            "committed (the image is built from source), and that no Lark refusal number is "
            "asserted anywhere — the bad-tab control records whatever code comes back and "
            "asserts only that the write FAILED.",
        ),
        (
            "test_live_docx_image_authoring_gate.py",
            "LD-433's docx IMAGE-AUTHORING gate — the first arm that writes BYTES into a "
            "document — ships WITH its mirror, the direction every new arm has taken since "
            "LD-247. The companion carries what a live run cannot show you by not running. "
            "The disposables posture first: no standing fixture named, no token-shaped "
            "literal, the document self-created and trashed in a finally. Then the two this "
            "arm exists for. ONE: the residue is DISCLOSED, not cleaned — an uploaded media "
            "token is permanent and no verb purges it, so the companion pins that the gate "
            "prints what it minted and pins that no fake purge leg ever appears, because a "
            "cleanup that could not work would read as hygiene. TWO: the verdict is an "
            "INDEPENDENT read-back — this route's whole hazard is that the upload answers "
            "code:0 and binds nothing, so an arm that asserted only the absence of an "
            "exception would sail straight past the failure it exists to catch. It also pins "
            "that the gate reuses the shipped hash check rather than reaching for hashlib, "
            "that no binary fixture is committed (the image is built from source), and that "
            "no Lark refusal number is asserted anywhere — the order-trap arm records "
            "whatever code comes back and asserts only that the bind FAILED and the block's "
            "token did not move.",
        ),
        (
            "test_live_drive_chunked_upload_gate.py",
            "LD-449's CHUNKED-UPLOAD gate — the first arm whose subject is a MULTI-PART "
            "upload, and it ships WITH its mirror. The companion carries what a live run "
            "cannot show you by not running. The disposables posture first, with this arm's "
            "own twist: unlike its LD-434 sibling the destination folder IS created here, by "
            "the GATE as D-12 plumbing, and deleted again — so the companion pins both halves, "
            "that the harness creates and deletes its own subject and that the LIBRARY still "
            "ships no folder-creating call anywhere. Then the three this arm exists for. ONE: "
            "the multi-part claim cannot be quietly downgraded — the spike ASKED about a "
            "16-part partition and never sent one, so an arm that accepted a single part would "
            "leave the finding unmade, and the companion pins the assertion and the sentence "
            "that says a single part is a finding rather than a pass. TWO: the residue is "
            "LEDGERED, not cleaned — an abandoned upload_id is a pending transaction with NO "
            "Drive object and no measured verb cancels it, so the companion pins the ledger "
            "and refuses any invented cancel/abort leg, because a cleanup that could not work "
            "would read as hygiene. THREE: teardown is proven by an INDEPENDENT re-query and "
            "the two object types answer DIFFERENTLY — a trashed folder token stops resolving "
            "while a trashed file token does not — so the file half is RECORDED rather than "
            "asserted, and the companion pins that it is never asserted. It also pins that the "
            "shipped hash check is reused rather than hashlib reached for, that no binary "
            "fixture is committed (the payload is generated), and that no Lark refusal number "
            "is asserted anywhere in the arm.",
        ),
        (
            "test_live_drive_folder_create_gate.py",
            "LD-467's FOLDER-CREATE gate — the ONE R3 organize verb a product ruling opened, "
            "and it ships WITH its mirror. The companion carries what a live run cannot show "
            "you by not running. The disposables posture first, with this arm's own twist: "
            "EVERY object it touches is one it made, including its parent folder, which it "
            "creates under the bot's OWN root discovered through the shipped read client — so "
            "the companion pins that no standing fixture, document or object-naming env var "
            "appears in it at all, and that no token-shaped literal is pasted in. Then the "
            "three this arm exists for. ONE: the DUPLICATE-NAME behaviour is RE-MEASURED live "
            "rather than trusted from the committed capture — the same name twice under one "
            "parent must yield two distinct tokens and two byte-identical names in the "
            "parent's own listing — and the companion pins that a contradiction is reported as "
            "the shipped DISCLOSURE being wrong, not as a bare failure, because that sentence "
            "is what a consumer plans around. TWO: the verdict that the folder EXISTS is the "
            "shipped read client's LISTING, never the create's own echo, and a file really is "
            "uploaded into it — a create verb whose product cannot be listed or written into "
            "would be a token rather than a folder. THREE: the folder DELETE is the gate's OWN "
            "raw call, because the library deliberately ships no folder-delete verb, and the "
            "teardown NAMES ITS RESIDUE rather than implying there is none — so the companion "
            "pins both the reason for the raw call and the residue ledger, and pins that the "
            "two object types answer DIFFERENTLY on re-query (a trashed folder token stops "
            "resolving, a trashed file token does not) with the file half RECORDED rather than "
            "asserted. It also pins that the shipped hash check is reused rather than hashlib "
            "reached for, that no binary fixture is committed (the payload is built from "
            "source), and that no Lark refusal number is asserted anywhere — the file-as-parent "
            "refusal is asserted on the LIBRARY's own sentence instead.",
        ),
        (
            "test_live_drive_bytes_leg_gate.py",
            "LD-474's BYTES-LEG gate — the disproof of a shipped sentence, and it ships WITH "
            "its mirror. Until 1.35 the folder read skipped every raw file saying the bytes "
            "leg 'is not shipped'; it is shipped, and one consumer run returned partial "
            "results on five of seven items because it believed the sentence. So the "
            "correction is not a paragraph but an arm: this one uploads a file into a folder "
            "it made, walks the folder through the shipped read, asserts the file was SKIPPED, "
            "and then downloads THAT VERY TOKEN and matches its sha256 against the upload's. "
            "The companion pins that the downloaded token is the skipped one rather than any "
            "file — a gate that downloaded an unrelated file would prove the verb works and "
            "disprove nothing — and pins both assertions on the skip reason: that it NAMES "
            "DriveFilesWriteClient.download and that it claims no absence. Three more "
            "measurements ride the same disposable, each because a shipped sentence now rests "
            "on it. The LEDGER FIELDS: which identity keys a folder_manifest row carries "
            "(created_time / modified_time / owner_id / url populated on every child kind, a "
            "revision only where the read supplied one) and — the half that rots silently — "
            "that NO size, digest, etag, checksum or content hash exists on any row, which the "
            "companion pins is asserted as an ABSENCE and not merely as a presence list. The "
            "CHANGE DETECTOR: one edit must advance revision_id and an immediately following "
            "read must not move it, so 'polling is inert' rests on a measurement rather than "
            "on a plausible-sounding sentence; the companion pins that BOTH halves are "
            "asserted. The CLASSIFICATION ROUTE: a DOCUMENT's tenant security level, taken "
            "THROUGH THE SHIPPED OP (DriveClient.document_security_level) rather than through a "
            "hand-rolled call, because the guide may not send anyone to a private API for "
            "something a documented route already answers — and once the read ships, a gate "
            "still hand-rolling it would prove the route while leaving the product unmeasured. "
            "The disposable is one nobody classified, so the answer must be the measured "
            "empty-means-NO-LEVEL-SET case; a level appearing there would mean that reading, "
            "not the route, needs re-measuring. Disposables posture throughout — every object "
            "is created under the bot's own discovered root, deleted in a finally, each "
            "deletion proved by an independent re-query with residue NAMED, and the folder "
            "delete is the gate's own raw call because the library ships no folder-delete "
            "verb. No binary fixture, the shipped hash rather than hashlib, and no Lark "
            "refusal number pinned anywhere.",
        ),
        (
            "test_live_drive_upload_identity_gate.py",
            "LD-464's UPLOAD-IDENTITY gate — the arm for the finding an automation hits on its "
            "SECOND run, and it ships WITH its mirror. The companion carries what a live run "
            "cannot show you by not running. The disposables posture first, on this arm's own "
            "terms: every object it touches is one it made, in a folder it created under the "
            "bot's OWN root discovered through the shipped read client, so the companion pins "
            "that no standing fixture, document or object-naming env var appears in it and that "
            "no token-shaped literal is pasted in. Then the four this arm exists for. ONE: the "
            "DUPLICATE-UPLOAD behaviour is RE-MEASURED live rather than trusted from the "
            "committed capture — the identical bytes under the identical name must yield a "
            "DISTINCT token — and the companion pins that a contradiction is reported as the "
            "shipped DISCLOSURE being wrong, not as a bare failure, because that sentence is "
            "what a consumer plans around. TWO: the by-name LOOKUP is exercised on BOTH arms, "
            "found and not-found, because a lookup only ever shown matching would never prove "
            "that an absence comes back as an empty answer rather than a refusal. THREE: the "
            "second delete is read through the SHIPPED PREDICATE rather than by matching a "
            "message string — the predicate is the contract and the message is disclosure, and "
            "a gate asserting the sentence would re-freeze the very string this arm exists to "
            "have changed. FOUR: BOTH halves of gone-ness appear and only one is asserted — the "
            "token must leave the folder listing (the half the library claims), while what the "
            "metadata route then says is RECORDED, because a trashed file token was measured "
            "still resolving; swapping one wrong sentence for another is the exact trap here. "
            "The companion also pins that the eight overwrite forms are NOT re-sent on every "
            "run (they are captured; re-sending eight ignored parameters against a live tenant "
            "would be noise), that the shipped hash check is reused rather than hashlib reached "
            "for, that no binary fixture is committed, and that no Lark refusal number is "
            "asserted anywhere in the arm.",
        ),
        (
            "test_live_drive_file_link_gate.py",
            "LD-434's UPLOADED-FILE SENTENCE-LINK gate — the arm that demonstrates both "
            "halves of one ask together, and it ships WITH its mirror. The companion carries "
            "what a live run cannot show you by not running. The disposables posture first, "
            "with one twist this arm is the only one to have: the document is self-created "
            "and trashed, but the DESTINATION FOLDER is deliberately NOT created — the "
            "shipped op refuses to invent a destination, so the gate refuses too and skips "
            "loudly without a caller-supplied token, and the companion pins that no "
            "folder-creating call ever appears in it. Then the three this arm exists for. "
            "ONE: the verdict is the READER'S OWN MARKDOWN — the whole claim is that a "
            "created run's link survives the round trip, so an arm that read the write "
            "client's own answer would prove only that the write echoed itself. TWO: BOTH "
            "deletions are proven by an INDEPENDENT re-query, never by a delete's own "
            "code:0 — and the media tokens the attachment arm mints are printed rather than "
            "swept, because nothing purges drive media and a fake purge leg would read as "
            "hygiene. THREE: the sentence goes through dry_run -> Plan -> apply, so the "
            "gate cannot quietly prove a capability the plan gate does not actually offer. "
            "It also pins that no binary fixture is committed (the .html is built from "
            "source), that the shipped hash check is reused rather than hashlib reached "
            "for, and that no Lark refusal number is asserted anywhere.",
        ),
        (
            "test_live_write_refusal_policy_gate.py",
            "LD-458's REFUSAL-POLICY arm ships with its companion. The policy's own behaviour "
            "is already pinned offline (tests/test_apply_refusal_policy.py, per surface), so "
            "what this companion pins is the thing only a round trip can claim and only a "
            "shape check can keep honest: that BOTH shapes are driven — the default raise AND "
            "allow_partial=True — and that the arm COMPARES the two documents' read-backs "
            "rather than asserting each alone, because 'nothing about the writes changed' is "
            "a statement about the pair. It also pins that the applied entry is read back and "
            "proved NOT rolled back by the raise (this library never rolls back), that the "
            "refused entry is proved to have written nothing, that the exception is asserted "
            "to CARRY what the return value used to (the log, what applied, each refusal's "
            "reason and detail, the count named both ways), that the refusable entry is the "
            "MEASURED ambiguous-quote shape rather than a cheaper invented one, and that both "
            "documents are self-created disposables emptied in a finally with the close-out "
            "re-query.",
        ),
        (
            "test_live_restructure_gate.py",
            "LD-471's RESTRUCTURE arm ships with its companion. The discipline it runs is "
            "already exercised offline by the shipped recipe itself (the guide-recipe harness "
            "runs it end to end, proving insert-before-delete on the document's own revision "
            "history), so what this companion pins is what only a shape check keeps honest: "
            "that the arm asserts the ORDER off a fresh READ rather than off the applies' "
            "outcomes — a fully-applied, refusal-free log is compatible with a document in the "
            "wrong order, which is the whole reason the arm exists — that it asserts the other "
            "half too (the ids the longest common subsequence left alone are still there), that "
            "the LCS it runs is SLICED OUT OF THE SHIPPED RECIPE rather than re-implemented "
            "here, that the comments READ is asserted while the flaky comment CREATE is "
            "deliberately not, and that the document is a self-created disposable emptied in a "
            "finally with the close-out re-query.",
        ),
        (
            "test_live_docx_folder_acl_gate.py",
            "LD-469's FOLDER-ACL arm — the re-measurement of a shipped sentence that was "
            "FALSE, and it ships WITH its mirror. The guide asserted unconditionally that a "
            "fresh docx is a document only the app can use; a docx created INTO A FOLDER comes "
            "back carrying inherited rows, so the arm measures the claim rather than "
            "transcribing a round-4 note. The disposables posture first, with this arm's own "
            "twist: BOTH documents and the parent folder are made by the run, the folder under "
            "the bot's OWN root discovered through the shipped read client — so the companion "
            "pins that no standing fixture, canary or object-naming env var appears in it and "
            "that no token-shaped literal is pasted in. Then the three this arm exists for. "
            "ONE: the CONTROL is run and asserted EMPTY — a document with no folder_token — "
            "because without a baseline 'the folder case is different' is a claim about "
            "nothing, and the companion pins that a control that stops reading empty is "
            "reported as the guide's no-folder half being WRONG rather than as a bare failure. "
            "TWO: the inherited-row VOCABULARY (perm_type='container', the word a consumer "
            "gets back and the word the guide now teaches) is asserted PER ROW rather than "
            "counted — a folder carrying no rows of its own passes none down, which is "
            "inheritance answering honestly and not a failure — and the companion pins the "
            "per-row shape so a later edit cannot quietly turn it into a count that only "
            "passes on a shared folder. THREE: the FOLDER's own member list is RECORDED and "
            "never asserted, because whether that route answers for a folder at all is the "
            "question the leg asks; the call is the gate's OWN because the shipped surface "
            "refuses `folder` by name as unmeasured (LD-456's fence, which this arm does not "
            "move), and the companion pins both the recording and the reason for the raw call. "
            "It also pins that member ids are abbreviated in the evidence print (an inherited "
            "row names a person or a chat the run did not create) with nothing asserted on the "
            "truncation, that the folder delete is the gate's own call because no folder-delete "
            "verb ships, that the teardown NAMES ITS RESIDUE, and that no Lark refusal number "
            "is asserted anywhere in the arm.",
        ),
        (
            "test_live_docx_media_placement_gate.py",
            "LD-470's docx MEDIA-PLACEMENT gate — the first arm whose subject is WHERE a "
            "media block lands rather than whether it bound, and it ships WITH its mirror. "
            "The two shipped arguments it measures (`parent_block_id` and `index`) appeared "
            "in no shipped text at all, and a dogfood run had DERIVED their semantics from a "
            "single diff; a derivation from one run is a hypothesis, so this arm measures "
            "them and the guide quotes the measurement. The disposables posture first: no "
            "standing fixture named, no token-shaped literal, the document self-created and "
            "trashed in a finally. Then the three this arm exists for. ONE: the placement "
            "verdict is read from the PARENT BLOCK'S OWN `children` list, never from a "
            "create's echo — an echo carries the block that was made, not the order it was "
            "made into, so an arm trusting it would assert nothing about placement at all, "
            "and the companion pins that every case re-reads. TWO: all four cases are "
            "present and each is asserted on the WHOLE order rather than on an index alone — "
            "a positive index, index=0, the default, and a NON-ROOT parent whose leg also "
            "proves the root's own child list did not move; the companion pins the four so a "
            "later edit cannot quietly reduce the measurement the shipped sentences rest on. "
            "THREE: the residue is DISCLOSED, not cleaned — four uploads mint four permanent "
            "media tokens no verb purges, so the companion pins the printed ledger and "
            "refuses any fake purge leg. It also pins that the wrapper trap is measured on "
            "the wire (both ids typed from independent reads, the child confirmed to be the "
            "type-23 file block and the create's own id the type-33 wrapper), that no binary "
            "fixture is committed (the PNG is built from source), and that no Lark refusal "
            "number is asserted anywhere.",
        ),
        (
            "test_live_sheets_ld472_doc_truth_gate.py",
            "LD-472's sheets DOC-TRUTH gate — the first arm whose subject is a SENTENCE. Two "
            "shipped claims were measured false in a consumer field exercise, and the issue's "
            "rule was that the docs are re-measured BEFORE they are rewritten and that the "
            "measurement wins; this arm is that re-measurement, and it ships with its mirror. "
            "The disposables posture first: no standing fixture named, no token-shaped "
            "literal, the workbook self-created and deleted in a finally with gone-ness proved "
            "by an independent re-query. Then the three this arm exists for. ONE: BOTH HALVES "
            "of each measurement are present, because half of either measures nothing — "
            "`AddTab` with no `index` beside `index=len(tabs)` (a placement claim needs the "
            "append control to mean 'first' rather than 'somewhere'), and a multi-cell "
            "`a1_range` beside the single-cell anchor (a refusal with no working control is "
            "indistinguishable from a broken call). The companion pins all four. TWO: the arm "
            "ASSERTS the shipped sentences rather than printing them — `no_index_position == "
            "[0]`, the append landing last, the multi-cell bind failing — so a future run that "
            "disagrees with the guide reddens instead of being read past, which is the whole "
            "meaning of 'the measurement wins'. THREE: the residue is DISCLOSED, not cleaned, "
            "and here it is disclosed twice over — the refused multi-cell bind ORPHANS a media "
            "token BY CONSTRUCTION (the upload precedes bind validation, which is the finding "
            "the guide now states), and no verb purges drive media, so the companion pins the "
            "printed ledger, the `orphan_file_token` and the refusal of any fake purge leg. It "
            "also pins that no binary fixture is committed (the PNG is built from source) and "
            "that no Lark refusal number is asserted anywhere — the codes `1310202` and the "
            "tab order are RECORDED in the evidence print, which is what a doc correction "
            "quotes.",
        ),
        (
            "test_live_sheets_hidden_tab_read_gate.py",
            "LD-477's hidden-tab READ-ROUTE gate — the first arm whose write credentials exist "
            "ONLY to build the situation, with the claim itself made by a different client. A "
            "read-only reporting job could not tell a hidden tab from a live one, and this arm "
            "is where that stops being true on the shipped surface. The disposables posture "
            "first: no standing fixture named, no token-shaped literal, the workbook "
            "self-created and deleted in a finally with gone-ness proved by an independent "
            "re-query — and, unusually for a write-ring arm, NO permanent residue at all, "
            "because nothing is uploaded. Then the three this arm exists for. ONE: THE CLAIM IS "
            "MADE THROUGH A READ CLIENT. Reading the visibility back through "
            "`SheetsWriteClient.query_tabs` would re-measure a capability that shipped in "
            "LD-187 and would say nothing whatever about the read route, so the companion pins "
            "that the assertion runs on `SheetsReadClient.from_read_credentials(...)"
            ".query_sheets`. TWO: BOTH CASES are asserted — the hidden tab `True` AND the "
            "visible tab an explicit `False`. Half of that measures nothing: without the "
            "visible arm the run cannot distinguish 'Lark reports visibility' from 'Lark "
            "reports hiddenness and stays silent otherwise', which is the very distinction the "
            "None-is-never-False rule turns on, and the situation is confirmed on the WRITE "
            "side before the read leg is asked so a read agreeing with itself cannot pass for "
            "evidence. THREE: the arm pins that the RENDERER STAYED SILENT — the rendered "
            "Markdown gains no hidden-tab marker — because that is the half of this change no "
            "consent exists for and the half that would move every consumer's golden files. "
            "The companion also pins that both credential pairs are named in the skip (the "
            "read pair is the subject, so its absence must skip loudly rather than surface as "
            "a config error mid-run) and that no Lark refusal number is asserted anywhere.",
        ),
        (
            "test_live_typed_create_returns_gate.py",
            "LD-583's TYPED-CREATE-RETURNS gate — the first arm whose subject is a RETURN "
            "TYPE, and it ships WITH its mirror. A typed return whose fields were only ever "
            "proven against a recorded double is a guess wearing the shape of an answer, which "
            "is the exact objection this issue exists to remove, so the four create/copy verbs "
            "are driven live and each type is compared against what came back today. The "
            "disposables posture first: no standing fixture named, no token-shaped literal, "
            "every one of the four objects self-created into the configured human-visible "
            "folder and torn down in a finally — and, unusually for a write-ring arm, NO "
            "permanent residue at all, because nothing is uploaded, which is why its budget "
            "can promise a clean sweep rather than disclose a ledger. Then the three this arm "
            "exists for. ONE: THE SUBJECT IS A NEGATIVE. `CreatedDocument`'s whole claim is "
            "that the docx v1 reply carries NO url, so the companion pins that the arm ASSERTS "
            "`\"url\" not in created` — and pins the sentence saying a reply that grew one is a "
            "FINDING rather than a pass, because an arm checking only the positive fields would "
            "leave the load-bearing half unmeasured. TWO: two of the four verbs return the "
            "SDK's `App` rather than a dict, so the attribute-compatibility check ITERATES "
            "`App._types` instead of a hand-typed list — a hand-typed list is a second "
            "definition of the SDK's shape that drifts the day the pin grows a field — and the "
            "companion pins the iteration on BOTH the create and the copy. THREE: the copy's "
            "measured fact is an EMPTINESS (`default_table_id` comes back empty because the "
            "copy is asynchronous), asserted on the same rule as ONE with its own "
            "finding-not-a-pass sentence. It also pins the permanent prohibition structurally "
            "— no `https://` appears anywhere in the arm, so no URL can be assembled from a "
            "host and a token — that the budget is DECLARED in the arm's own docstring kind by "
            "kind before the spend, that the residue is NAMED per object through the harness "
            "oracle rather than summarised as a count, and that no fake purge leg exists.",
        ),
        # LD-601 — the REMOVAL-ROUTE probe. Paired, and for a reason no arm here has carried:
        # the gate exists because a THIRD-PARTY measurement was declined as evidence (the maintainer
        # ruling recorded as its own `requirements/DECISIONS.md` row), so its captures are the
        # sole provenance of a shipped guide paragraph. That makes the discipline the claim: a
        # BEFORE control leg, one route table run twice rather than two hand-written legs that
        # could drift apart, an explicit `doc_type` literal per route (LD-606 measured that a
        # wrong spelling answers `code:0` with an empty `metas`), and a verdict read from
        # `failed_list` rather than the envelope. None of that is provable on a run that skips.
        (
            "test_live_docx_removal_routes_gate.py",
            "the removal-route probe's captures are the ONLY source of a shipped guide "
            "paragraph, so its companion pins the things that decide whether the capture "
            "means anything: that the BEFORE control leg runs and is asserted (an `after` "
            "answer proves nothing about a delete without it), that ONE route table is run "
            "twice rather than two legs that can drift, that every route sends an EXPLICIT "
            "object-type literal and records it in the capture, that resolution is read from "
            "`failed_list` rather than the envelope `code`, that both standing fixtures are "
            "named as a FENCE and never consumed, that nothing in the arm can mint permanent "
            "media, and that the committed captures carry both legs and the request they sent.",
        ),
    )
    for row in _pair(gate, why=why)
)


#: **Stories in a rung that ship NO live file at all, and why** — the other half of *"a live
#: ring or a written reason"*.
#:
#: The registry above is globbed over ``tests/test_live_*.py``, so a story that never created
#: such a file leaves **no row**, and an absence in a file-keyed registry is indistinguishable
#: from an oversight. That is exactly the shape the whole registry exists to refuse, so the
#: reason is recorded as data here, keyed by the **surface the story shipped** rather than by an
#: issue id: a surface is still there to read in a year.
#:
#: Two entries, both from the relational rung, and both are *zero-call by their own acceptance
#: criteria* rather than untested — which is the distinction that makes the absence a decision.
_RINGS_DECLINED: dict[str, str] = {
    "larkdocio.base.referential": (
        "the column-level dangling-target reading makes no call at all: it is derived from the "
        "field property a Base read has ALREADY fetched, imports no client and no transport, "
        "and a guard over its own syntax tree pins that. A live ring would have nothing to run "
        "— there is no request to watch — so the shape of the claim is pinned offline against "
        "the committed capture the signature came from, and the aftermath it reads is exercised "
        "live by the relational gate, which deletes a real target table and reads the real "
        "column back."
    ),
    "the person/chat disclosure": (
        "the identity story added zero call sites by ruling: it says what an id-written person "
        "cell does, where the three honest id sources are, and that no roster, directory dump "
        "or chat lister ships — all of which are statements ABOUT calls this library does not "
        "make. A live ring would either have nothing to run or would have to make the very call "
        "the disclosure exists to say is not made, so the offline corpus is the whole of it."
    ),
}


_UNMIRRORED: tuple[GateRow, ...] = (
    GateRow(
        filename="test_live_canary.py",
        kind=Kind.DECLARED_NONE,
        reason=(
            "the reader canary (LD-003) predates the companion pattern. Unverified offline: "
            "that it is credential-gated rather than silently passing, that it addresses only "
            "LARKDOCIO_CANARY_DOC, and that it stays read-only."
        ),
    ),
    GateRow(
        filename="test_live_contacts_lookup.py",
        kind=Kind.DECLARED_NONE,
        reason=(
            "the read-only name-lookup arm has no separate companion. What is therefore "
            "unverified offline is only its POSTURE — that it makes search calls and nothing "
            "else, and that it skips loudly rather than passing when the grant is absent; the "
            "behaviour it exercises is already pinned offline by tests/test_contacts_lookup.py "
            "against the committed captures, so the gap here is narrower than most on this "
            "list."
        ),
    ),
    GateRow(
        filename="test_live_comment_anchor_zoo_arm.py",
        kind=Kind.DECLARED_NONE,
        reason=(
            "the read-only zoo arm has no companion pinning its two load-bearing claims — "
            "that it never writes, and that the only document it addresses is the shared "
            "comment document named by its own env var."
        ),
    ),
    GateRow(
        filename="test_live_sheets_dimension_write_gate.py",
        kind=Kind.DECLARED_NONE,
        reason=(
            "LD-185's dimension-property arm carries the 1-indexed-INCLUSIVE convention claim "
            "live only; no companion pins its shape or its disposables-only provisioning."
        ),
    ),
    GateRow(
        filename="test_live_sheets_dropdown_write_gate.py",
        kind=Kind.DECLARED_NONE,
        reason=(
            "LD-120's dropdown-rule arm has no companion; its self-provision + finally-delete "
            "discipline is unchecked on an ordinary run."
        ),
    ),
    GateRow(
        filename="test_live_sheets_formula_write_gate.py",
        kind=Kind.DECLARED_NONE,
        reason=(
            "LD-149's nine-arm formula gate has no companion; the largest unmirrored gate in "
            "the set, and the one whose disposables discipline is most worth pinning."
        ),
    ),
    GateRow(
        filename="test_live_sheets_merge_tab_write_gate.py",
        kind=Kind.DECLARED_NONE,
        reason=(
            "LD-122's merge/unmerge + tab arm has no companion; nothing pins that it verifies "
            "through the v3 merge leg rather than trusting the write's own echo."
        ),
    ),
    GateRow(
        filename="test_live_sheets_rich_write_gate.py",
        kind=Kind.DECLARED_NONE,
        reason=(
            "LD-119's four rich-cell encoders are proven live only; no companion pins the "
            "arm's shape or its self-provisioned target."
        ),
    ),
    GateRow(
        filename="test_live_sheets_structural_write_gate.py",
        kind=Kind.DECLARED_NONE,
        reason=(
            "LD-121's structural arm carries the index-convention asymmetry claim live only; "
            "no companion mirrors it."
        ),
    ),
    GateRow(
        filename="test_live_write_mermaid_create_gate.py",
        kind=Kind.IN_FILE_MIRROR,
        mirror_marker="def test_this_gate_never_addresses_the_specimen_document",
        reason=(
            "the 15th spelling of the invariant: LD-192 kept the always-on discipline checks "
            "INSIDE the gate file (the gate's own source is split at a marker and swept for "
            "specimen tokens, create/delete, and the finally-delete). Mirrored, but not by a "
            "companion file — classifying it as either HAS_COMPANION or DECLARED_NONE would "
            "be wrong."
        ),
    ),
)


_NON_GATES: tuple[GateRow, ...] = (
    GateRow(
        filename="test_live_sheets_write_harness.py",
        kind=Kind.HARNESS,
        reason=(
            "the LD-112 Sheets self-provision cycle — a live PROVISIONING harness, not a gate "
            "over shipped read/write behavior. Excluded from the 27-gate count by the audit's "
            "own arithmetic; the arms that depend on it carry the disposables-only invariant "
            "in their own companions."
        ),
    ),
    GateRow(
        filename="test_live_write_harness.py",
        kind=Kind.HARNESS,
        reason=(
            "the W0 self-provisioning live-write harness (LD-064) — transport-level "
            "provisioning, not a gate over shipped behavior. Its offline scaffolding tests "
            "live in test_live_write_offline.py, which is deliberately NOT counted among the "
            "14 gate companions."
        ),
    ),
    GateRow(
        filename="test_live_base_disposable_harness.py",
        kind=Kind.HARNESS,
        reason=(
            "LD-258's Base self-provision cycle — the third live PROVISIONING harness, and a "
            "harness for the same reason the other two are: it proves the create → exercise → "
            "delete-in-`finally` → ledger → zero-orphan close-out lifecycle of "
            "`tests/base_write_harness.py`, not any shipped read or write behavior (the Base "
            "write client's own gate is test_live_base_write_arm.py). Classified HARNESS "
            "per file rather than by its name, so the gate arithmetic and the published gap "
            "table are deliberately unmoved by it. Its offline half is an OFFLINE_SUPPORT row "
            "below — not a companion — for exactly the reason the W0 pair is."
        ),
    ),
    GateRow(
        filename="test_live_base_disposable_harness_offline.py",
        kind=Kind.OFFLINE_SUPPORT,
        subject="test_live_base_disposable_harness.py",
        reason=(
            "the always-on offline half of the Base harness cycle (LD-258): the enforced "
            "`larkdocio-DISPOSABLE-` prefix refused before the SDK is touched, the allow-list "
            "that makes the Scratch Base's hand-authored specimens untouchable WITHOUT the "
            "harness naming any configured target, the delete proven to run when the body "
            "raises, the ledger that flags rather than drops — cross-session and resolved to "
            "the MAIN checkout since LD-275, so a leg run in a linked worktree cannot take its "
            "only record of a live Base to the grave, with a not-found answer inside the "
            "addressability window judged `pending` rather than believed and adoption "
            "restricted to the stale so a parallel leg's Base is never swept out from under "
            "it — the bitable-API orphan oracle "
            "(1002/91402/1254041) with Drive metadata proven never reached for, and the "
            "exactly-one-provisioner rule. Offline and mirroring a live file — but its subject "
            "is a HARNESS row, so it is NOT one of the gate companions."
        ),
    ),
    GateRow(
        filename="test_live_write_offline.py",
        kind=Kind.OFFLINE_SUPPORT,
        subject="test_live_write_harness.py",
        reason=(
            "offline unit tests for the W0 harness SCAFFOLDING (LD-064). It is offline and it "
            "mirrors a live file, but its subject is a HARNESS row rather than a gate — which "
            "is exactly why the audit's companion count is 14, not 15."
        ),
    ),
)


REGISTRY: dict[str, GateRow] = {
    row.filename: row for row in (*_PAIRED, *_UNMIRRORED, *_NON_GATES)
}


# ---------------------------------------------------------------------------
# Derivations — nothing below is hand-typed
# ---------------------------------------------------------------------------

_GATE_KINDS = (Kind.HAS_COMPANION, Kind.DECLARED_NONE, Kind.IN_FILE_MIRROR)


def rows() -> tuple[GateRow, ...]:
    """Every row, ordered by filename."""
    return tuple(REGISTRY[name] for name in sorted(REGISTRY))


def gates() -> tuple[GateRow, ...]:
    """The live gates — everything that is neither a companion, a harness, nor support.

    27 when the 2026-08-01 audit counted them; 34 today (the count is derived, never restated:
    +1 for the LD-229 name-lookup arm, +4 for LD-236's round-trip arms, +1 for
    LD-247's Base read arm, +1 for LD-252's Base canary — THE L1 GATE).
    """
    return tuple(row for row in rows() if row.kind in _GATE_KINDS)


def gap_list() -> tuple[GateRow, ...]:
    """The gates with **no separate offline companion file** — 10 of them.

    9 are ``DECLARED_NONE`` (no mirror at all — the gaps the maintainer ratified on 2026-08-03); the
    10th is the mermaid gate's in-file mirror, listed so the count reconciles and so the T5b
    question ("does the in-file spelling want normalizing?") stays visible.
    """
    return tuple(row for row in gates() if row.kind is not Kind.HAS_COMPANION)


def declared_none() -> tuple[GateRow, ...]:
    """The gates with no offline mirror of any kind — the nine ratified gaps."""
    return tuple(row for row in gates() if row.kind is Kind.DECLARED_NONE)


def rings_declined() -> dict[str, str]:
    """``{surface: written reason}`` for every story that ships **no live file at all**.

    The companion to :func:`gates` and the reason the registry is not purely file-keyed: a
    zero-call story leaves nothing for a glob to find, and *"a live ring or a written reason"*
    is only exhaustive if the reasons are data too.
    """
    return dict(_RINGS_DECLINED)


def first_pass_excluded() -> tuple[str, ...]:
    """Files both audits keep out of the first normalization pass (LD-222 AC7)."""
    return tuple(row.filename for row in rows() if row.first_pass_excluded)


def counts() -> dict[str, int]:
    """The population arithmetic, derived from the rows rather than restated."""
    offline = [r for r in rows() if r.filename.endswith("_offline.py")]
    return {
        "discovered": len(REGISTRY),
        "offline_files": len(offline),
        "live_files": len(REGISTRY) - len(offline),
        "harnesses": sum(1 for r in rows() if r.kind is Kind.HARNESS),
        "gates": len(gates()),
        "companions": sum(1 for r in rows() if r.kind is Kind.COMPANION),
        "gaps": len(gap_list()),
    }


def render_gap_table() -> str:
    """Render the published gap table (the region pinned in this module's docstring).

    Regenerate after touching the rows::

        .venv/bin/python -c "import sys; sys.path.insert(0,'tests'); \\
            import gate_registry; print(gate_registry.render_gap_table(), end='')"
    """
    gaps = gap_list()
    names = [r.filename.removesuffix(".py") for r in gaps]
    kinds = [r.kind.name for r in gaps]
    arcs = ["* v1.24.0 arc" if r.arc_v1_24_0 else "—" for r in gaps]

    head = ("#", "live gate (no separate offline companion file)", "kind", "added by")
    w_n = max(len(head[0]), len(str(len(gaps))))
    w_f = max(len(head[1]), *(len(s) for s in names))
    w_k = max(len(head[2]), *(len(s) for s in kinds))
    w_a = max(len(head[3]), *(len(s) for s in arcs))

    lines = [
        f"| {head[0]:>{w_n}} | {head[1]:<{w_f}} | {head[2]:<{w_k}} | {head[3]:<{w_a}} |",
        f"|{'-' * (w_n + 1)}:|{'-' * (w_f + 2)}|{'-' * (w_k + 2)}|{'-' * (w_a + 2)}|",
    ]
    for i, (name, kind, arc) in enumerate(zip(names, kinds, arcs), start=1):
        lines.append(f"| {i:>{w_n}} | {name:<{w_f}} | {kind:<{w_k}} | {arc:<{w_a}} |")
    return "\n".join(lines) + "\n"


# ===========================================================================
# THE MEDIA-MINTING CLASSIFICATION (LD-505) - the OTHER cost of running a ring
# ===========================================================================
#
# The classification above prices the ABSENCE OF AN OFFLINE MIRROR. This one prices what a
# run SPENDS: an upload mints a drive media token, **no route in Lark's open API purges drive
# media - measured, not assumed** (`larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA`, ruled
# D-95: nine destructive spellings, fourteen sends, four tokens, both media paths, not one
# removed), and deleting the document does not remove it. So the price of a live run was
# invisible at exactly the moment somebody decided to pay it.
#
# The two classifications are INDEPENDENT and sit beside each other over ONE population. This
# section changes no `Kind`, no companion pairing and none of the nine ratified DECLARED_NONE
# reasons - those are verbatim decisions.
#
# THE CENSUS IS MEASURED, NOT INHERITED (AC1a). Method, reproducible: grep every discovered
# `tests/test_live_*.py` for the library's own upload vocabulary - the four minting surfaces
# (`larkdocio.write.media`, `larkdocio.sheets.media`, `larkdocio.base.media`,
# `larkdocio.drive.files_write`), the two harness verbs a Base arm reaches them through, and
# the raw `upload_all` spelling - then READ every hit and decide what the run actually sends.
# The mechanical sweep is only the haystack; three of its answers are wrong in each direction
# and are recorded per file below, which is why the verdicts are authored data rather than a
# pattern.
#
# Every one of the 153 files is named LITERALLY below. There is no `if "offline" in name`
# anywhere here, for the same reason `test_gate_registry`'s docstring forbids one.


class MediaMint(enum.Enum):
    """What running one discovered ``tests/test_live_*.py`` costs in permanent residue."""

    PERMANENT_MEDIA = (
        "the live ring UPLOADS BYTES and mints a permanent, unpurgeable drive media token")
    SWEEPABLE_DRIVE_OBJECT = (
        "the live ring uploads a drive FILE OBJECT - not drive media - which a shipped delete "
        "removes (trash, not purge)")
    NONE = "the file mints no drive media at all"


@dataclass(frozen=True)
class MediaVerdict:
    """One file's media price. ``reason`` is required for every verdict - including NONE, so
    that "no" is a recorded decision rather than a blank (LD-505 AC1b)."""

    filename: str
    mint: MediaMint
    reason: str
    note: str | None = None
    """Set where the mechanical sweep and the truth disagree - a file that NAMES an upload op
    and mints nothing, or mints without naming one. The note says which, and why."""


#: The written grounds a verdict of NONE stands on. Each is a decision about a class of file;
#: the files are then enumerated by name against it, never matched by shape.
_NO_MINT_GROUNDS: dict[str, str] = {
    "OFFLINE_BY_CONSTRUCTION": (
        "offline by construction - it reads its subject as TEXT and makes no API call at all, "
        "so there is nothing for it to upload."),
    "NO_UPLOAD_CALL_SITE": (
        "a live ring that calls the API but names no upload op on any of the library's four "
        "minting surfaces. Creating a block, reading a token back and downloading bytes all "
        "mint nothing - `A download mints nothing` (`src/larkdocio/write/media.py`)."),
    "THE_TOKEN_WORD_IS_NOT_A_MEDIA_TOKEN": (
        "the file's `file_token` is a DOCUMENT, FOLDER or drive-file token - the parameter "
        "name Lark uses for every object it addresses - and never a media token. This is the "
        "trap the approximate sweep exists to be corrected on: grepping for the word finds "
        "these files and they mint nothing."),
}

#: The mirror note. An offline companion names the op it mirrors because the NAME is what it
#: greps for; naming a call is not making one.
_MIRRORS_THE_NAME = (
        "an offline companion NAMES the upload op it mirrors because grepping its subject's "
        "source text for exactly that name IS its mechanism. The name is the check, never a "
        "call: this file makes no API call at all.")

_MEDIA_MINTERS: dict[str, str] = {
    "test_live_base_media_gate.py": (
        "LD-268's Base attachment arm. `base_write_harness.attach_media` -> "
        "`BaseMediaClient.upload` -> `POST drive/v1/medias/upload_all` with `parent_type` in "
        "`larkdocio.base.media.MEDIA_PARENT_TYPES` (`bitable_file` / `bitable_image`). Every "
        "send is a token that SURVIVES ITS TABLE'S DELETION - BASE.md's limitation register "
        "row 10, and the reason `base_write_harness.Ledger` has a MEDIA half at all: media "
        "residue is explicitly OUTSIDE the arm's `orphans == 0` claim."),
    "test_live_base_relational_gate.py": (
        "LD-272's relational round-trip uploads ONE generated file through "
        "`base_write_harness.attach_media` - one, not four, because every upload is permanent "
        "- and its own docstring says the price out loud: *\"THIS ARM MINTS PERMANENT, "
        "UNSWEEPABLE RESIDUE, AND THAT WAS BOUGHT KNOWINGLY\"*. The token is ledgered with "
        "its `parent_type` and printed in the arm's `_residue` evidence line."),
    "test_live_docx_image_authoring_gate.py": (
        "LD-421's docx image arm drives the shipped `put_image_in_document`, whose SECOND "
        "beat is `medias/upload_all` with `parent_type: docx_image` bound to the block "
        "created by the first. A run mints one token per image; the block create alone would "
        "mint nothing, which is why the verdict is about the upload and not about the write."),
    "test_live_docx_media_placement_gate.py": (
        "the placement arm exercises BOTH docx media routes - `put_image_in_document` "
        "(`parent_type: docx_image`) and `put_file_in_document` (`parent_type: docx_file`, "
        "through the type-33 view wrapper's child) - so a run mints on both routes, not one."),
    "test_live_drive_file_link_gate.py": (
        "the file-link arm uploads on TWO different routes and the STRONGER verdict governs: "
        "`put_file_in_folder` is a sweepable drive FILE object, but `put_file_in_document` "
        "rides `medias/upload_all` with `parent_type: docx_file` and that half is permanent, "
        "unpurgeable media. A row that averaged the two would under-price the run."),
    "test_live_sheets_float_image_gate.py": (
        "LD-435's float-image arm. Beat one is `medias/upload_all` with `parent_type: "
        "sheet_image` parented on the WORKBOOK (not on a cell), beat two binds it through "
        "`float_images`. The token outlives the bind: `remove_float_image_from_sheet` unbinds "
        "the picture and removes no bytes (D-95's *unbinding is not a purge*)."),
    "test_live_sheets_in_cell_image_gate.py": (
        "the in-cell image route has **NO `medias/upload_all` leg at all** - the bytes ride "
        "in the `values_image` JSON body and **Lark mints its OWN token** "
        "(`src/larkdocio/sheets/media.py` § Residue: *\"A successful call mints a permanent "
        "drive media token - Lark's own, not one you uploaded\"*). This row is the clearest "
        "argument for the classification being DATA rather than a grep: the minting call is "
        "not spelled like an upload anywhere in the file, and the residue is permanent all "
        "the same."),
    "test_live_sheets_ld472_doc_truth_gate.py": (
        "the LD-472 doc-truth re-measurement floats images to re-derive the single-cell- "
        "anchor refutation, so it rides the same `medias/upload_all` / `sheet_image` beat as "
        "the float arm - up to two sends per run, plus any orphan token a failed bind leaves. "
        "Its own docstring carries the disclosure and it PRINTS every token it mints, which "
        "is what makes the residue ledgerable after the fact."),
}

#: Sweepable, and recorded rather than left blank precisely because a grep finds them.
_SWEEPABLE_DRIVE_OBJECTS: dict[str, str] = {
    "test_live_drive_bytes_leg_gate.py": (
        "uploads a drive FILE OBJECT through `files/upload_all` with `parent_type: explorer`, "
        "which is **not drive media** - the library authors that distinction itself "
        "(`src/larkdocio/drive/files_write.py` § RESIDUE: media is permanent and unpurgeable, "
        "whereas *\"a file uploaded into a folder is a normal Drive object and `files.delete` "
        "removes it\"*, with the measured edge stated - the delete is **trash, not purge**, "
        "and the metadata route was observed still resolving a trashed token). So this ring "
        "costs a sweepable object and **no permanent media token**, and folding the two would "
        "tell a reader the wrong thing about residue. It is recorded here rather than left "
        "blank precisely because a grep for `upload` finds it and a reader has to be told why "
        "it is not gated."),
    "test_live_drive_chunked_upload_gate.py": (
        "uploads a drive FILE OBJECT through `files/upload_all` with `parent_type: explorer`, "
        "which is **not drive media** - the library authors that distinction itself "
        "(`src/larkdocio/drive/files_write.py` § RESIDUE: media is permanent and unpurgeable, "
        "whereas *\"a file uploaded into a folder is a normal Drive object and `files.delete` "
        "removes it\"*, with the measured edge stated - the delete is **trash, not purge**, "
        "and the metadata route was observed still resolving a trashed token). So this ring "
        "costs a sweepable object and **no permanent media token**, and folding the two would "
        "tell a reader the wrong thing about residue. It is recorded here rather than left "
        "blank precisely because a grep for `upload` finds it and a reader has to be told why "
        "it is not gated."),
    "test_live_drive_folder_create_gate.py": (
        "uploads a drive FILE OBJECT through `files/upload_all` with `parent_type: explorer`, "
        "which is **not drive media** - the library authors that distinction itself "
        "(`src/larkdocio/drive/files_write.py` § RESIDUE: media is permanent and unpurgeable, "
        "whereas *\"a file uploaded into a folder is a normal Drive object and `files.delete` "
        "removes it\"*, with the measured edge stated - the delete is **trash, not purge**, "
        "and the metadata route was observed still resolving a trashed token). So this ring "
        "costs a sweepable object and **no permanent media token**, and folding the two would "
        "tell a reader the wrong thing about residue. It is recorded here rather than left "
        "blank precisely because a grep for `upload` finds it and a reader has to be told why "
        "it is not gated."),
    "test_live_drive_upload_identity_gate.py": (
        "uploads a drive FILE OBJECT through `files/upload_all` with `parent_type: explorer`, "
        "which is **not drive media** - the library authors that distinction itself "
        "(`src/larkdocio/drive/files_write.py` § RESIDUE: media is permanent and unpurgeable, "
        "whereas *\"a file uploaded into a folder is a normal Drive object and `files.delete` "
        "removes it\"*, with the measured edge stated - the delete is **trash, not purge**, "
        "and the metadata route was observed still resolving a trashed token). So this ring "
        "costs a sweepable object and **no permanent media token**, and folding the two would "
        "tell a reader the wrong thing about residue. It is recorded here rather than left "
        "blank precisely because a grep for `upload` finds it and a reader has to be told why "
        "it is not gated."),
}

#: filename -> (ground key, note or None). Every remaining file, named literally.
_NO_MINT: dict[str, tuple[str, str | None]] = {
    # --- offline companions and offline support: no API call is possible from here ---
    "test_live_base_canary_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_computed_provenance_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_destructive_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_disposable_harness_offline.py": ("OFFLINE_BY_CONSTRUCTION", _MIRRORS_THE_NAME),
    "test_live_base_field_migration_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_link_resolution_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_media_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", _MIRRORS_THE_NAME),
    "test_live_base_minimal_form_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_read_arm_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_read_filter_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_read_raw_values_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_relational_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", _MIRRORS_THE_NAME),
    "test_live_base_row_hierarchy_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_schema_arm_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_schema_fields_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_schema_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", _MIRRORS_THE_NAME),
    "test_live_base_view_scoped_read_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_views_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_write_arm_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_base_write_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_comments_read_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_contacts_resolve_colleague_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_docx_folder_acl_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_docx_historical_read_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_docx_image_authoring_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_docx_media_placement_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", _MIRRORS_THE_NAME),
    "test_live_drive_access_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_drive_assets_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", _MIRRORS_THE_NAME),
    "test_live_drive_bytes_leg_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_drive_canary_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_drive_chunked_upload_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_drive_enumeration_arm_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_drive_file_link_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", _MIRRORS_THE_NAME),
    "test_live_drive_folder_create_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", _MIRRORS_THE_NAME),
    "test_live_drive_upload_identity_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", _MIRRORS_THE_NAME),
    "test_live_drive_versions_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_restructure_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_sheets_border_write_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_sheets_disposition_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_sheets_final_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_sheets_float_image_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_sheets_freeze_write_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_sheets_ghost_tab_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_sheets_hidden_tab_read_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", _MIRRORS_THE_NAME),
    "test_live_sheets_in_cell_image_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_sheets_ld472_doc_truth_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_sheets_lifecycle_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_sheets_revision_guard_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_sheets_style_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_sheets_style_write_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_sheets_tab_presentation_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_sheets_write_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_anchor_by_id_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_anchor_whitespace_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_authoring_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_batched_table_fill_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_comment_op_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_one_call_table_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_refusal_policy_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_round_trip_conservation_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_round_trip_escape_identity_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_round_trip_no_marker_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_round_trip_stale_document_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_round_trip_surgical_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_roundtrip_verb_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", _MIRRORS_THE_NAME),
    "test_live_docx_removal_routes_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", "it NAMES the uploader ops (`upload_all`, `upload_prepare`, `upload_media`, ...) inside a NEGATIVE assertion - the guard that none of them appears in its subject gate - so the markers are present precisely because nothing is minted."),
    "test_live_write_table_create_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_typed_create_returns_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_todo_done_edit_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_table_growth_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_w1_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_w2_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    "test_live_write_w3_gate_offline.py": ("OFFLINE_BY_CONSTRUCTION", None),
    # --- live rings whose `file_token` is a document/folder token, not media ---
    "test_live_comments_read_gate.py": ("THE_TOKEN_WORD_IS_NOT_A_MEDIA_TOKEN", (
        "its `file_token` is the disposable DOCUMENT id, keyed into the arm's own evidence "
        "ledger row.")),
    "test_live_docx_folder_acl_gate.py": ("THE_TOKEN_WORD_IS_NOT_A_MEDIA_TOKEN", (
        "its `file_token(...)` is the SDK builder argument on `DeleteFileRequest` for the "
        "disposable FOLDER it tears down.")),
    "test_live_docx_historical_read_gate.py": ("THE_TOKEN_WORD_IS_NOT_A_MEDIA_TOKEN", "its `file_token` is the disposable document id in the arm's evidence row."),
    "test_live_drive_access_gate.py": ("THE_TOKEN_WORD_IS_NOT_A_MEDIA_TOKEN", "its `file_token` is the disposable document id in the arm's evidence row."),
    "test_live_drive_versions_gate.py": ("THE_TOKEN_WORD_IS_NOT_A_MEDIA_TOKEN", (
        "its `file_token` / `empty_file_token` are the two disposable DOCUMENT ids the "
        "versions arm creates.")),
    "test_live_write_comment_op_gate.py": ("THE_TOKEN_WORD_IS_NOT_A_MEDIA_TOKEN", "its `file_token` is the disposable document id in the arm's evidence row."),
    # --- live rings with no upload call site on any minting surface ---
    "test_live_base_canary.py": ("NO_UPLOAD_CALL_SITE", (
        "the Base canary cites the media survival fact (`bitable_file` / `bitable_image` "
        "tokens outlive their table) as a limitation it must not create; it uploads nothing "
        "itself.")),
    "test_live_base_computed_provenance.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_base_destructive.py": ("NO_UPLOAD_CALL_SITE", "the arm says it in its own docstring: *\"Nothing here uploads media.\"*"),
    "test_live_base_disposable_harness.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_base_field_migration.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_base_link_resolution.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_base_minimal_form.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_base_read_arm.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_base_read_filter.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_base_read_raw_values.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_base_row_hierarchy.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_base_schema_arm.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_base_schema_fields.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_base_schema_gate.py": ("NO_UPLOAD_CALL_SITE", "the arm says it in its own docstring: *\"Nothing here uploads media.\"*"),
    "test_live_base_view_scoped_read.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_base_views.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_base_write_arm.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_base_write_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_canary.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_comment_anchor_zoo_arm.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_contacts_lookup.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_contacts_resolve_colleague.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_drive_assets_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_drive_canary.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_drive_enumeration_arm.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_restructure_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_border_write_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_dimension_write_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_disposition_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_dropdown_write_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_final_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_formula_write_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_freeze_write_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_ghost_tab_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_hidden_tab_read_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_lifecycle_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_merge_tab_write_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_revision_guard_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_rich_write_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_structural_write_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_style_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_style_write_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_tab_presentation_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_write_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_sheets_write_harness.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_anchor_by_id_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_anchor_whitespace_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_authoring_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_batched_table_fill_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_harness.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_mermaid_create_gate.py": ("NO_UPLOAD_CALL_SITE", (
        "a mermaid/board block is CREATED, never uploaded - the create route carries the "
        "drawing, there is no media leg, and the gate's PNG side is a download. A download "
        "mints nothing.")),
    "test_live_write_one_call_table_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_refusal_policy_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_round_trip_conservation_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_round_trip_escape_identity_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_round_trip_no_marker_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_round_trip_stale_document_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_round_trip_surgical_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_roundtrip_verb_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_docx_removal_routes_gate.py": ("NO_UPLOAD_CALL_SITE", "the arm's declared budget is ONE reclaimable docx document and `zero permanent media by construction`; its companion pins that no uploader name appears in it at all and that it never sets the mint consent variable."),
    "test_live_write_table_create_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_typed_create_returns_gate.py": ("NO_UPLOAD_CALL_SITE", "the arm's own budget says it: four reclaimable objects, `no media token minted`, and its companion pins that no uploader name appears in it at all."),
    "test_live_write_todo_done_edit_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_table_growth_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_w1_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_w2_gate.py": ("NO_UPLOAD_CALL_SITE", None),
    "test_live_write_w3_gate.py": ("NO_UPLOAD_CALL_SITE", None),
}


def _media_verdicts() -> dict[str, MediaVerdict]:
    built: dict[str, MediaVerdict] = {}
    for name, why in _MEDIA_MINTERS.items():
        built[name] = MediaVerdict(name, MediaMint.PERMANENT_MEDIA, why)
    for name, why in _SWEEPABLE_DRIVE_OBJECTS.items():
        built[name] = MediaVerdict(name, MediaMint.SWEEPABLE_DRIVE_OBJECT, why)
    for name, (ground, note) in _NO_MINT.items():
        built[name] = MediaVerdict(name, MediaMint.NONE, _NO_MINT_GROUNDS[ground], note)
    return built


#: One verdict per discovered file - the data half of the guardrail. `media_guardrail` reads
#: it; `tests/test_media_minting_guardrail.py` holds it exhaustive in both directions and
#: cross-checks every verdict against the file's own text.
MEDIA_VERDICTS: dict[str, MediaVerdict] = _media_verdicts()

MEDIA_TABLE_BEGIN = ".. BEGIN GENERATED MEDIA TABLE"
MEDIA_TABLE_END = ".. END GENERATED MEDIA TABLE"


def media_minting_gates() -> tuple[str, ...]:
    """The files whose live ring mints PERMANENT drive media - what the guardrail gates."""
    return tuple(
        sorted(n for n, v in MEDIA_VERDICTS.items() if v.mint is MediaMint.PERMANENT_MEDIA))


def sweepable_upload_gates() -> tuple[str, ...]:
    """Files that upload a drive FILE object. Recorded, deliberately NOT gated - a shipped
    delete removes one, which is the whole reason the two are not folded together."""
    return tuple(
        sorted(n for n, v in MEDIA_VERDICTS.items()
               if v.mint is MediaMint.SWEEPABLE_DRIVE_OBJECT))


def media_counts() -> dict[str, int]:
    """The media arithmetic, derived from the verdicts rather than restated."""
    return {
        "classified": len(MEDIA_VERDICTS),
        "mints_permanent_media": len(media_minting_gates()),
        "uploads_a_sweepable_object": len(sweepable_upload_gates()),
        "mints_nothing": sum(1 for v in MEDIA_VERDICTS.values() if v.mint is MediaMint.NONE),
    }


def render_media_mint_table() -> str:
    """Render the published media price list (the region pinned in this module's docstring).

    Regenerate after touching the verdicts::

        .venv/bin/python -c "import sys; sys.path.insert(0,'tests'); \\
            import gate_registry; print(gate_registry.render_media_mint_table(), end='')"
    """
    rows = [(n.removesuffix(".py"), MEDIA_VERDICTS[n].mint.name)
            for n in (*media_minting_gates(), *sweepable_upload_gates())]
    head = ("#", "live file whose run UPLOADS BYTES", "verdict")
    w_n = max(len(head[0]), len(str(len(rows))))
    w_f = max(len(head[1]), *(len(r[0]) for r in rows))
    w_k = max(len(head[2]), *(len(r[1]) for r in rows))
    lines = [
        f"| {head[0]:>{w_n}} | {head[1]:<{w_f}} | {head[2]:<{w_k}} |",
        f"|{'-' * (w_n + 1)}:|{'-' * (w_f + 2)}|{'-' * (w_k + 2)}|",
    ]
    for i, (name, kind) in enumerate(rows, start=1):
        lines.append(f"| {i:>{w_n}} | {name:<{w_f}} | {kind:<{w_k}} |")
    return "\n".join(lines) + "\n"
