"""larkdocio.sheets.ops._merge — the MERGE family — merge / unmerge geometry writes.

``MergeCells`` / ``UnmergeCells``: the ``merge`` descriptor's legs and the merge-cover notes
its preview discloses. Named after ``requests/_merge.py``.

Split out of the flat 3,019-line ``sheets/ops.py`` by LD-532, **verbatim**. The
package's ``__init__`` holds the ``OPS`` registry, the dispatchers and the engine
loop, and re-exports every name defined here, so
``from larkdocio.sheets.ops import <name>`` is unchanged.
"""
from dataclasses import replace

from larkdocio.errors import LarkAPIError
from larkdocio.sheets.write_range import WriteRange
from larkdocio.sheets.merge_geometry import _normalize_merge
from larkdocio.sheets.plan import ApplyLogEntry, PlanEntry

from ._shared import _post_write_revision, _unreadable_tab_refusal



def _merge_hit(target: WriteRange, merges):
    """The first merge region the ``target`` range **intersects at all**, or ``None``
    (LD-150 / dogfood **F22**).

    The sibling of :func:`_covered_cell_hit`, which asks the narrower question "does the target
    touch a merge's *covered* cell?" (a write concern). Dissolving is the whole-region concern:
    Lark unmerges the merge a range **touches**, anchor included, so an unmerge that intersects
    nothing dissolves nothing. Same 0-idx END-inclusive convention, same normalizer.
    """
    for m in merges or []:
        sr, er, sc, ec = _normalize_merge(m)
        if (max(target.start.row, sr + 1) <= min(target.end.row, er + 1)
                and max(target.start.col, sc + 1) <= min(target.end.col, ec + 1)):
            return m
    return None


def no_merge_at_range_note(a1_range, merges) -> dict:
    """The ``no-merge-at-range`` preview note for an unmerge that will dissolve nothing
    (LD-150 / dogfood **F22**).

    An unmerge preview is deterministic and read-free by design, which made a **no-op
    indistinguishable from a real dissolve** — while its ``MergeCells`` sibling pays for a read
    and previews the loss precisely. This closes the asymmetry at **zero** extra cost: the merge
    set is the one the caller already handed :func:`dry_run` (``merges=``, the LD-122 / D4
    opt-in), so no call is added.

    Not a refusal: an unmerge of an unmerged range is a harmless no-op, not an error — and
    refusing it would break the idempotent restore pattern the live gates rely on. The plan just
    stops implying something will happen.
    """
    return {
        "kind": "no-merge-at-range",
        "a1_range": a1_range,
        "merges_checked": len(list(merges or ())),
        "note": (
            f"NO MERGE at {a1_range}: none of the {len(list(merges or ()))} merge region(s) this "
            f"plan was given intersects that range, so this unmerge will dissolve NOTHING — it "
            f"is a no-op, not an error, and it is NOT refused (an idempotent unmerge is a "
            f"legitimate restore step). Nothing else on the sheet changes, and the write still "
            f"advances the revision. If you expected a merge here, re-read the tab's merges "
            f"(read_sheet_geometry(...)['merges'] / query_tabs) — merge geometry lives ONLY in "
            f"the v3 tab query; a values read cannot see it."
        ),
    }


def _preview_merge(request, client, spreadsheet_token, merges=None) -> PlanEntry:
    """Preview a merge/unmerge write (LD-122). A **merge** reads the target range so the
    anchor-value loss is previewed EXPLICITLY (:meth:`MergeCells.loss_preview` — delete-log
    parity); an unreadable range refuses ``UNKNOWN_TAB`` (the tab listing proves the
    ``sheet_id`` never existed — LD-131) or ``TAB_VANISHED``. An **unmerge** previews the
    dissolved region deterministically (no read). Zero writes.

    **LD-150 / F22:** when the plan was **given** the tab's merge set (``merges=``, the D4
    opt-in — ``[]`` means "checked, there are none", which is why the test is ``is not None``
    and not truthiness), an unmerge whose range intersects no merge carries the
    ``no-merge-at-range`` note. A merge-unaware plan is byte-unchanged: finding out would cost
    a read, and AC7 buys this disclosure for zero calls."""
    desc = request.descriptor()
    if desc["op"] == "merge":
        try:
            before = client.read_values(spreadsheet_token, request.a1_range)
        except LarkAPIError as e:
            return PlanEntry.refused(
                target=request.target,
                after=None,
                refusal=_unreadable_tab_refusal(
                    client, spreadsheet_token,
                    sheet_id=desc.get("sheet_id"),
                    detail=f"could not read merge target {request.a1_range}: {e}",
                    a1_range=request.a1_range, error=e,
                ),
            )
        return PlanEntry.resolved_structural(
            structural=desc, after=request.loss_preview(before), write_kind="merge")
    entry = PlanEntry.resolved_structural(
        structural=desc, after=request.dissolve_preview(), write_kind="merge")
    if merges is not None and _merge_hit(request.target, merges) is None:
        return replace(entry, preview_note=no_merge_at_range_note(request.a1_range, merges))
    return entry



def _apply_merge_one(entry: PlanEntry, client, spreadsheet_token, expected_revision=None):
    """Execute ONE resolved MERGE / UNMERGE entry (LD-122). Returns ``(log_entry,
    next_expected_revision)``.

    The revision compare-and-swap already passed in :func:`_apply_one`. A merge write has
    **no scalar precondition** (it is geometry, not a cell value); instead it:

    * reads the sheet's ``merges`` **before** the write (the merge-leg baseline);
    * writes via the merge seam — ``merge_cells`` (anchor-value semantics — the covered
      values, previewed at plan time, are discarded) or ``unmerge_cells``;
    * **re-reads the ``merges`` array** after the write (the LD-116 merge leg) and records
      the ``merges_before`` / ``merges_after`` arrays + the added/removed delta, so a unit
      test (or a live gate) can verify the geometry with the merge leg. The plan's loss
      preview (merge) rides along in the log for delete-log parity.
    """
    desc = dict(entry.structural)
    op = desc["op"]
    sheet_id = desc["sheet_id"]
    a1 = desc["a1_range"]

    geo_before = client.read_sheet_geometry(spreadsheet_token, sheet_id)
    merges_before = (geo_before or {}).get("merges") or []

    if op == "merge":
        reply = client.merge_cells(spreadsheet_token, a1, desc["merge_type"])
    else:  # unmerge
        reply = client.unmerge_cells(spreadsheet_token, a1)

    geo_after = client.read_sheet_geometry(spreadsheet_token, sheet_id)
    merges_after = (geo_after or {}).get("merges") or []
    added = [m for m in merges_after if m not in merges_before]
    removed = [m for m in merges_before if m not in merges_after]

    # Shape A: the merge/unmerge reply carries {"spreadsheetToken": …} (no revision) — fall
    # back to metainfo (spike Q4).
    post_revision = _post_write_revision(
        reply, lambda: client.read_revision(spreadsheet_token))

    merge_log = {
        **desc,
        "merges_before": merges_before,
        "merges_after": merges_after,
        "merges_added": added,
        "merges_removed": removed,
        "preview": entry.after,   # the loss preview (merge) / dissolve note (unmerge)
    }
    applied = ApplyLogEntry.applied_structural(
        structural=merge_log, revision=post_revision, write_kind="merge")
    return applied, post_revision
