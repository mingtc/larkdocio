"""larkdocio.sheets.ops._freeze — the FREEZE-PANES family — a view-state write.

Shares the tab family's endpoint and request element, not its verification: a freeze is read
back off the ``metainfo`` frozen counts. Named after ``requests/_freeze.py``.

Split out of the flat 3,019-line ``sheets/ops.py`` by LD-532, **verbatim**. The
package's ``__init__`` holds the ``OPS`` registry, the dispatchers and the engine
loop, and re-exports every name defined here, so
``from larkdocio.sheets.ops import <name>`` is unchanged.
"""
from dataclasses import replace
from typing import Optional

from larkdocio.errors import LarkAPIError
from larkdocio.sheets.models import FrozenPanes
from larkdocio.sheets.plan import ApplyLogEntry, PlanEntry, Refusal

from ._shared import VerificationLeg, _post_write_revision, _unreadable_tab_refusal


# --------------------------------------------------------------------------- #
# FREEZE PANES (LD-186) — the preview + apply legs of a view-state write.        #
#                                                                              #
# Zero new HTTP: the `updateSheet` element rides the already-shipped            #
# `sheets_batch_update` the tab family calls. Its OWN family all the same,      #
# because what verifies it is different: not a geometry delta (a freeze moves    #
# nothing), not the export style leg (a freeze is not cell style), not the v3    #
# merges leg (a freeze is not merge geometry) — but the `metainfo` frozen        #
# counts, which LD-186 also shipped precisely because they did not exist.       #
# --------------------------------------------------------------------------- #

#: This family's **own** verification leg — the ``metainfo`` frozen read
#: (:meth:`~larkdocio.sheets.write_client.SheetsWriteClient.read_frozen_panes`).
#:
#: **Why this leg.** A freeze is readable there and only there among the cheap reads: ``metainfo``
#: carries sheet-level ``frozenRowCount`` / ``frozenColCount`` and the v3 tab query carries the
#: same two under ``grid_properties`` (both probed) — while the values read cannot see a freeze
#: at all, and no export is needed. Unlike :data:`DIMENSION_VERIFICATION_LEG`, this leg is a
#: single cheap GET, so it **does** run inside ``apply``: there is no reason to record "applied"
#: when "applied and read back" costs one un-throttled read.
FREEZE_VERIFICATION = VerificationLeg(
    id="metainfo-frozen-leg",
    # Recorded in every freeze apply-log entry, so the record states its own posture.
    note=(
        "verified by its own frozen leg — the metainfo sheet-level frozenRowCount / "
        "frozenColCount read (SheetsWriteClient.read_frozen_panes), which is the read this "
        "issue had to ship before a freeze could be verified at all (the counts were surfaced "
        "NOWHERE in the library beforehand). That leg IS run inside apply — it is one cheap "
        "un-throttled GET, unlike the dimension leg's async whole-workbook export — so a "
        "freeze entry carries the frozen counts observed AFTER the write, not merely the fact "
        "that the call returned. The op is correspondingly kept out of STYLE_LEG_OP_KINDS / "
        "MERGE_LEG_OP_KINDS (the TAB / DATA_VALIDATION posture): a freeze is view state, not "
        "cell content and not merge geometry."
    ),
)

#: Authored on :data:`FREEZE_VERIFICATION` above; these two names are references to it.
FREEZE_VERIFICATION_LEG = FREEZE_VERIFICATION.id
FREEZE_VERIFICATION_NOTE = FREEZE_VERIFICATION.note


def frozen_replacement_note(desc, current) -> Optional[dict]:
    """The ``freeze-replaces-freeze`` preview note — or ``None`` when the tab freezes nothing
    today, so there is nothing being replaced.

    **A freeze silently moves somebody else's frozen band.** Unlike a value write, there is no
    precondition to compare and no cell to diff: a freeze just wins. So when the tab already
    freezes something, the plan names **both** the current counts and the target ones before the
    write, which is the whole point of having a plan. It fires for an **unfreeze** too — that is
    the most surprising case of all, because it discards a frozen band and looks like a cleanup
    — and for a freeze whose target **equals** the current state, since Lark bumps ``revision``
    for an identical freeze anyway (probed), so "nothing changes" is still a write.

    Deliberately a **note**, not a refusal, and worded in LD-150's shipped disclosure vocabulary
    rather than a newly-coined one: the "Nothing is refused … re-read … and re-plan … if that is
    not what you meant" register of ``out_of_bounds_dimension_note`` /
    :func:`no_merge_at_range_note`. Built from the frozen read the preview already makes, so it
    costs **no extra API call**.
    """
    if not isinstance(current, dict):
        return None
    cur_rows, cur_cols = current.get("frozen_rows"), current.get("frozen_cols")
    if not isinstance(cur_rows, int) or not isinstance(cur_cols, int):
        return None
    if not (cur_rows or cur_cols):
        return None                      # nothing frozen — nothing being replaced
    asked_rows, asked_cols = desc.get("rows"), desc.get("cols")
    target_rows = cur_rows if asked_rows is None else asked_rows
    target_cols = cur_cols if asked_cols is None else asked_cols
    preserved = [name for name, asked in (("frozen_rows", asked_rows),
                                          ("frozen_cols", asked_cols)) if asked is None]
    current_text = FrozenPanes(rows=cur_rows, cols=cur_cols).describe()
    target_text = FrozenPanes(rows=target_rows, cols=target_cols).describe()
    unchanged = (target_rows, target_cols) == (cur_rows, cur_cols)
    if unchanged:
        outcome = (
            f"This freeze asks for exactly what is already there ({target_text}), so nothing "
            f"about the view changes — but it is still a write: Lark bumps the spreadsheet "
            f"revision for an identical freeze (probed), so it will invalidate any other plan "
            f"held against this snapshot."
        )
    else:
        outcome = (
            f"After this write: {target_text}. The band that is there now is REPLACED, not "
            f"merged with — a freeze has no precondition to compare and no cell to diff, so it "
            f"simply wins."
        )
    if preserved:
        axes = " and ".join("rows" if p == "frozen_rows" else "columns" for p in preserved)
        patch_clause = (
            f" The {axes} axis is not named by this request and is left exactly as it is "
            f"(`properties` is a PATCH, probed — an axis you do not name is not reset)."
        )
    else:
        patch_clause = " Both axes are named, so both are set by this request."
    return {
        "kind": "freeze-replaces-freeze",
        "sheet_id": desc.get("sheet_id"),
        "current": {"frozen_rows": cur_rows, "frozen_cols": cur_cols},
        "target": {"frozen_rows": target_rows, "frozen_cols": target_cols},
        "preserved_axes": preserved,
        "unchanged": unchanged,
        "note": (
            f"FREEZE REPLACES FREEZE: tab {desc.get('sheet_id')!r} already has {current_text}. "
            f"{outcome}{patch_clause} Nothing is refused — Lark accepts the call — but you are "
            f"being told before the write rather than discovering it after, so nobody is "
            f"surprised to find someone else's frozen band moved. Re-read the frozen counts "
            f"(read_frozen_panes(...)) and re-plan if that is not what you meant."
        ),
    }


def _preview_freeze(request, client, spreadsheet_token, merges=None) -> PlanEntry:
    """Preview a FREEZE-PANES write (LD-186). ZERO writes, and **one** read that pays for four
    jobs:

    * the **tab-identity** refusal — ``UNKNOWN_TAB`` when the ``sheet_id`` is not a tab of this
      spreadsheet (with a did-you-mean), else ``TAB_VANISHED`` (the LD-131 split);
    * the plan-time **out-of-range** refusal (AC4) — a count past the tab's own row/column count
      cannot succeed (``90226``), so it is refused **before any write**, naming the count, the
      real boundary and both repairs;
    * the **replacement disclosure** (AC5) — :func:`frozen_replacement_note`;
    * nothing else: ``metainfo`` answers all of it in a single un-throttled GET.

    The faults knowable from the caller's own arguments (no axis, a negative count, a bool, a
    fraction) never arrive here — they are refused at **construction**
    (:class:`~larkdocio.sheets.requests.FreezeError`) and cost zero calls.
    """
    desc = request.descriptor()
    preview = request.freeze_preview()
    sheet_id = desc["sheet_id"]
    try:
        current = client.read_frozen_panes(spreadsheet_token, sheet_id)
    except LarkAPIError as e:
        return PlanEntry.refused(
            target=None,
            after=preview,
            refusal=_unreadable_tab_refusal(
                client, spreadsheet_token, sheet_id=sheet_id,
                detail=(
                    f"could not read the frozen counts for {desc['semantic']}, so neither the "
                    f"count bounds nor an existing freeze can be checked — refusing rather than "
                    f"freezing blind: {e}"
                ),
                error=e,
            ),
        )
    if not isinstance(current, dict):
        return PlanEntry.refused(
            target=None,
            after=preview,
            refusal=_unreadable_tab_refusal(
                client, spreadsheet_token, sheet_id=sheet_id,
                detail=(
                    f"the frozen (metainfo) read succeeded but names no tab {sheet_id!r} for "
                    f"{desc['semantic']}"
                ),
            ),
        )
    for axis, asked, key in (("row", desc.get("rows"), "row_count"),
                             ("column", desc.get("cols"), "column_count")):
        count = current.get(key)
        if asked is None or not isinstance(count, int) or count <= 0:
            continue
        if asked > count:
            return PlanEntry.refused(
                target=None,
                after=preview,
                refusal=Refusal.frozen_count_out_of_range(
                    axis=axis, asked=asked, count=count, sheet_id=sheet_id),
            )
    entry = PlanEntry.resolved_structural(
        structural={**desc, "frozen_before": {"frozen_rows": current.get("frozen_rows"),
                                              "frozen_cols": current.get("frozen_cols")}},
        after=preview, write_kind="freeze-panes")
    note = frozen_replacement_note(desc, current)
    return entry if note is None else replace(entry, preview_note=note)


def _apply_freeze_one(entry: PlanEntry, client, spreadsheet_token, expected_revision=None):
    """Execute ONE resolved FREEZE-PANES entry (LD-186). Returns ``(log_entry,
    next_expected_revision)``.

    The revision compare-and-swap already passed in :func:`_apply_one`. A freeze has no scalar
    precondition (there is no cell ``before`` value) and no geometry delta to verify (it moves
    nothing — the probed ``rowCount``/``columnCount`` are unchanged by it), so this:

    * writes the request element the request OWNS (``desc["request_element"]`` — an
      ``updateSheet``) through the **already-shipped** ``sheets_batch_update`` seam, exactly as
      the tab family does. No new endpoint, no second body assembler;
    * runs the verification leg (:data:`FREEZE_VERIFICATION_LEG`) **here**, because it is one
      cheap read: the frozen counts are read back and recorded as ``observed``, so the log says
      what the tab now freezes rather than only that the call returned;
    * takes the post-write ``revision`` from that same read (the ``updateSheet`` reply carries
      none — probed), so verification and the compare-and-swap anchor cost ONE call between them.
    """
    desc = dict(entry.structural)
    reply = client.batch_update_sheets(spreadsheet_token, [desc["request_element"]])
    replies = (reply or {}).get("replies") or []
    first = replies[0] if replies else {}

    state = client.read_frozen_panes(spreadsheet_token)
    observed_tab = ((state or {}).get("sheets") or {}).get(desc["sheet_id"])
    # Shape B: the fallback is the frozen read ALREADY IN HAND above — never a second call.
    post_revision = _post_write_revision(reply, lambda: (state or {}).get("revision"))

    record = FREEZE_VERIFICATION.stamp({
        **desc,
        "reply": first,
        "preview": entry.after,
        "observed": (None if not isinstance(observed_tab, dict) else
                     {"frozen_rows": observed_tab.get("frozen_rows"),
                      "frozen_cols": observed_tab.get("frozen_cols")}),
    })
    applied = ApplyLogEntry.applied_structural(
        structural=record, revision=post_revision, write_kind="freeze-panes")
    return applied, post_revision
