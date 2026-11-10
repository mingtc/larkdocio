"""larkdocio.sheets.ops._styles — the CELL STYLE family — fill / font / number-format / border writes.

One family for both wire shapes (one range, or N in a batch call), with the export-leg cost,
partial-merge and border-not-verifiable disclosures its preview stamps. Named after
``requests/_styles.py``.

Split out of the flat 3,019-line ``sheets/ops.py`` by LD-532, **verbatim**. The
package's ``__init__`` holds the ``OPS`` registry, the dispatchers and the engine
loop, and re-exports every name defined here, so
``from larkdocio.sheets.ops import <name>`` is unchanged.
"""
from dataclasses import replace
from typing import Optional

from larkdocio.sheets.write_range import A1Cell, parse_write_range
from larkdocio.sheets.merge_geometry import _normalize_merge
from larkdocio.sheets.plan import ApplyLogEntry, PlanEntry, combine_preview_notes

from ._shared import (
    VerificationLeg,
    _post_write_revision,
    _revision_of,
    _unreadable_tab_refusal,
)


# --------------------------------------------------------------------------- #
# CELL STYLE (LD-188) — the preview + apply legs of a fill / font / number-format #
# write, promoted out of tests/sheets_write_harness.py::SheetsStyleWriter.        #
#                                                                              #
# No new gate wiring: WriteOpKind.STYLE / NUMBER_FORMAT were reserved in         #
# STYLE_LEG_OP_KINDS for exactly this write, and certify_gate_legs already       #
# refuses to certify it on the cheap values leg alone. What this family adds is  #
# the request type, the two client ops, and the DISCLOSURE of what that          #
# pre-wired leg costs.                                                          #
# --------------------------------------------------------------------------- #

#: The extra scope that leg needs, written ONCE in this module and referenced from the note, the
#: apply-log record and the disclosure text below. The requirement itself is authored in
#: :mod:`larkdocio.permissions` (the single source) — this is a reference to it, so the module
#: does not spell the string three times and cannot disagree with itself.
STYLE_LEG_SCOPE = "drive:export"

#: This family's verification leg — the xlsx export's resolved cell style
#: (:class:`~larkdocio.sheets.export_reader.ExportedCell`'s ``bold`` / ``italic`` /
#: ``fill_rgb`` / ``num_fmt``).
#:
#: **Why this leg.** Cell style is readable **nowhere else**: the values API answers values
#: (``FormattedValue`` shows the *effect* of a number format on the text, never the pattern),
#: ``metainfo`` and the v3 tab query carry no cell style at all, and the whole reason the L2
#: read exists is that ``xl/styles.xml`` is the only surface that reports it (LD-107 Q2). So
#: this op is in :data:`~larkdocio.sheets.requests.STYLE_LEG_OP_KINDS` — the same position the
#: dimension family is in, arrived at the same way.
#:
#: **This is the family whose key drifted** (LD-223): its two PREVIEW notes used to spell the
#: attribution ``leg`` while its apply log spelled it ``verified_by``. Both now go through
#: this one object, so the two surfaces cannot disagree again.
STYLE_VERIFICATION = VerificationLeg(
    id="xlsx-export-style-leg",
    # Recorded in every style apply-log entry, so the record states its own verification
    # posture rather than leaving a bare "applied" to be mistaken for "verified".
    note=(
        "verified by the export-based style leg — the xlsx export's resolved cell style "
        "(export_reader.ExportedCell bold / italic / fill_rgb / num_fmt), which is the ONLY "
        "read that can see a cell style at all (the values API carries none, and metainfo / "
        "the v3 tab query carry none — the premise the L2 read was built on). That leg is "
        "deliberately NOT run inside apply: an export is an asynchronous whole-workbook task "
        "(create -> poll -> download -> unzip -> parse, ~1.2 s measured and up to ~30 s worst "
        f"case) and it needs a third scope, {STYLE_LEG_SCOPE}, so paying it per entry would "
        "make a two-cell restyle cost more than the write. This op IS in STYLE_LEG_OP_KINDS, "
        "so certify_gate_legs REFUSES to certify "
        "it surgical until that leg has run; the live_write ring runs it "
        "(tests/test_live_sheets_style_write_gate.py), and a caller who wants it in-process "
        "runs SheetsExportReader.read_workbook(...) and reads the cell's bold / fill_rgb / "
        "num_fmt."
    ),
)

#: Authored on :data:`STYLE_VERIFICATION` above; these two names are references to it.
STYLE_VERIFICATION_LEG = STYLE_VERIFICATION.id
STYLE_VERIFICATION_NOTE = STYLE_VERIFICATION.note


def style_export_cost_note(desc) -> dict:
    """The ``style-verification-cost`` preview note — **the gate's price, on the plan** (AC6).

    A style write turns ``--verify-style`` **on automatically** (it is in
    :data:`~larkdocio.sheets.requests.STYLE_LEG_OP_KINDS`), and what that flag buys is not a
    cheap read: it is the asynchronous whole-workbook xlsx export. A caller who plans a style
    write and then wonders why proving it took thirty seconds and a scope they had not granted
    was told nothing — so the plan says it up front.

    The wording is **LD-152's own shipped export-cost wording** (``GUIDE.md`` § "What it
    costs" — ``create`` → poll → ``download`` → unzip → parse, **~1.2 s** measured,
    ``poll_interval=0.5s × max_polls=60`` so **~30 s** worst case, and the **third scope**
    :data:`STYLE_LEG_SCOPE`), quoted rather than re-coined, so the two cannot drift apart. Costs
    no API
    call: it is a statement about the *verification*, computed from the op kinds alone.
    """
    return {
        "kind": "style-verification-cost",
        **STYLE_VERIFICATION.attribution(),
        "scope": STYLE_LEG_SCOPE,
        "ranges": list(desc.get("ranges") or []),
        "note": (
            "STYLE VERIFICATION IS NOT FREE: this write is in STYLE_LEG_OP_KINDS, so "
            "--verify-style is auto-on and proving it surgical needs the export-based style "
            "leg — a second, asynchronous whole-workbook export task: create -> poll -> "
            "download -> unzip -> parse, for the ENTIRE spreadsheet however many tabs it has. "
            "Measured ~1.2 s on a small workbook; the poll loop is deliberately gentle and "
            "bounded (poll_interval=0.5s x max_polls=60), so the worst case is ~30 s before it "
            "raises rather than spinning. It also needs a third scope, "
            f"{STYLE_LEG_SCOPE}, on top of "
            "the write scopes; without it the export call is refused. Nothing is refused here "
            "and the write itself costs none of that — the price is the PROOF, which is why "
            "the leg is not run inside apply and why certify_gate_legs will not call this "
            "write surgical until you have run it (SheetsExportReader.read_workbook(...), or "
            "the live_write ring, which does)."
        ),
    }


def _merge_a1(sheet_id, merge) -> str:
    """A merge region (0-idx, END-inclusive) as an A1 range on ``sheet_id`` — so a disclosure can
    hand back the range that names the WHOLE region rather than describing it."""
    sr, er, sc, ec = _normalize_merge(merge)
    body = f"{A1Cell(sc + 1, sr + 1).a1()}:{A1Cell(ec + 1, er + 1).a1()}"
    return f"{sheet_id}!{body}" if sheet_id else body


def style_partial_merge_note(desc, merges) -> Optional[dict]:
    """The ``style-partial-merge`` preview note — or ``None`` when no target clips a merge.

    **A style lands on EXACTLY the cells its range names — a merge does not spread it.** This is
    the finding a first probe got wrong and a second one settled: styling the whole of a
    three-cell merge left all three cells styled, which *looked* like the merge spreading the
    style, but the range had simply named three cells. Styling the merge's **anchor alone**
    answered ``updatedCells: 1`` and left the covered cells carrying **no** style at all
    (``tests/captures/sheets-style-write-probe/captures/02-merge-anchor-only.json``, in the source repository).

    So the hazard is the opposite of the one first assumed: a target that names *part* of a merge
    leaves the rest of that region with different stored style — invisible while the cells stay
    merged, and plainly visible the moment the merge is dissolved. The note fires only for that
    partial case (a target that contains the whole region has nothing to disclose), names the
    region, and hands back the A1 range that would cover all of it.

    Deliberately a **note**, not a refusal — styling a merged heading through its anchor is
    completely ordinary — and worded in the shipped disclosure register of
    :func:`no_merge_at_range_note` / :func:`frozen_replacement_note`. Costs **no extra call**:
    the merges come from the read the preview already makes (or from the ``merges=`` the caller
    handed :func:`dry_run`).
    """
    if not merges:
        return None
    clipped = []
    for a1_range in desc.get("ranges") or []:
        target = parse_write_range(a1_range)
        for merge in merges:
            sr, er, sc, ec = _normalize_merge(merge)
            intersects = (max(target.start.row, sr + 1) <= min(target.end.row, er + 1)
                          and max(target.start.col, sc + 1) <= min(target.end.col, ec + 1))
            if not intersects:
                continue
            contains = (target.start.row <= sr + 1 and target.end.row >= er + 1
                        and target.start.col <= sc + 1 and target.end.col >= ec + 1)
            if contains:
                continue                     # the whole region is named — nothing to disclose
            clipped.append({
                "range": a1_range,
                "merge": [sr, er, sc, ec],
                "merge_range": _merge_a1(target.sheet_id, merge),
                "cells": (er - sr + 1) * (ec - sc + 1),
            })
    if not clipped:
        return None
    ranges = ", ".join(item["range"] for item in clipped)
    whole = ", ".join(item["merge_range"] for item in clipped)
    return {
        "kind": "style-partial-merge",
        "sheet_id": desc.get("sheet_id"),
        "merged_ranges": clipped,
        "whole_regions": [item["merge_range"] for item in clipped],
        "note": (
            f"THIS STYLE NAMES ONLY PART OF A MERGED REGION: {ranges} intersects a merge without "
            f"covering all of it. A style lands on EXACTLY the cells its range names — a merge "
            f"does NOT spread it (probed: styling a three-cell merge's anchor answered "
            f"updatedCells: 1 and left the other two cells with no style at all) — so the "
            f"region will end up with mixed stored style: invisible while the cells stay merged, "
            f"and plainly visible the moment the merge is dissolved. Nothing is refused; styling "
            f"a merged heading through its anchor is ordinary. If you meant the whole block, name "
            f"the whole region instead: {whole}."
        ),
    }


def style_border_not_verifiable_note(desc) -> Optional[dict]:
    """The ``style-border-not-verifiable`` preview note (LD-189) — or ``None`` when no span
    carries a border.

    **The awkward middle case, disclosed instead of hidden.** A border write is CONFIRMED: it
    lands, and the exported workbook carries it (each cell's ``s=`` index resolves to a
    ``xl/styles.xml`` ``borders`` entry, probed per edge). But the shipped
    :class:`~larkdocio.sheets.export_reader.ExportedCell` surfaces ``bold`` / ``italic`` /
    ``fill_rgb`` / ``num_fmt`` and **no border** — so the ``--verify-style`` export leg, which is
    auto-on for this write, physically cannot check that the border landed. Widening the reader is
    style READ, a different piece of work; what is NOT acceptable is a plan that turns a
    verification leg on and lets the caller believe it covered the border it did not look at.

    So the note states the gap in the same breath as the leg: the fill, font and number format in
    this write ARE verified, the border is NOT. Deliberately a **note**, not a refusal — a border
    write is completely ordinary, and fire-and-forget is a fine thing to choose knowingly. Costs
    no API call: it is computed from the descriptor the caller's own request produced.
    """
    bordered = [span_range
                for span in desc.get("spans") or []
                for span_range in (span.get("ranges") or [])
                if "borderType" in (span.get("style") or {})]
    if not bordered:
        return None
    ranges = ", ".join(bordered)
    return {
        "kind": "style-border-not-verifiable",
        "sheet_id": desc.get("sheet_id"),
        "border_ranges": bordered,
        **STYLE_VERIFICATION.attribution(),
        "note": (
            f"THE BORDER IN THIS WRITE IS NOT VERIFIED BY THE STYLE LEG: {ranges} sets a "
            f"borderType, and the export-based {STYLE_VERIFICATION_LEG} leg this write turns on "
            f"reads each cell's bold / italic / fill / number-format and NOT its border — the "
            f"shipped ExportedCell has no border field, so there is nothing for the differ to "
            f"compare. The border itself is real and does land (probed live per edge, read back "
            f"out of the export's own xl/styles.xml), and everything else in this style IS "
            f"verified as usual; the border alone is write-only as far as the gate is concerned. "
            f"Nothing is refused. If you need to prove a border landed, read the exported "
            f"workbook's xl/styles.xml yourself, "
            f"or check it in the "
            f"Lark UI."
        ),
    }


def _preview_style(request, client, spreadsheet_token, merges=None) -> PlanEntry:
    """Preview a CELL STYLE write (LD-188). ZERO writes, and at most **one read per named tab**.

    **What is deliberately NOT read: a ``before``.** Cell style is readable only through the
    async whole-workbook export (:data:`STYLE_VERIFICATION_LEG`), so a style precondition would
    cost ~1.2 s per plan and a third scope. There is therefore no value/style precondition on
    this family — the compare-and-swap ``revision`` guard is what protects it, exactly as it is
    for the dimension family, and the plan says so instead of implying a diff it never made.

    The one read it does make pays for both jobs at once:

    * the **tab-identity** refusal — ``UNKNOWN_TAB`` when the range's ``{sheet_id}!`` prefix is
      not a tab of this spreadsheet (with a did-you-mean), else ``TAB_VANISHED`` (the LD-131
      split);
    * the **merge disclosure** (:func:`style_partial_merge_note`), off the ``merges`` that same
      geometry read returns — so the disclosure is unconditional rather than depending on the
      caller having passed ``merges=``.

    A prefix-less range (no ``{sheet_id}!``) names no tab to check, so it reads nothing and
    falls back to the ``merges`` the caller supplied, if any. Every fault knowable from the
    caller's own arguments — an out-of-range font size, a malformed colour, an empty style, an
    empty batch, a malformed A1 range — was already refused at **construction** and cost zero
    calls.
    """
    desc = request.descriptor()
    preview = request.style_preview()
    known_merges = list(merges or [])
    sheet_ids = desc.get("sheet_ids") or (
        [desc["sheet_id"]] if desc.get("sheet_id") else [])
    for sheet_id in sheet_ids:
        geometry = client.read_sheet_geometry(spreadsheet_token, sheet_id)
        if not isinstance(geometry, dict):
            return PlanEntry.refused(
                target=None,
                after=preview,
                refusal=_unreadable_tab_refusal(
                    client, spreadsheet_token, sheet_id=sheet_id,
                    detail=(
                        f"could not read the tab for {desc['semantic']}, so neither the tab's "
                        f"identity nor the merges this style would cover can be checked — "
                        f"refusing rather than styling a tab that may not exist"
                    ),
                ),
            )
        for merge in geometry.get("merges") or []:
            if merge not in known_merges:
                known_merges.append(merge)
    entry = PlanEntry.resolved_structural(
        structural=desc, after=preview, write_kind="style")
    note = combine_preview_notes(
        style_export_cost_note(desc),
        style_partial_merge_note(desc, known_merges),
        # LD-189: the leg is on, and it cannot see a border. Said in the same plan that turns
        # the leg on, so the caller never infers a coverage the differ does not have.
        style_border_not_verifiable_note(desc),
    )
    return entry if note is None else replace(entry, preview_note=note)


def _style_reply_revision(reply) -> Optional[int]:
    """The post-write ``revision`` a style reply carries, or ``None``.

    Probed (LD-188): ``PUT …/style`` reports it **nested**, at ``data.updates.revision``
    (``{"updates": {"revision": 3, "updatedCells": 1, …}}`` once the client has unwrapped
    ``data``) — so the flat :func:`_revision_of` finds nothing there — while
    ``styles_batch_update`` reports **none at all** (only per-range ``responses``). Both cases
    fall through to a ``metainfo`` read in the apply leg rather than guessing.
    """
    flat = _revision_of(reply)
    if flat is not None:
        return flat
    if isinstance(reply, dict):
        return _revision_of(reply.get("updates"))
    return None


def _apply_style_one(entry: PlanEntry, client, spreadsheet_token, expected_revision=None):
    """Execute ONE resolved CELL STYLE entry (LD-188). Returns ``(log_entry,
    next_expected_revision)``.

    The revision compare-and-swap already passed in :func:`_apply_one`. A style write has **no
    scalar precondition** (there is no cheap ``before`` — see :func:`_preview_style`) and **no
    geometry delta** to verify (it moves nothing), so this:

    * writes through the seam the request's own shape chose — ``put_style`` for one range,
      ``batch_update_styles`` for N ranges in ONE call (the reason the batch form exists: N
      single-range writes would spend N throttled calls and N compare-and-swaps);
    * takes the post-write ``revision`` from the reply's own envelope where it has one
      (:func:`_style_reply_revision`) and from ``metainfo`` where it does not — both cases
      probed, neither guessed;
    * records **which leg verifies this op and why that leg is not run here**
      (:data:`STYLE_VERIFICATION_NOTE`), the same honesty the dimension family's log carries.
    """
    desc = dict(entry.structural)
    if desc.get("batch"):
        reply = client.batch_update_styles(spreadsheet_token, desc["spans"])
    else:
        reply = client.put_style(spreadsheet_token, desc["ranges"][0], desc["style"])

    # Shape C: the style reply nests `revision` under `updates`, so the extractor differs.
    post_revision = _post_write_revision(
        reply, lambda: client.read_revision(spreadsheet_token),
        extract=_style_reply_revision)

    record = STYLE_VERIFICATION.stamp({
        **desc,
        "reply": reply if isinstance(reply, dict) else None,
        "preview": entry.after,
    })
    applied = ApplyLogEntry.applied_structural(
        structural=record, revision=post_revision, write_kind="style")
    return applied, post_revision
