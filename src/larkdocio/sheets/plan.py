"""larkdocio.sheets.plan — the previewer-backed plan + apply-log value objects (LD-125 T3).

Extracted verbatim from ``write_apply.py`` (behavior-preserving): the typed findings-agnostic
:class:`Refusal` vocabulary, the previewed :class:`PlanEntry`, the non-forgeable :class:`Plan`
(the ``_PLAN_TOKEN`` hard gate — a plan is produced ONLY by
:func:`larkdocio.sheets.ops.dry_run`, and there is deliberately no ``Plan.from_dict``), and
the JSON-serializable :class:`ApplyLogEntry` / :class:`ApplyLog`. Pure value objects — nothing
here opens a socket.

**The staleness guard is never silently off (LD-132 / dogfood F7).** Some spreadsheets report
a **constant ``0``** (or no value at all) from ``metainfo.properties.revision``, which made the
D5 compare-and-swap compare ``0 == 0`` and **silently no-op** — the advertised safety contract
was off and a consumer could not tell. Every plan now carries the tier-1 anchor's
**availability** explicitly (:func:`revision_guard_status` / :func:`revision_guard_semantics`,
surfaced as :attr:`Plan.revision_guard` + the WHY in :attr:`Plan.revision_guard_detail`), and
each entry states whether the **tier-2** value precondition covers it
(:attr:`PlanEntry.value_precondition`). The marker is **derived inside**
:meth:`Plan.__init__` from the plan's own revision — no code path (not even a future op family
whose preview leg forgets) can produce a plan that lacks it.

**The marker vocabulary is now shared, not mirrored (LD-143 / T1).** The two markers and the
:func:`revision_guard_status` classifier live in :mod:`larkdocio.common.staleness` — ONE core
with the docx surface, whose copy this module used to mirror **and had already drifted from**
(docx called a negative anchor ``unavailable``; this surface called it ``active``). The shared
core adopted the **stricter docx rule**, so a negative / negative-string ``revision`` now reads
``unavailable`` here too. That is a **disclosure** change only: tier-1 *enforcement* is the
independent ``live != expected`` compare in :func:`larkdocio.sheets.ops._apply_one`, which
never consults the marker — a negative-anchor plan still refuses ``STALE_SHEET`` with zero
writes on drift (pinned in ``tests/test_staleness_core.py``) — and no spreadsheet ``revision``
can be negative in the first place. Everything else stays per-surface: this module keeps its
own :func:`revision_guard_semantics` (the two-tier wording + the ``tiers`` key) and the sheets
enforcement semantics (resync-and-continue) are deliberately NOT shared.
"""
import json
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Iterable, Optional, Tuple

from larkdocio.common.staleness import (  # noqa: F401 — re-exported: this IS the public path
    REVISION_GUARD_ACTIVE,
    REVISION_GUARD_UNAVAILABLE,
    revision_guard_status,
)
from larkdocio.sheets.rich_encode import mention_open_ids
from larkdocio.sheets.write_range import WriteRange, parse_write_range


# The private construction token. Only this module holds it, so a :class:`Plan` can be
# built solely via :func:`dry_run` — a caller cannot hand-forge one from raw records
# (the sheets parity of the docx ``write.preview._PLAN_TOKEN`` hard gate).
_PLAN_TOKEN = object()


# --------------------------------------------------------------------------- #
# The two-tier staleness vocabulary (LD-132) — tier 1 = the `revision`          #
# compare-and-swap WHEN AVAILABLE; tier 2 = the value precondition, always.     #
#                                                                              #
# Tier 1's marker + classifier are RE-EXPORTED from the shared core             #
# (`larkdocio.common.staleness`, LD-143) — imported above, not defined here, so #
# this surface and docx cannot drift apart again. Tier 2 below is sheets-only.  #
# --------------------------------------------------------------------------- #

#: Tier 2 covers this entry: its target's raw value is re-read immediately before the write
#: and any drift refuses :data:`Refusal.PRECONDITION_MISMATCH`.
VALUE_PRECONDITION_ENFORCED = "enforced"
#: Tier 2 does **not** exist for this entry — a dropdown rule / structural dimension edit /
#: merge / tab op has no cell-value ``before`` to compare. Stated plainly rather than letting
#: a consumer assume a second tier that is not there.
VALUE_PRECONDITION_NONE = "none"

#: The tier-2 blurb carried in every plan's ``revision_guard_tiers`` (the per-entry truth is
#: each entry's own ``value_precondition``).
_TIER2_SUMMARY = (
    "enforced on every value / rich-cell / formula entry — the target is re-read immediately "
    "before its write and any drift refuses precondition-mismatch (a value / rich-cell entry "
    "compares the raw value; a FORMULA entry compares the EXPRESSION, because a computed "
    "value drifts whenever the referenced data changes); each entry's "
    "value_precondition says which entries this covers, and a dropdown-rule / structural / "
    "merge / tab entry has no cell-value precondition"
)


def revision_guard_semantics(revision) -> dict:
    """The complete, JSON-serializable staleness disclosure for a plan-time ``revision`` —
    ``{"status", "detail", "tiers"}``.

    ONE source for the marker, the WHY and the two-tier summary, so the plan, the apply-log
    and the docs cannot drift apart. Both statuses carry a non-empty ``detail`` (the
    mandatory-detail discipline: a marker with no WHY is a riddle).
    """
    status = revision_guard_status(revision)
    if status == REVISION_GUARD_UNAVAILABLE:
        detail = (
            f"tier 1 (the revision compare-and-swap) is UNAVAILABLE: the plan-time "
            f"spreadsheet revision read back as {revision!r} — some spreadsheets report a "
            f"constant 0 (or no properties.revision at all) from metainfo, so comparing that "
            f"anchor before a write cannot observe an advance and would be silently inert. "
            f"tier 2 (the value precondition) STILL enforces: {_TIER2_SUMMARY}. Entries whose "
            f"value_precondition is 'none' have NO second tier on this spreadsheet — they are "
            f"unguarded against a concurrent edit. The guard self-heals: ANY nonzero advance "
            f"before a write still refuses stale-sheet, and the next plan built on a nonzero "
            f"anchor marks itself 'active'."
        )
    else:
        detail = (
            f"tier 1 (the revision compare-and-swap) is ACTIVE on the plan-time anchor "
            f"revision={revision!r}: apply re-reads metainfo.properties.revision immediately "
            f"before EACH write and refuses stale-sheet (no write) if it advanced. tier 2 (the "
            f"value precondition) also enforces: {_TIER2_SUMMARY}."
        )
    return {
        "status": status,
        "detail": detail,
        "tiers": {
            "tier1_revision_compare_and_swap": status,
            "tier2_value_precondition": _TIER2_SUMMARY,
        },
    }


# --------------------------------------------------------------------------- #
# LD-148 — the plan-time MENTION-VALIDATION disclosure (never silently off).     #
#                                                                              #
# The same discipline as the tier-1 staleness marker above: the plan states     #
# whether the check RAN, and when it could not run it says so with the WHY —    #
# a silently-skipped validation is exactly how the T27 Blocker reached apply.   #
# --------------------------------------------------------------------------- #

#: The mention ``open_id`` existence check RAN for this plan; any id Lark **proved**
#: nonexistent is refused :data:`Refusal.UNKNOWN_MENTION` at plan time.
MENTION_VALIDATION_ACTIVE = "active"
#: The check could **not** run (the client seam offers no ``validate_user_ids``, or the
#: lookup call failed — no scope / network / API drift). **Disclosed, never silent:** the
#: plan's mention entries are NOT id-validated, so a nonexistent id will surface at apply
#: as a typed per-entry :data:`Refusal.API_ERROR` refusal instead (never a crash).
MENTION_VALIDATION_UNAVAILABLE = "unavailable"
#: There is nothing to validate — no entry in this plan writes a mention cell. No read call
#: was spent. (Stated rather than reported as "active" on an empty check.)
MENTION_VALIDATION_NOT_APPLICABLE = "not-applicable"

#: What the check does and does NOT prove — carried in every disclosure so a consumer never
#: over-reads it.
_MENTION_SCOPE_NOTE = (
    "the check proves only that the open_id EXISTS in the tenant directory (Lark answers a "
    "nonexistent id with 99992351 naming it); it does not prove the user is reachable, and a "
    "display name is deliberately NOT required — an app without the contact detail scope "
    "still gets a usable existence answer"
)


def mention_validation_semantics(record, mention_ids=()) -> dict:
    """The complete, JSON-serializable mention-validation disclosure for a plan.

    ``record`` is the validator's own result (``{"status", "detail", "checked", "resolved",
    "invalid"}``) or ``None``. A ``None`` record is **derived, never assumed**: with no
    mention id anywhere in the batch the plan is honestly
    :data:`MENTION_VALIDATION_NOT_APPLICABLE`; with mention ids present and no record
    attached it is :data:`MENTION_VALIDATION_UNAVAILABLE` **with the WHY** — so a plan can
    never look validated when it was not (the derive-inside-``Plan.__init__``
    discipline, applied to the second never-silent guard).
    """
    if record is not None:
        return {
            "status": record.get("status"),
            "detail": record.get("detail"),
            "checked": list(record.get("checked") or ()),
            "resolved": dict(record.get("resolved") or {}),
            "invalid": list(record.get("invalid") or ()),
        }
    ids = list(mention_ids)
    if not ids:
        return {
            "status": MENTION_VALIDATION_NOT_APPLICABLE,
            "detail": (
                "no entry in this plan writes an @mention cell, so no open_id validation was "
                f"needed and no read call was spent. (When one is: {_MENTION_SCOPE_NOTE}.)"
            ),
            "checked": [], "resolved": {}, "invalid": [],
        }
    return {
        "status": MENTION_VALIDATION_UNAVAILABLE,
        "detail": (
            f"this plan writes {len(ids)} @mention open_id(s) ({', '.join(sorted(ids))}) but "
            f"carries NO validation record — it was not built by a dry_run that validated "
            f"them, so the ids are UNVERIFIED. A nonexistent id will surface at apply as a "
            f"typed per-entry api-error refusal (the batch continues; nothing is lost), "
            f"never as a raised exception."
        ),
        "checked": [], "resolved": {}, "invalid": [],
    }


# --------------------------------------------------------------------------- #
# LD-150 — MORE THAN ONE DISCLOSURE PER ENTRY (a warning must never displace     #
# another warning). Before LD-150 `preview_note` was a single dict and the        #
# previewer's seam only stamped the `=`-prefix note when the op's own leg had     #
# set none — so an entry that earned two disclosures shipped one. That is the     #
# same class of bug as F8 (a warning lost between plan and log), so the fix is    #
# structural: notes COMPOSE into a `"multiple"` envelope, and `preview_notes`     #
# is the ONE uniform accessor over both shapes.                                  #
#                                                                               #
# ZERO-DRIFT: an entry with exactly one note serializes byte-identically to      #
# pre-LD-150 (the envelope appears only from the second note onward).            #
#                                                                               #
# LD-172 lifted the three names below into `larkdocio.common.notes` — ONE core,   #
# now shared with the docx write surface, which grew its own preview note (the    #
# reviewer-anchor disclosure on the sub-span path). Re-exported here, unchanged,  #
# so every existing `larkdocio.sheets.plan` import keeps resolving and the        #
# convention has exactly one definition rather than two that could drift.        #
# --------------------------------------------------------------------------- #

from larkdocio.common.notes import (  # noqa: E402  (re-export, deliberately late)
    NOTE_KIND_MULTIPLE,
    combine_preview_notes,
    preview_notes_of,
)


# --------------------------------------------------------------------------- #
# Refusal — the small, typed, findings-agnostic refusal vocabulary              #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Refusal:
    """Why a value-write entry was refused — a typed reason + an inspectable detail.

    All sheets-write-safety concerns (no consumer findings/status vocabulary): the
    ``revision`` compare-and-swap tripped (:data:`STALE_SHEET`), the target's current raw
    value drifted from the plan's capture (:data:`PRECONDITION_MISMATCH`), the target is a
    structured/rich cell — a rich-cell write, not this engine's plain-value slice
    (:data:`RICH_CELL_TARGET`), the range names a tab that **never existed**
    (:data:`UNKNOWN_TAB`), or a range that WAS readable became unreadable
    (:data:`TAB_VANISHED`).

    **``UNKNOWN_TAB`` vs ``TAB_VANISHED``.** The two are different
    stories with different repairs and must never be conflated:

    * :data:`UNKNOWN_TAB` — a **plan-time** identifier-kind error: the range's
      ``{sheet_id}!`` prefix is **not** among the spreadsheet's tabs (``query_tabs`` proves
      it). The classic case is passing a tab **title** where the ``sheet_id`` belongs (the
      guide's own ``"Sheet1!A1:A1"`` — Lark answers ``90215 not found sheetId``). The
      ``detail`` carries a **did-you-mean** listing the real ``(sheet_id, title)`` pairs, so
      the fix is one substitution and no re-read.
    * :data:`TAB_VANISHED` — a **staleness** story, **reserved** for a range that was
      readable at plan time and is unreadable now (or unreadable for a reason other than an
      unknown id). The repair is to re-read and re-plan.

    An earlier release refused ``TAB_VANISHED`` for every unreadable range, which told a consumer
    whose tab never existed to go re-plan a tab that was never there.
    """

    reason: str
    detail: Optional[str] = None

    STALE_SHEET = "stale-sheet"
    PRECONDITION_MISMATCH = "precondition-mismatch"
    RICH_CELL_TARGET = "rich-cell-target"
    #: LD-131 — the range names a ``sheet_id`` that is not a tab of this spreadsheet (the
    #: tab listing PROVES it never existed). A plan-time identifier-kind error, NOT
    #: staleness; the detail carries the did-you-mean ``(sheet_id, title)`` listing.
    UNKNOWN_TAB = "unknown-tab"
    #: The range was readable at plan time and is not now (or failed for a reason other
    #: than an unknown id) — the staleness story. See the class docstring for the split.
    TAB_VANISHED = "tab-vanished"
    #: LD-150 / dogfood **F21** — the proposed values matrix's **arity** does not match the
    #: target range's shape. Decided **pre-I/O** (the arity is knowable before any call), so
    #: the refusal costs zero reads. Refused rather than resolved because a wrong-arity write
    #: leaves the target's **uncovered** cells in a state the plan cannot describe — the
    #: observed failure mode is silently blanking them. The ``detail`` names **both** shapes,
    #: the offending range, and both repairs.
    SHAPE_MISMATCH = "shape-mismatch"
    #: LD-150 / dogfood **F20** — the range itself is **malformed** (Lark answers ``90202
    #: validate RangeVal fail``): reversed (``C3:A1``), or otherwise not an addressable
    #: ``Start:End``. A clean, actionable signal that used to be mislabelled
    #: :data:`TAB_VANISHED` — which sent a consumer whose tab was fine off to re-plan
    #: staleness. The ``detail`` names the offending range and the valid form.
    MALFORMED_RANGE = "malformed-range"
    #: A value write whose target intersects a merge's **covered** (non-anchor) cell
    #: (LD-122, D4). Writing into a merge-covered cell is refused — a merge
    #: keeps only its anchor's value, so a covered-cell write would be silently dropped or
    #: corrupt the merge. Detected only when the plan is given the tab's ``merges`` (the
    #: opt-in ``dry_run(..., merges=…)`` argument); a merge-unaware plan is unchanged.
    MERGED_CELL_TARGET = "merged-cell-target"
    #: LD-185 — a **dimension-property** write whose band runs past the tab's declared
    #: row/column count. Refused at **plan time**, off the geometry the leg already reads, so
    #: nothing is written: Lark itself rejects that band (probed — ``90202 dimension endIndex
    #: wrong, endIndex must less than or equal to sheetMaxRowCount``), and its message names
    #: neither the count nor the repair. The ``detail`` names both, plus how to grow the tab
    #: first if the band was the intent. Unlike a DELETE running past the edge (which Lark
    #: accepts and simply removes fewer rows — the ``out-of-bounds-dimension`` *note*), this
    #: one cannot succeed at all, so it is a refusal rather than a disclosure.
    OUT_OF_BOUNDS_DIMENSION = "out-of-bounds-dimension"
    #: LD-186 — a **freeze-panes** write asking to pin more leading rows/columns than the tab
    #: has. Refused at **plan time**, off the ``metainfo`` frozen read the freeze preview
    #: already makes, so nothing is written. Its own reason rather than
    #: :data:`OUT_OF_BOUNDS_DIMENSION`, because the two are different faults with different
    #: repairs: that one is a *band* of rows running past the edge, this one is a *count* of
    #: leading rows exceeding what exists, and the boundary is off by one between them —
    #: freezing **every** row is legal (probed: ``frozenRowCount == rowCount`` → ``code 0``),
    #: while a dimension band ending past the last row is not. Lark's own message
    #: (``90226 frozenRowCount must less than sheet rowCount``) **misstates** that boundary, so
    #: the detail carries the probed truth, the tab's real count and a valid example.
    FROZEN_COUNT_OUT_OF_RANGE = "frozen-count-out-of-range"
    #: LD-187 — a tab **reorder** whose target position is past the last tab. Refused at
    #: **plan time** off the tab query the preview already makes. Its own reason because the
    #: fault is unlike every other out-of-range: Lark does **not** reject it. It answers
    #: ``code 0`` and silently **clamps** the tab to the end (probed: ``index: 4`` and
    #: ``index: 99`` on a 4-tab spreadsheet both land the tab last). So there is no API error
    #: to surface and nothing would look wrong — which is exactly why it is refused here: a
    #: silent clamp means the position the caller stated is not the position they got.
    TAB_INDEX_OUT_OF_RANGE = "tab-index-out-of-range"
    #: LD-187 — a tab **retitle** to a title another tab already holds. Refused at **plan
    #: time**, quoting Lark's own answer (``90210 sheetTitle already exist in snapshot``) so a
    #: consumer sees the same fact one call earlier. The comparison is **exact and
    #: case-SENSITIVE**, matching the probed API: ``gamma`` beside an existing ``Gamma`` is a
    #: legal retitle (``code 0``), so case-folding this check would refuse a write that works.
    DUPLICATE_TAB_TITLE = "duplicate-tab-title"
    #: LD-187 — a **hide** that would leave the spreadsheet with no visible tab. Refused at
    #: **plan time**: Lark refuses it too, but with ``95201 server error`` — a body that names
    #: neither the fault nor the repair and reads like an outage. The refusal rests on
    #: **proof**, never a guess: a tab whose ``hidden`` state could not be read counts as
    #: possibly-visible, so an unknown never manufactures this refusal.
    LAST_VISIBLE_TAB = "last-visible-tab"

    # ------------------------------------------------------------------ #
    # LD-148 — the DISPOSITION vocabulary (dogfood round-2 T27).          #
    #                                                                     #
    # Before LD-148 the engine typed every failure it MODELLED and let a   #
    # raw transport exception escape `apply()` mid-batch, so the failing   #
    # entry AND the remainder got no disposition at all. The reasons below #
    # close that hole: every exception a per-entry step can raise now ends #
    # as one of them, and every entry the batch never reached is logged    #
    # `not-attempted`. See `larkdocio.sheets.disposition` for the          #
    # classification rules and `write_apply.apply` for the boundary.       #
    # (The count is deliberately NOT written here — a hand-kept "these N   #
    # reasons" goes stale the moment one is added, as LD-206 found it had.  #
    # `tests/test_sheets_plan_disclosure_completion.py` pins the set.)     #
    # ------------------------------------------------------------------ #

    #: **Plan-time** (LD-148 AC5): the mention's ``open_id`` does not exist — Lark's own
    #: directory lookup PROVED it (``contact/v3/users/batch`` → ``99992351`` naming the id
    #: in ``error.field_violations``). Refused by ``dry_run`` so the ``90204 id not found``
    #: class never reaches apply. The ``detail`` names the offending id.
    UNKNOWN_MENTION = "unknown-mention"
    #: **ENTRY-SCOPED** (LD-148 AC2): Lark answered this entry's own call with a non-zero
    #: code (the ``90204 id not found`` class). **Nothing landed** for this entry and the
    #: batch **CONTINUES** — the maintainer-blessed sheets per-entry doctrine. The ``detail``
    #: carries Lark's ``code``/``msg``.
    API_ERROR = "api-error"
    #: **ENTRY-SCOPED** (LD-148): a **local, pre-wire** validation error
    #: (:class:`~larkdocio.errors.LarkConfigError` — e.g. an un-emittable range). No call
    #: was made, **nothing landed**, and the batch **CONTINUES**.
    INVALID_REQUEST = "invalid-request"
    #: **SYSTEMIC** (LD-148 AC3): Lark's rate limit (``99991400``) survived the write
    #: transport's own backoff-and-retry. **Nothing landed** for this entry, and the batch
    #: **HALTS** — pressing on would only burn more budget. Every remaining entry is logged
    #: :data:`NOT_ATTEMPTED`.
    RATE_LIMITED = "rate-limited"
    #: **SYSTEMIC** (LD-148 AC3): the call failed **below Lark** — a socket/DNS/TLS failure
    #: (``URLError``), which the transport surfaces as a :class:`LarkAPIError` carrying **no
    #: ``code``**. Whether the write landed is **INDETERMINATE** (the request may or may not
    #: have reached Lark) — the log says so rather than guessing. The batch **HALTS**.
    TRANSPORT_FAILURE = "transport-failure"
    #: **SYSTEMIC** (LD-148 AC1): any other exception escaped the op leg (a library bug, an
    #: API-drift ``KeyError``, an un-modelled type). **INDETERMINATE**, and the batch
    #: **HALTS** — an unknown failure mode must never be assumed entry-local. Logged, never
    #: leaked.
    UNEXPECTED_ERROR = "unexpected-error"
    #: **SYSTEMIC after-effect** (LD-148 AC3): the batch halted at an earlier entry, so this
    #: one was **never attempted** — no call, nothing landed. Recorded explicitly because
    #: "absent from the log" is exactly the ambiguity T27 created.
    NOT_ATTEMPTED = "not-attempted"
    #: **SYSTEMIC** (LD-148): the entry's write op itself **returned** — the change **IS on
    #: the spreadsheet** — but a **post-write** step failed (the ``revision`` read-back, the
    #: mandatory geometry re-read, the merge re-read), so the entry's verification record is
    #: incomplete. Paired with outcome ``applied-unverified``. The batch **HALTS**: after an
    #: unverified write the compare-and-swap anchor is unknown, and continuing would judge
    #: every later entry against a revision the engine can no longer trust.
    UNVERIFIED_WRITE = "unverified-write"
    #: **SYSTEMIC**: Lark refused the call because the app lacks a required **scope** (the
    #: typed :class:`~larkdocio.errors.LarkPermissionError`). **Nothing landed** for this
    #: entry and the batch **HALTS** — this is the one coded failure whose blast radius is
    #: *knowable*: a missing grant would refuse every remaining entry too, so continuing
    #: would spend one throttled write call per entry on a condition that cannot clear
    #: between them, and report N unrelated-looking refusals instead of one condition. The
    #: repair is a **grant in the Lark console** (never something this library asks for),
    #: then re-``dry_run`` + re-apply the remainder. Every remaining entry is logged
    #: :data:`NOT_ATTEMPTED`, so the log stays complete.
    PERMISSION_DENIED = "permission-denied"

    @classmethod
    def stale_sheet(cls, *, cached, live) -> "Refusal":
        return cls(
            reason=cls.STALE_SHEET,
            detail=f"spreadsheet revision advanced {cached} -> {live} since plan time",
        )

    @classmethod
    def precondition_mismatch(cls, *, expected, live) -> "Refusal":
        return cls(
            reason=cls.PRECONDITION_MISMATCH,
            detail=f"target value drifted since plan time: expected {expected!r}, live {live!r}",
        )

    @classmethod
    def rich_cell_target(cls, detail: str) -> "Refusal":
        return cls(reason=cls.RICH_CELL_TARGET, detail=detail)

    @classmethod
    def tab_vanished(cls, detail: str) -> "Refusal":
        """A range that WAS readable is not now — the staleness story (re-read, re-plan).

        Never use this for a tab that never existed: that is :meth:`unknown_tab`."""
        return cls(reason=cls.TAB_VANISHED, detail=detail)

    @classmethod
    def unknown_tab(cls, detail: str) -> "Refusal":
        """The range names a ``sheet_id`` this spreadsheet does not have — an
        identifier-kind error caught at plan time, with a did-you-mean in the ``detail``."""
        return cls(reason=cls.UNKNOWN_TAB, detail=detail)

    @classmethod
    def merged_cell_target(cls, detail: str) -> "Refusal":
        return cls(reason=cls.MERGED_CELL_TARGET, detail=detail)

    # -- LD-185 factory (the dimension-property band vs the tab's declared grid) -- #

    @classmethod
    def out_of_bounds_dimension(cls, *, dimension, first, last, count, sheet_id) -> "Refusal":
        """A dimension-property band running past the tab's declared row/column count.

        Built here (not at the call site) so the wording is identical for both axes, and
        naming **all three** of what was asked, what exists, and how to get what was asked.
        """
        axis = "row" if dimension == "ROWS" else "column"
        ceiling = "sheetMaxRowCount" if dimension == "ROWS" else "sheetMaxColumnCount"
        grower = ("AppendDimension(sheet_id, 'ROWS', n)" if dimension == "ROWS"
                  else "AppendDimension(sheet_id, 'COLUMNS', n)")
        return cls(
            reason=cls.OUT_OF_BOUNDS_DIMENSION,
            detail=(
                f"out-of-bounds dimension band: this write names {axis}s {first}..{last} "
                f"(inclusive) on tab {sheet_id!r}, but the tab declares only {count} "
                f"{axis}(s). REFUSED BEFORE ANY WRITE — Lark rejects that band outright "
                f"('90202 dimension endIndex wrong, endIndex must less than or equal to "
                f"{ceiling}'), a message that names neither the count nor the repair. Either "
                f"narrow the band to last={count} or lower, or grow the tab first "
                f"({grower}) and re-plan — one batch is one snapshot, so the grow and the "
                f"property write must not be queued together."
            ),
        )

    # -- LD-186 factory (a frozen COUNT vs the tab's declared grid) ----------- #

    @classmethod
    def frozen_count_out_of_range(cls, *, axis, asked, count, sheet_id) -> "Refusal":
        """A freeze pinning more leading rows/columns than the tab has.

        Built here (not at the call site) so both axes read identically, and naming all four of
        what was asked, what exists, **where the boundary really is** (freezing every row is
        legal — the probed fact Lark's own message contradicts) and a valid form.
        """
        wire = "frozenRowCount" if axis == "row" else "frozenColCount"
        grid = "rowCount" if axis == "row" else "columnCount"
        kwarg = "rows" if axis == "row" else "cols"
        grower = ("AppendDimension(sheet_id, 'ROWS', n)" if axis == "row"
                  else "AppendDimension(sheet_id, 'COLUMNS', n)")
        return cls(
            reason=cls.FROZEN_COUNT_OUT_OF_RANGE,
            detail=(
                f"frozen {axis} count out of range: this write asks to freeze the first "
                f"{asked} {axis}(s) of tab {sheet_id!r}, but the tab declares only {count} "
                f"{axis}(s). REFUSED BEFORE ANY WRITE — Lark rejects it outright "
                f"('90226 {wire} must less than sheet {grid}'), and that message misstates the "
                f"boundary: freezing ALL {count} {axis}(s) is accepted (probed), it is only "
                f"{count} + 1 and above that fails. So either freeze at most "
                f"FreezePanes(sheet_id={sheet_id!r}, {kwarg}={count}), or grow the tab first "
                f"({grower}) and re-plan — one batch is one snapshot, so the grow and the "
                f"freeze must not be queued together."
            ),
        )

    # -- LD-187 factories (the three tab-presentation faults) ----------------- #

    @classmethod
    def tab_index_out_of_range(cls, *, asked, count, sheet_id) -> "Refusal":
        """A reorder past the last tab — the refusal that exists because Lark does NOT refuse.

        Built here (not at the call site) so the wording carries the probed truth every time:
        the call is *accepted* and the tab is *clamped*, which is a silent reinterpretation of
        the caller's stated intent and the one thing a plan-gated engine must not pass through.
        """
        last = count - 1
        return cls(
            reason=cls.TAB_INDEX_OUT_OF_RANGE,
            detail=(
                f"tab position out of range: this write asks to move tab {sheet_id!r} to "
                f"position {asked}, but the spreadsheet has {count} tab(s), so the positions "
                f"are 0..{last} (0-based — position 0 is the first tab). REFUSED BEFORE ANY "
                f"WRITE, and note WHY: Lark does not reject this. It answers success and "
                f"silently CLAMPS the tab to the end (probed), so the tab would move somewhere "
                f"you did not ask for while everything looked fine. Ask for at most "
                f"ReorderTab(sheet_id={sheet_id!r}, index={last}) — which IS the last position "
                f"— or re-read the tab list and re-plan if you expected more tabs."
            ),
        )

    @classmethod
    def duplicate_tab_title(cls, *, title, sheet_id, holder_sheet_id) -> "Refusal":
        """A retitle onto a title another tab already holds — Lark's own ``90210``, one call
        earlier, naming WHICH tab holds it (which Lark's message does not)."""
        return cls(
            reason=cls.DUPLICATE_TAB_TITLE,
            detail=(
                f"duplicate tab title: this write asks to retitle tab {sheet_id!r} to "
                f"{title!r}, but tab {holder_sheet_id!r} already carries that exact title. "
                f"REFUSED BEFORE ANY WRITE — Lark refuses it too ('90210 sheetTitle already "
                f"exist in snapshot'), without naming which tab is in the way. Note that the "
                f"check is EXACT and case-SENSITIVE, matching the API: a title differing only "
                f"in case is accepted (probed), so {title.lower()!r} beside {title!r} is a "
                f"legal rename. Pick another title, or retitle the other tab first and re-plan "
                f"— one batch is one snapshot, so the two renames must not be queued together."
            ),
        )

    @classmethod
    def last_visible_tab(cls, *, sheet_id, title=None) -> "Refusal":
        """A hide that would leave no visible tab — Lark's ``95201 server error`` replaced by a
        body that actually names the fault."""
        named = f" ({title!r})" if title else ""
        return cls(
            reason=cls.LAST_VISIBLE_TAB,
            detail=(
                f"last visible tab: this write asks to hide tab {sheet_id!r}{named}, which is "
                f"the only tab still visible — a spreadsheet cannot hide every tab. REFUSED "
                f"BEFORE ANY WRITE, and the reason it is refused HERE is the answer Lark gives: "
                f"'95201 server error', a body that names neither the fault nor the repair and "
                f"reads like an outage. Show another tab first "
                f"(SetTabVisibility.show(sheet_id=...)) and re-plan, or hide a different tab. "
                f"Remember that hiding never protects or removes data: a hidden tab stays fully "
                f"readable through this library."
            ),
        )

    # -- LD-150 factories (F21 / F20) ---------------------------------------- #

    @classmethod
    def shape_mismatch(cls, *, target, values) -> "Refusal":
        """The **pre-I/O** arity refusal — names both shapes and both repairs.

        ``target`` is the :class:`~larkdocio.sheets.write_range.WriteRange` being written and
        ``values`` the caller's proposed matrix. The detail is built here (not at the call
        site) so every family's wording is identical — the whole point of checking at one seam.
        """
        from larkdocio.sheets.write_range import (
            A1Cell,
            describe_matrix_shape,
            matrix_shape,
        )

        rows, cols = target.n_rows, target.n_cols
        shape = matrix_shape(values)
        if shape is None:
            repair = (
                f"Give the write a rectangular matrix of {rows} row(s) x {cols} col(s) — one "
                f"list per row, all the same length"
            )
        else:
            narrowed = WriteRange(
                target.start,
                A1Cell(target.start.col + shape[1] - 1, target.start.row + shape[0] - 1),
                sheet_id=target.sheet_id,
            ).a1()
            repair = (
                f"Either resize the matrix to {rows} row(s) x {cols} col(s), or narrow the "
                f"target to exactly the cells you are writing ({narrowed} covers a "
                f"{shape[0]}x{shape[1]} payload)"
            )
        return cls(
            reason=cls.SHAPE_MISMATCH,
            detail=(
                f"values shape mismatch: target {target.a1()} is {rows} row(s) x {cols} "
                f"col(s), but the proposed values are {describe_matrix_shape(values)}. "
                f"REFUSED BEFORE ANY CALL — nothing was read and nothing will be written. A "
                f"wrong-arity write leaves the target's uncovered cells in a state this plan "
                f"cannot describe (the observed failure is silently blanking them), so the "
                f"engine refuses rather than guess which cells you meant. {repair}."
            ),
        )

    @classmethod
    def malformed_range(cls, *, a1_range, detail: str = None, lark_code=None) -> "Refusal":
        """The range itself is not an addressable rectangle.

        Two arrivals, one reason — because the **repair is the same** either way:

        * **pre-I/O** (``lark_code is None``) — the engine saw it for itself (a reversed
          ``C3:A1``, a sub-``1`` coordinate, a column past the notation ceiling), so no call
          was made at all;
        * **from Lark** (``lark_code=90202``) — a range the engine had no rule for, rejected on
          the wire with ``validate RangeVal fail``.

        Never :meth:`tab_vanished`: the tab is readable, so re-planning cannot help — which is
        exactly why the old ``tab-vanished`` label cost the seat session its recovery.
        """
        from larkdocio.sheets.write_range import _A1_VALID_FORM

        if lark_code is not None:
            lead = (
                f"Lark rejected the RANGE with code {lark_code} (validate RangeVal fail) — that "
                f"is about the range, not the tab: the tab is readable, so this is NOT "
                f"staleness and re-planning will not help."
            )
        else:
            lead = (
                "refused BEFORE any call — the range is not an addressable rectangle, so no "
                "read and no write was attempted. This is NOT staleness (Lark answers this "
                "class of range with code 90202, validate RangeVal fail); re-planning will not "
                "help."
            )
        return cls(
            reason=cls.MALFORMED_RANGE,
            detail=(
                f"malformed A1 range {a1_range!r}: {lead} The usual cause is a REVERSED range — "
                f"write the top-left cell first ('A1:C3', not 'C3:A1'); a range whose end "
                f"precedes its start addresses no rectangle. {_A1_VALID_FORM}"
                + (f" (underlying: {detail})" if detail else "")
            ),
        )

    # -- LD-148 factories (every one carries a mandatory, actionable detail) -- #

    @classmethod
    def unknown_mention(cls, *, open_id, detail: str = None) -> "Refusal":
        """A plan-time refusal for a mention ``open_id`` Lark proved does not exist."""
        return cls(
            reason=cls.UNKNOWN_MENTION,
            detail=detail or (
                f"mention open_id {open_id!r} does not exist — Lark's own directory lookup "
                f"proved it at plan time, so this write is refused BEFORE apply (it is the "
                f"'90204 id not found' class that used to surface mid-batch). Fix the "
                f"open_id (a mention addresses a user by open_id, never by name — there is "
                f"no name lookup on this surface) and re-run dry_run."
            ),
        )

    @classmethod
    def api_error(cls, detail: str) -> "Refusal":
        """An **entry-scoped** Lark error: this entry did not land, the batch continued."""
        return cls(reason=cls.API_ERROR, detail=detail)

    @classmethod
    def invalid_request(cls, detail: str) -> "Refusal":
        """An **entry-scoped** local (pre-wire) validation error; the batch continued."""
        return cls(reason=cls.INVALID_REQUEST, detail=detail)

    @classmethod
    def rate_limited(cls, detail: str) -> "Refusal":
        """A **systemic** rate limit: nothing landed here and the batch halted."""
        return cls(reason=cls.RATE_LIMITED, detail=detail)

    @classmethod
    def transport_failure(cls, detail: str) -> "Refusal":
        """A **systemic** sub-Lark failure: whether the write landed is INDETERMINATE."""
        return cls(reason=cls.TRANSPORT_FAILURE, detail=detail)

    @classmethod
    def unexpected_error(cls, detail: str) -> "Refusal":
        """A **systemic** un-modelled exception, converted to a disposition (never leaked)."""
        return cls(reason=cls.UNEXPECTED_ERROR, detail=detail)

    @classmethod
    def unverified_write(cls, detail: str) -> "Refusal":
        """The write LANDED but its post-write verification failed; the batch halted."""
        return cls(reason=cls.UNVERIFIED_WRITE, detail=detail)

    @classmethod
    def permission_denied(cls, detail: str) -> "Refusal":
        """A **systemic** scope denial: nothing landed here and the batch halted, because a
        missing grant cannot clear between entries."""
        return cls(reason=cls.PERMISSION_DENIED, detail=detail)

    @classmethod
    def not_attempted(cls, *, halted_at, reason, detail: str = None) -> "Refusal":
        """This entry was never attempted — the batch halted at entry ``halted_at``."""
        return cls(
            reason=cls.NOT_ATTEMPTED,
            detail=detail or (
                f"NOT ATTEMPTED: the batch halted at entry #{halted_at} ({reason}), so no "
                f"call was made for this entry and nothing on the spreadsheet changed for "
                f"it. Resolve the halt, then dry_run + apply the remaining entries again."
            ),
        )

    def to_dict(self) -> dict:
        return {"reason": self.reason, "detail": self.detail}

    @classmethod
    def from_dict(cls, d: dict) -> "Refusal":
        return cls(reason=d["reason"], detail=d.get("detail"))


# --------------------------------------------------------------------------- #
# RefusalReason — the vocabulary, ON THE EXPORT SURFACE                         #
#                                                                              #
# LD-457: `Refusal.reason` is a plain string, so the ONLY spelling a `==`       #
# can match is the wire value. For fourteen releases the shipped guide wrote    #
# `STALE_SHEET` and the wire carried `stale-sheet`, so the retry guard the      #
# guide taught never fired and the refused write was dropped in silence.       #
# `Refusal`'s attributes (above, each with its story) stay the AUTHORING SITE;  #
# this namespace is their exported projection, so a consumer imports the        #
# spelling instead of typing it. The guard is in the source repository, not in the      #
# wheel: `tests/test_refusal_reason_vocabulary.py` enumerates the class and     #
# reddens if the two disagree, so a reason added later cannot ship unexported.  #
# --------------------------------------------------------------------------- #


class RefusalReason:
    """The sheets refusal-reason vocabulary — **import it, never type it**.

    Every value here is the exact string :attr:`Refusal.reason` carries on the wire, so a
    guard written against it fires::

        from larkdocio.sheets import RefusalReason

        for entry in log.entries:
            if entry.refusal is not None and entry.refusal.reason == RefusalReason.STALE_SHEET:
                ...   # re-read, re-plan, re-apply — the refusal is recoverable

    Each reason's meaning, its blast radius (entry-scoped or batch-halting) and its repair are
    documented on :class:`Refusal`, whose attributes these mirror one for one.

    This is a namespace of plain strings, deliberately not an enum: the values are what a
    serialized plan / apply-log already carries, and an existing comparison against the raw
    string keeps working unchanged.
    """

    __slots__ = ()

    #: The compare-and-swap tripped — the spreadsheet moved between the plan and the write.
    STALE_SHEET = Refusal.STALE_SHEET
    PRECONDITION_MISMATCH = Refusal.PRECONDITION_MISMATCH
    RICH_CELL_TARGET = Refusal.RICH_CELL_TARGET
    UNKNOWN_TAB = Refusal.UNKNOWN_TAB
    TAB_VANISHED = Refusal.TAB_VANISHED
    SHAPE_MISMATCH = Refusal.SHAPE_MISMATCH
    MALFORMED_RANGE = Refusal.MALFORMED_RANGE
    MERGED_CELL_TARGET = Refusal.MERGED_CELL_TARGET
    OUT_OF_BOUNDS_DIMENSION = Refusal.OUT_OF_BOUNDS_DIMENSION
    FROZEN_COUNT_OUT_OF_RANGE = Refusal.FROZEN_COUNT_OUT_OF_RANGE
    TAB_INDEX_OUT_OF_RANGE = Refusal.TAB_INDEX_OUT_OF_RANGE
    DUPLICATE_TAB_TITLE = Refusal.DUPLICATE_TAB_TITLE
    LAST_VISIBLE_TAB = Refusal.LAST_VISIBLE_TAB
    UNKNOWN_MENTION = Refusal.UNKNOWN_MENTION
    API_ERROR = Refusal.API_ERROR
    INVALID_REQUEST = Refusal.INVALID_REQUEST
    RATE_LIMITED = Refusal.RATE_LIMITED
    TRANSPORT_FAILURE = Refusal.TRANSPORT_FAILURE
    UNEXPECTED_ERROR = Refusal.UNEXPECTED_ERROR
    NOT_ATTEMPTED = Refusal.NOT_ATTEMPTED
    UNVERIFIED_WRITE = Refusal.UNVERIFIED_WRITE
    PERMISSION_DENIED = Refusal.PERMISSION_DENIED


#: ``{NAME: wire value}`` for every sheets refusal reason — the enumerable form, for a
#: consumer that logs, groups or routes on the reason rather than comparing one.
REFUSAL_REASONS = MappingProxyType({
    name: value
    for name, value in vars(RefusalReason).items()
    if name.isupper() and isinstance(value, str)
})


# --------------------------------------------------------------------------- #
# PlanEntry — the previewed outcome of ONE request (resolved / refused)         #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PlanEntry:
    """The previewed outcome of ONE write request — any of the **ten** request families
    (value / formula / rich-cell / dropdown-rule / structural / dimension-property / style /
    merge·unmerge / tab / freeze-panes), not only a value write. (An earlier release said
    "ONE ``ValueWriteRequest``"; the engine now previews all **ten** request families — the
    family is carried by :attr:`write_kind` and, for a structural / dimension-property / merge /
    tab / freeze entry, the :attr:`structural` descriptor's ``op``. The arity is
    :data:`larkdocio.sheets.ops.OPS`'s and is guarded, not restated —
    ``tests/test_sheets_registration_seam.py``; this docstring said **six** twice while
    :meth:`value_precondition` three hundred lines below said seven.)

    ``resolved`` — the write would proceed: for a value/rich/dropdown entry the ``target`` +
    the ``before`` (the current values read at plan time, ``None`` for a rule) + the ``after``
    (the proposed values / rule); for a structural/merge/tab entry ``target is None`` and the
    ``structural`` descriptor + previewed shift/loss ride in ``after``. ``refused`` — a typed
    :class:`Refusal` (a rich-cell target, an unreadable range, a merge-covered cell, an
    un-snapshottable destructive delete, caught at preview); the ``after`` intent is still
    carried so an approval UX can show the rejected op. A ``resolved`` entry is a *plan*, not
    an apply-log entry — nothing is written yet.
    """

    outcome: str
    target: Optional[WriteRange] = None
    before: Optional[object] = None
    after: Optional[object] = None
    refusal: Optional[Refusal] = None
    rich: bool = False
    #: The write endpoint a resolved entry drives — ``"value"`` (``put_values``),
    #: ``"data-validation"`` (``set_data_validation``, LD-120), or ``"structure"`` (a
    #: dimension write, LD-121). :func:`apply` dispatches its write step on this, so a
    #: dropdown-rule / structural entry never hits the value endpoint.
    write_kind: str = "value"
    #: A **structural** dimension write's descriptor (LD-121) — the op + native span +
    #: expected count, produced by the request's :meth:`descriptor`. ``None`` for a
    #: value / rich / dropdown-rule entry (which carries an A1 ``target`` instead). A
    #: structural entry has ``target is None`` and carries its previewed shift in
    #: :attr:`after`.
    structural: Optional[dict] = None
    #: The **tier-1** staleness status this entry is planned under (LD-132) —
    #: :data:`REVISION_GUARD_ACTIVE` / :data:`REVISION_GUARD_UNAVAILABLE`. Stamped by
    #: :meth:`Plan.__init__` from the plan's own revision, so an entry **inside a plan**
    #: always carries it; ``None`` means "a loose entry, not part of any plan yet".
    revision_guard: Optional[str] = None
    #: A **family-specific preview disclosure** (LD-149) — JSON-serializable, ``None`` for an
    #: entry that has nothing extra to say (and then absent from :meth:`to_dict` entirely, so
    #: every pre-LD-149 entry serializes byte-identically). Two producers today:
    #:
    #: * a **formula** entry carries its expression, the target's current expression AND
    #:   current computed value, and what the precondition compares
    #:   (:func:`~larkdocio.sheets.formula.formula_preview_note`);
    #: * **any** entry whose proposed values contain a ``=``-prefixed **plain string** carries
    #:   the loud inert-text warning (:data:`~larkdocio.sheets.formula.INERT_STRING_NOTE`) —
    #:   stamped at the previewer's single dispatch seam, so no family can forget it.
    #:
    #: A note is a **disclosure, not a verdict**: it rides a refused entry too, so an approval
    #: UX shows the warning either way.
    preview_note: Optional[dict] = None

    @classmethod
    def resolved(cls, *, target: WriteRange, before, after,
                 rich: bool = False, write_kind: str = "value") -> "PlanEntry":
        return cls(outcome="resolved", target=target, before=before, after=after,
                   rich=rich, write_kind=write_kind)

    @classmethod
    def resolved_structural(cls, *, structural: dict, after: dict,
                            write_kind: str = "structure") -> "PlanEntry":
        """A resolved **structural** dimension-write entry — no A1 target; the
        ``structural`` descriptor names the native span + expected count, and ``after``
        is the previewed shift (exactly what shifts)."""
        return cls(outcome="resolved", target=None, before=None, after=after,
                   write_kind=write_kind, structural=structural)

    @classmethod
    def refused(cls, *, target: WriteRange, after, refusal: Refusal) -> "PlanEntry":
        return cls(outcome="refused", target=target, after=after, refusal=refusal)

    @property
    def is_resolved(self) -> bool:
        return self.outcome == "resolved"

    @property
    def value_precondition(self) -> str:
        """The **tier-2** guard for THIS entry — derived, never asserted.

        :data:`VALUE_PRECONDITION_ENFORCED` for a value / rich-cell entry (its target's raw
        value is re-read immediately before the write and any drift refuses
        ``PRECONDITION_MISMATCH``); :data:`VALUE_PRECONDITION_NONE` for a dropdown-rule /
        structural / merge / tab entry, which has **no cell-value ``before``** to compare.

        A **formula** entry is ``enforced`` too, on a different basis: it compares the
        target's **expression** (``valueRenderOption=Formula``), not its computed value, because
        a computed value drifts whenever the referenced data changes and comparing it would
        refuse writes nobody made.

        Stated per entry because a blanket "the value precondition always backs you up" would
        be a lie for **seven** of the **ten** families (every family except value / formula /
        rich-cell — both numbers derived and guarded in
        ``tests/test_sheets_registration_seam.py``, the subset by asking this very property)
        — and on a spreadsheet whose tier-1 anchor is
        :data:`REVISION_GUARD_UNAVAILABLE` those entries have no staleness guard at all. A
        consumer that needs one can refuse to submit them (the library does not decide that
        for them — see the issue's rejected "refuse to plan" alternative).
        """
        if self.structural is None and self.write_kind in ("value", "formula"):
            return VALUE_PRECONDITION_ENFORCED
        return VALUE_PRECONDITION_NONE

    @property
    def preview_notes(self) -> Tuple[dict, ...]:
        """**Every** disclosure on this entry, uniformly.

        ``()`` when there is none, a 1-tuple for a single note, and each individual note when
        the entry carries several (a ``"multiple"`` envelope). Use this rather than
        :attr:`preview_note` whenever you want *all* the warnings — an entry can legitimately
        earn two (e.g. its target holds a live formula **and** its payload is an inert
        ``=``-string), and reading only the first is how a warning gets lost.
        """
        return preview_notes_of(self.preview_note)

    def with_revision_guard(self, status: str) -> "PlanEntry":
        """This entry, stamped with the plan's tier-1 :attr:`revision_guard` status.
        Called by :meth:`Plan.__init__` for **every** entry, so the marker cannot be forgotten
        by a preview leg."""
        return replace(self, revision_guard=status)

    @property
    def mention_open_ids(self) -> tuple:
        """Every ``open_id`` this entry would @mention — first-seen order, ``()``
        for an entry that mentions nobody.

        Read out of the entry's **proposed payload** (:attr:`after` + the
        :attr:`structural` descriptor) rather than off a request type, so the plan-time
        validation is **family-agnostic**: a mention riding in a 1×1 rich cell, inside a
        styled-run array, or in the rows of an ``AppendRowsWithValues`` is all found by the
        one decoder (:func:`~larkdocio.sheets.rich_encode.mention_open_ids`).
        """
        found: list = []
        for oid in mention_open_ids(self.after) + mention_open_ids(self.structural):
            if oid not in found:
                found.append(oid)
        return tuple(found)

    def to_dict(self) -> dict:
        d = {
            "outcome": self.outcome,
            "target": self.target.a1() if self.target is not None else None,
            "before": self.before,
            "after": self.after,
            "refusal": self.refusal.to_dict() if self.refusal is not None else None,
            "rich": self.rich,
            "write_kind": self.write_kind,
            # LD-132 — the two-tier staleness disclosure, per entry, always present.
            "revision_guard": self.revision_guard,
            "value_precondition": self.value_precondition,
        }
        if self.structural is not None:
            d["structural"] = self.structural
        # LD-149: present only when there IS a note, so every pre-LD-149 entry's serialized
        # shape is byte-identical (the zero-drift discipline applied to the wire form).
        if self.preview_note is not None:
            d["preview_note"] = self.preview_note
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PlanEntry":
        refusal = d.get("refusal")
        target = d.get("target")
        return cls(
            outcome=d["outcome"],
            target=parse_write_range(target) if target is not None else None,
            before=d.get("before"),
            after=d.get("after"),
            refusal=Refusal.from_dict(refusal) if refusal is not None else None,
            rich=bool(d.get("rich", False)),
            write_kind=d.get("write_kind", "value"),
            structural=d.get("structural"),
            revision_guard=d.get("revision_guard"),
            preview_note=d.get("preview_note"),
        )


# --------------------------------------------------------------------------- #
# Plan — the sole, non-forgeable hand-off type into apply                       #
# --------------------------------------------------------------------------- #

class Plan:
    """An ordered, previewer-backed batch of :class:`PlanEntry` + the cached ``revision``.

    The **only** input :func:`apply` accepts. It cannot be hand-forged: its constructor is
    guarded by a module-private token, so the sole way to obtain a :class:`Plan` is
    :func:`dry_run` (which reads every target's current values and caches the ``revision``).
    ``Plan(...)`` from arbitrary records raises :class:`TypeError`. There is intentionally
    **no** ``from_dict`` — a plan is trusted *because* it came from the previewer, and
    reconstructing one from JSON would re-open the forge vector the hard gate closes.

    Inspectable / serializable for a consumer's approval UX: iterate :attr:`entries` (or the
    :attr:`resolved` / :attr:`refusals` partitions), or serialize with :meth:`to_dict` /
    :meth:`to_json`. :attr:`revision` is the plan-time compare-and-swap anchor;
    :attr:`spreadsheet_token` is the target spreadsheet.

    **The staleness disclosure.** :attr:`revision_guard` states whether tier 1 (the
    ``revision`` compare-and-swap) is ``"active"`` or ``"unavailable"`` on this plan's anchor,
    :attr:`revision_guard_detail` says WHY, and :attr:`revision_guard_tiers` names both tiers;
    every entry is stamped with the same status and reports its own tier-2 coverage. All three
    are **derived from :attr:`revision` in the constructor** — there is no writable slot and no
    way to construct a plan without them, so the guard can never be silently off.
    """

    __slots__ = ("_entries", "_revision", "_spreadsheet_token", "_mention_validation")

    def __init__(self, entries: Iterable[PlanEntry] = (), *, revision=None,
                 spreadsheet_token=None, mention_validation=None, _token: object = None):
        if _token is not _PLAN_TOKEN:
            raise TypeError(
                "Plan objects are produced only by larkdocio.sheets.write_apply.dry_run(...); "
                "construct a plan via the previewer, not directly."
            )
        # LD-132: stamp EVERY entry with the tier-1 status derived from this plan's own
        # anchor. Doing it here — at the one seam every plan must pass through — is what
        # makes "no plan lacks the marker" structural rather than a per-leg convention.
        guard = revision_guard_status(revision)
        stamped = tuple(e.with_revision_guard(guard) for e in entries)
        object.__setattr__(self, "_entries", stamped)
        object.__setattr__(self, "_revision", revision)
        object.__setattr__(self, "_spreadsheet_token", spreadsheet_token)
        # LD-148: the mention-validation disclosure is DERIVED here too — the same seam,
        # the same reason. A plan handed no validation record still states the truth
        # (not-applicable with no mention in the batch, unavailable-with-the-WHY when there
        # is one), so no code path can produce a plan that looks id-validated when it is not.
        mention_ids: list = []
        for entry in stamped:
            for oid in entry.mention_open_ids:
                if oid not in mention_ids:
                    mention_ids.append(oid)
        object.__setattr__(self, "_mention_validation",
                           mention_validation_semantics(mention_validation, mention_ids))

    @property
    def entries(self) -> Tuple[PlanEntry, ...]:
        return self._entries

    @property
    def revision(self):
        return self._revision

    @property
    def revision_guard(self) -> str:
        """Tier 1's availability on this plan's anchor — ``"active"`` /
        ``"unavailable"``. Derived from :attr:`revision`, never stored or settable."""
        return revision_guard_status(self._revision)

    @property
    def revision_guard_detail(self) -> str:
        """WHY tier 1 is active / unavailable, and what still guards the batch either way."""
        return revision_guard_semantics(self._revision)["detail"]

    @property
    def revision_guard_tiers(self) -> dict:
        """The two-tier story as data: ``tier1_revision_compare_and_swap`` (this plan's
        status) + ``tier2_value_precondition`` (what the per-entry precondition covers)."""
        return revision_guard_semantics(self._revision)["tiers"]

    @property
    def spreadsheet_token(self):
        return self._spreadsheet_token

    @property
    def mention_validation(self) -> str:
        """Whether the plan-time @mention ``open_id`` check ran — ``"active"`` /
        ``"unavailable"`` / ``"not-applicable"``. Derived in the constructor; never silent."""
        return self._mention_validation["status"]

    @property
    def mention_validation_detail(self) -> str:
        """WHY the mention check is active / unavailable / not-applicable, and what that
        means for this plan's mention entries."""
        return self._mention_validation["detail"]

    @property
    def mention_validation_ids(self) -> dict:
        """The check as data — ``{"checked", "resolved", "invalid"}``: the ids looked up, any
        display names the lookup happened to return, and the ids Lark **proved** nonexistent
        (each of which refused :data:`Refusal.UNKNOWN_MENTION` in this plan)."""
        return {
            "checked": list(self._mention_validation["checked"]),
            "resolved": dict(self._mention_validation["resolved"]),
            "invalid": list(self._mention_validation["invalid"]),
        }

    @property
    def resolved(self) -> Tuple[PlanEntry, ...]:
        return tuple(e for e in self._entries if e.is_resolved)

    @property
    def refusals(self) -> Tuple[PlanEntry, ...]:
        return tuple(e for e in self._entries if not e.is_resolved)

    def __iter__(self):
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        # The guard status rides in the repr because `print(plan)` is a consumer's first
        # move — an inert anchor must be visible without reading the JSON (LD-132).
        return (
            f"Plan(resolved={len(self.resolved)}, refused={len(self.refusals)}, "
            f"revision={self._revision}, revision_guard={self.revision_guard})"
        )

    def to_dict(self) -> dict:
        semantics = revision_guard_semantics(self._revision)
        return {
            "spreadsheet_token": self._spreadsheet_token,
            "revision": self._revision,
            # LD-132 — the consumer-visible staleness disclosure. Always present: the
            # dry-run output can never be silent about the guard's state.
            "revision_guard": semantics["status"],
            "revision_guard_detail": semantics["detail"],
            "revision_guard_tiers": semantics["tiers"],
            # LD-148 — the plan-time @mention id check, disclosed the same way: a consumer
            # reading only the JSON can tell a validated batch from an unvalidated one.
            "mention_validation": self.mention_validation,
            "mention_validation_detail": self.mention_validation_detail,
            "mention_validation_ids": self.mention_validation_ids,
            "entries": [e.to_dict() for e in self._entries],
        }

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), **kwargs)


# --------------------------------------------------------------------------- #
# ApplyLogEntry / ApplyLog — the JSON-serializable record of a processed batch  #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ApplyLogEntry:
    """The record of ONE processed plan entry — its **disposition**.

    ``applied`` carries the target + the ``before`` (the live values actually replaced) +
    the ``after`` (written values) + the **post-write ``revision``**. ``stale`` and
    ``refused`` carry the target + the typed :class:`Refusal` and no write happened.

    **The complete outcome vocabulary.** Every entry of an
    :func:`~larkdocio.sheets.write_apply.apply` run ends in exactly one of these, always —
    that completeness *is* the contract the undo / disclosure story rests on:

    ========================= ============ ==================================================
    ``outcome``               landed?      meaning
    ========================= ============ ==================================================
    ``applied``               **yes**      the write went through and was verified.
    ``applied-unverified``    **yes**      the write op returned (the change IS on the sheet)
                                           but a **post-write** step failed, so the
                                           verification record is incomplete
                                           (:data:`Refusal.UNVERIFIED_WRITE`); the batch
                                           halted.
    ``stale``                 no           the compare-and-swap tripped
                                           (:data:`Refusal.STALE_SHEET`) — no write issued.
    ``refused``               no           a typed refusal: decided at plan time, or the
                                           precondition / an **entry-scoped** API error
                                           (:data:`Refusal.API_ERROR`) at apply time.
    ``failed``                **unknown**  the attempt failed in a way that leaves whether it
                                           landed **INDETERMINATE**
                                           (:data:`Refusal.TRANSPORT_FAILURE` /
                                           :data:`Refusal.UNEXPECTED_ERROR`); the batch
                                           halted. Deliberately NOT called a refusal — the
                                           engine does not know, and says so.
    ``not-attempted``         no           the batch halted at an earlier entry; nothing was
                                           issued for this one
                                           (:data:`Refusal.NOT_ATTEMPTED`).
    ========================= ============ ==================================================
    """

    outcome: str
    target: Optional[WriteRange] = None
    before: Optional[object] = None
    after: Optional[object] = None
    revision: Optional[int] = None
    refusal: Optional[Refusal] = None
    #: The write endpoint an applied entry drove — ``"value"`` / ``"data-validation"``
    #: (LD-120) / ``"structure"`` (LD-121) — so the apply-log record names the op, not
    #: only the payload shape.
    write_kind: str = "value"
    #: A **structural** dimension write's log record (LD-121) — the descriptor plus the
    #: verification (the trusted reply ``addCount``/``delCount``, the re-read geometry
    #: delta, and whether they matched the requested span). ``None`` for a value / rich /
    #: dropdown-rule entry.
    structural: Optional[dict] = None
    #: The **plan-time tier-1 status** this entry was processed under (LD-132) — stamped by
    #: :func:`~larkdocio.sheets.ops.apply` for every log entry, so an applied write on a
    #: revision-0 spreadsheet is no longer indistinguishable from a fully guarded one in the
    #: audit record. ``None`` only on a hand-built entry that never went through ``apply``.
    revision_guard: Optional[str] = None
    #: A **formula** write's verification record (LD-149) — the sent expression, the stored
    #: expression + computed value read back **after** the write, and the ``evaluated`` /
    #: ``error_value`` / ``normalized`` flags with a mandatory WHY
    #: (:func:`~larkdocio.sheets.formula.formula_record`). ``None`` for every other family.
    #:
    #: **``evaluated: False`` is the one thing to check.** Lark **accepts** an unparsable
    #: formula with ``code 0`` and stores it as inert text, so there is no API error to catch
    #: — this record is the detection. The write DID land, so the outcome stays ``applied``
    #: (denying a real change would be a worse lie); :attr:`formula_evaluated` and
    #: :attr:`ApplyLog.formula_not_evaluated` make the check one line.
    formula: Optional[dict] = None
    #: The plan entry's :attr:`PlanEntry.preview_note`, **carried** onto this log entry
    #: (LD-150 / dogfood **F8**).
    #:
    #: **The bug this closes.** The log used to build a *fresh* record on success, so every
    #: disclosure the plan had earned — including the LOUD inert-``=``-string warning — died at
    #: the plan→log boundary: "the warning is loud only to an interactive operator; a CI job or
    #: background batch gets a green log". It is now stamped by
    #: :func:`~larkdocio.sheets.ops.apply` for **every** entry of **every** disposition, at the
    #: one seam every log entry passes through (the same structural discipline as
    #: :attr:`revision_guard`), so no future op family can drop it.
    #:
    #: A carried note is a **disclosure, not a verdict** — it says what the plan warned about,
    #: never whether the write landed (:attr:`outcome` says that). Use :attr:`preview_notes` to
    #: read them all, and :attr:`ApplyLog.inert_formula_strings` for the one-line CI check.
    preview_note: Optional[dict] = None

    @classmethod
    def applied(cls, *, target: WriteRange, before, after, revision,
                write_kind: str = "value", formula: Optional[dict] = None) -> "ApplyLogEntry":
        return cls(outcome="applied", target=target, before=before, after=after,
                   revision=revision, write_kind=write_kind, formula=formula)

    @classmethod
    def applied_structural(cls, *, structural: dict, revision,
                           write_kind: str = "structure") -> "ApplyLogEntry":
        """An applied **structural** dimension write — no A1 target; the
        ``structural`` record carries the op + the trusted reply count + the mandatory
        geometry re-read + the shift verification."""
        return cls(outcome="applied", target=None, revision=revision,
                   write_kind=write_kind, structural=structural)

    @classmethod
    def stale(cls, *, target: Optional[WriteRange] = None, refusal: Refusal,
              structural: Optional[dict] = None) -> "ApplyLogEntry":
        return cls(outcome="stale", target=target, refusal=refusal, structural=structural)

    @classmethod
    def refused(cls, *, target: Optional[WriteRange] = None, refusal: Refusal,
                write_kind: str = "value",
                structural: Optional[dict] = None) -> "ApplyLogEntry":
        return cls(outcome="refused", target=target, refusal=refusal,
                   write_kind=write_kind, structural=structural)

    # -- LD-148 — the three dispositions an escaping exception used to leave blank -- #

    @classmethod
    def failed(cls, *, target: Optional[WriteRange] = None, refusal: Refusal,
               write_kind: str = "value",
               structural: Optional[dict] = None) -> "ApplyLogEntry":
        """An attempt whose result is **INDETERMINATE** (transport / unexpected). Never
        recorded as a refusal, because the engine does not know that nothing landed."""
        return cls(outcome="failed", target=target, refusal=refusal,
                   write_kind=write_kind, structural=structural)

    @classmethod
    def applied_unverified(cls, *, target: Optional[WriteRange] = None, before=None,
                           after=None, refusal: Refusal, write_kind: str = "value",
                           structural: Optional[dict] = None) -> "ApplyLogEntry":
        """The write **landed** but a post-write verification step failed. ``revision`` is
        deliberately ``None`` — the post-write anchor is exactly what could not be read."""
        return cls(outcome="applied-unverified", target=target, before=before, after=after,
                   revision=None, refusal=refusal, write_kind=write_kind,
                   structural=structural)

    @classmethod
    def not_attempted(cls, *, target: Optional[WriteRange] = None, refusal: Refusal,
                      write_kind: str = "value",
                      structural: Optional[dict] = None) -> "ApplyLogEntry":
        """The batch halted earlier, so this entry was never attempted — logged explicitly
        (an entry missing from the log is exactly the ambiguity this closes)."""
        return cls(outcome="not-attempted", target=target, refusal=refusal,
                   write_kind=write_kind, structural=structural)

    @property
    def is_applied(self) -> bool:
        """True when the write **landed** — ``applied`` or ``applied-unverified``.

        An ``applied-unverified`` entry IS on the spreadsheet; reporting it as "not applied"
        would make :attr:`ApplyLog.refusals` lie about a real change. Use
        :attr:`is_verified` when the distinction matters.
        """
        return self.outcome in ("applied", "applied-unverified")

    @property
    def is_verified(self) -> bool:
        """True only for a fully verified ``applied`` entry."""
        return self.outcome == "applied"

    @property
    def is_indeterminate(self) -> bool:
        """True when whether this entry landed is **unknown** (``failed``)."""
        return self.outcome == "failed"

    @property
    def formula_evaluated(self) -> Optional[bool]:
        """Did this **formula** write actually become an evaluating formula?

        ``True`` / ``False`` for a formula entry that was verified, ``None`` for any other
        family (and for a formula entry whose verification never ran). ``False`` means the
        cell now holds **inert text** — the write landed, Lark could not parse the expression,
        and it answered ``code 0`` while doing so. This one-line accessor exists because
        digging that out of the ``formula`` dict is exactly the check a consumer would skip.
        """
        if not self.formula:
            return None
        return bool(self.formula.get("evaluated"))

    @property
    def preview_notes(self) -> Tuple[dict, ...]:
        """**Every** disclosure carried from the plan onto this entry, uniformly —
        the log-side twin of :attr:`PlanEntry.preview_notes`."""
        return preview_notes_of(self.preview_note)

    @property
    def stored_inert_formula_string(self) -> bool:
        """True iff this entry's write **landed** and what it stored was a ``=``-prefixed
        **plain string** — i.e. the cell now holds inert text that looks like a formula.

        Read off the carried plan-time disclosure (the
        ``equals-prefixed-plain-string`` note), so it needs no extra read-back: the note was
        proven from the payload itself, and Lark has **no** ``valueInputOption`` that could have
        turned that string into a formula. Refused / stale / not-attempted entries are excluded
        — nothing was stored, and reporting them would send a consumer hunting for text that is
        not on the sheet.
        """
        if not self.is_applied:
            return False
        return any(n.get("kind") == "equals-prefixed-plain-string"
                   for n in self.preview_notes)

    def with_revision_guard(self, status: str) -> "ApplyLogEntry":
        """This log entry, stamped with the plan-time tier-1 status."""
        return replace(self, revision_guard=status)

    def with_preview_note(self, note: Optional[dict]) -> "ApplyLogEntry":
        """This log entry, stamped with the plan entry's disclosure.

        Called by :func:`~larkdocio.sheets.ops.apply` for **every** entry, so a warning cannot
        be lost by a disposition arm that forgets to copy it — the fix is that the
        plan→log transition **carries** disclosure rather than rebuilding it. An entry that
        already carries one keeps it (the arms that build their own compose, never replace)."""
        if note is None:
            return self
        return replace(self, preview_note=combine_preview_notes(self.preview_note, note))

    def to_dict(self) -> dict:
        d = {
            "outcome": self.outcome,
            "target": self.target.a1() if self.target is not None else None,
            "before": self.before,
            "after": self.after,
            "revision": self.revision,
            "refusal": self.refusal.to_dict() if self.refusal is not None else None,
            "write_kind": self.write_kind,
            # LD-132 — the plan-time staleness status this entry ran under.
            "revision_guard": self.revision_guard,
        }
        if self.structural is not None:
            d["structural"] = self.structural
        # LD-149: present only for a formula entry, so every other family's serialized shape
        # is byte-identical to pre-LD-149.
        if self.formula is not None:
            d["formula"] = self.formula
        # LD-150: present only when the plan actually warned about something, so every
        # warning-free entry's serialized shape is byte-identical to pre-LD-150.
        if self.preview_note is not None:
            d["preview_note"] = self.preview_note
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ApplyLogEntry":
        refusal = d.get("refusal")
        target = d.get("target")
        return cls(
            outcome=d["outcome"],
            target=parse_write_range(target) if target is not None else None,
            before=d.get("before"),
            after=d.get("after"),
            revision=d.get("revision"),
            refusal=Refusal.from_dict(refusal) if refusal is not None else None,
            write_kind=d.get("write_kind", "value"),
            structural=d.get("structural"),
            revision_guard=d.get("revision_guard"),
            formula=d.get("formula"),
            preview_note=d.get("preview_note"),
        )


@dataclass(frozen=True)
class ApplyLog:
    """The 1:1, in-order record of an :func:`apply` run — one entry per plan entry.

    **The completeness invariant.** ``len(log.entries) == len(plan.entries)``,
    in plan order, for **every** run — including one that hit an exception, halted, or
    both. There is no path on which an entry is silently absent: the disposition boundary
    in :func:`~larkdocio.sheets.write_apply.apply` converts every exception into an entry,
    and everything after a halt is recorded ``not-attempted``.

    :attr:`halt` is the batch-level disclosure: ``None`` when the whole batch was processed,
    else ``{"index", "reason", "detail", "not_attempted"}`` naming the entry the batch
    stopped at and why.
    """

    entries: Tuple[ApplyLogEntry, ...] = ()
    #: LD-148 — the batch-halt disclosure (``None`` ⇒ the batch ran to the end).
    halt: Optional[dict] = None

    def __iter__(self):
        """Iterate the entries (LD-458) — ``for entry in log:`` on every apply-log this
        library ships."""
        return iter(self.entries)

    def __len__(self) -> int:
        """How many entries — 1:1 with the plan (the completeness invariant above)."""
        return len(self.entries)

    @property
    def applied(self) -> Tuple[ApplyLogEntry, ...]:
        """Every entry whose write **landed** (``applied`` + ``applied-unverified``)."""
        return tuple(e for e in self.entries if e.is_applied)

    @property
    def refusals(self) -> Tuple[ApplyLogEntry, ...]:
        """Every entry that did **not** land — including the ``failed`` /
        ``not-attempted`` dispositions."""
        return tuple(e for e in self.entries if not e.is_applied)

    @property
    def indeterminate(self) -> Tuple[ApplyLogEntry, ...]:
        """Every entry whose fate is **unknown** (``failed``) — the set a consumer must
        reconcile by hand before re-planning."""
        return tuple(e for e in self.entries if e.is_indeterminate)

    @property
    def not_attempted(self) -> Tuple[ApplyLogEntry, ...]:
        """Every entry the batch never reached because it halted."""
        return tuple(e for e in self.entries if e.outcome == "not-attempted")

    @property
    def formula_not_evaluated(self) -> Tuple[ApplyLogEntry, ...]:
        """Every **formula** entry whose write landed as **INERT TEXT**.

        Empty on a clean run. Non-empty means Lark could not parse those expressions and
        stored them as strings — while answering ``code 0``, which is why a green apply-log
        alone is not proof a formula is live. Half of the assertion a consumer's CI wants; the
        other half is :attr:`inert_formula_strings` (see there).
        """
        return tuple(e for e in self.entries if e.formula_evaluated is False)

    @property
    def inert_formula_strings(self) -> Tuple[ApplyLogEntry, ...]:
        """Every entry whose write **landed** and stored a ``=``-prefixed **plain string** —
        a cell that now displays ``=SUM(...)`` and computes **nothing**.

        **Why this exists.** :attr:`formula_not_evaluated` only sees the **formula family**: it
        asks "did this ``FormulaWriteRequest`` become a live formula?". A batch that wrote
        ``"=SUM(A1:A4)"`` as an ordinary **value** has no formula entry at all, so the guide's
        one-line CI assertion came back green on exactly the trap the dry-run had warned about
        loudly. This is the other half of that check, and the two together are what the guide's
        recipe now asserts::

            assert not log.formula_not_evaluated and not log.inert_formula_strings

        Refused / stale / not-attempted entries are excluded — they stored nothing.
        """
        return tuple(e for e in self.entries if e.stored_inert_formula_string)

    @property
    def halted(self) -> bool:
        """True when the batch stopped early on a **systemic** failure."""
        return self.halt is not None

    def to_dict(self) -> dict:
        return {"entries": [e.to_dict() for e in self.entries], "halt": self.halt}

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), **kwargs)
