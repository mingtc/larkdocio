"""larkdocio.sheets.ops._structural — the STRUCTURAL family — insert / delete / append writes.

The row/column geometry family: its preview's destructive-delete snapshot (the payload a
refused delete is proven complete from), its out-of-bounds disclosure, and the apply leg's
geometry-delta verification. Named after ``requests/_structural.py``.

Split out of the flat 3,019-line ``sheets/ops.py`` by LD-532, **verbatim**. The
package's ``__init__`` holds the ``OPS`` registry, the dispatchers and the engine
loop, and re-exports every name defined here, so
``from larkdocio.sheets.ops import <name>`` is unchanged.
"""
from dataclasses import replace
from typing import Optional

from larkdocio.errors import LarkAPIError, LarkDocIOError
from larkdocio.sheets.write_range import A1Cell, WriteRange
from larkdocio.sheets.extent import trim_pad_along, used_extent_along
from larkdocio.sheets.merge_geometry import _normalize_merge
from larkdocio.sheets.plan import ApplyLogEntry, PlanEntry

from ._shared import _post_write_revision, _unreadable_tab_refusal



def _removed_dimension_range_a1(desc, geometry) -> Optional[str]:
    """The A1 range a row/col DELETE removes — the deleted rows across ALL columns (a row
    delete) / the deleted columns across ALL rows (a col delete), bounded by the pre-write
    geometry's extent. ``None`` when the bounding extent is unknown (can't address the loss).

    ``desc['start_index']``/``end_index`` are the delete's **1-indexed inclusive** span (the
    DeleteRows/DeleteCols native convention, D3); the range is built through the same S2
    A1 model every write uses, so the removed-payload address is byte-consistent with it."""
    sheet_id = desc["sheet_id"]
    first, last = desc["start_index"], desc["end_index"]  # 1-idx inclusive (delete convention)
    row_count = geometry.get("row_count")
    column_count = geometry.get("column_count")
    if desc["major_dimension"] == "ROWS":
        if not column_count:
            return None
        wr = WriteRange(A1Cell(1, first), A1Cell(column_count, last), sheet_id=sheet_id)
    else:
        if not row_count:
            return None
        wr = WriteRange(A1Cell(first, 1), A1Cell(last, row_count), sheet_id=sheet_id)
    return wr.a1()



def _intersecting_merges(desc, merges) -> list:
    """The merges (0-idx END-inclusive) intersecting a delete's removed span on the deleted
    axis — the subset a reconstruction must restore alongside the removed cell values. The
    other axis is irrelevant (a full row/col delete spans it entirely)."""
    if not merges:
        return []
    d_start, d_end = desc["start_index"] - 1, desc["end_index"] - 1  # 1-idx incl → 0-idx incl
    row_axis = desc["major_dimension"] == "ROWS"
    hits = []
    for m in merges:
        sr, er, sc, ec = _normalize_merge(m)
        lo, hi = (sr, er) if row_axis else (sc, ec)
        if not (hi < d_start or lo > d_end):  # overlap on the deleted axis
            hits.append(m)
    return hits



def _snapshot_removed_dimension(desc, client, spreadsheet_token) -> Optional[dict]:
    """Snapshot the DESTRUCTIVE-SAFE removed payload for a row/col DELETE (LD-123 / D5) at
    plan time — the removed cells' **values** + the **pre-write geometry** (+ the merges the
    span intersects), enough to RECONSTRUCT what the delete destroys (the docx W3
    delete-log parity, Decision c).

    Snapshotting at **plan time** pairs the removed payload with the compare-and-swap anchor:
    if the sheet advances before the write, ``STALE_SHEET`` refuses (no write) and the
    snapshot is never mismatched. Returns ``None`` when the loss cannot be snapshot (the
    geometry is unreadable — a vanished tab — or the removed-range read raises), so the
    caller REFUSES the delete rather than perform an un-reconstructable destruction.

    (The style/format leg of the removed payload is the write-gate fidelity differ's; dropdown rules on the
    removed range are the S6/LD-124 live leg — both out of scope here, which is the apply-side
    values+geometry safety.)"""
    sheet_id = desc["sheet_id"]
    geometry = client.read_sheet_geometry(spreadsheet_token, sheet_id)
    if not isinstance(geometry, dict):
        return None
    a1_range = _removed_dimension_range_a1(desc, geometry)
    if a1_range is None:
        return None
    try:
        values = client.read_values(spreadsheet_token, a1_range)
    except LarkAPIError as exc:
        # The failure is carried on the exception (LD-150 / F20): the caller classifies it —
        # a `90202` is a MALFORMED RANGE, not the staleness story — so it must not be
        # swallowed into a bare None the way it was before.
        raise _RemovedSnapshotFailed(a1_range, exc) from exc
    trimmed, trim = _trim_removed_values(values, desc, geometry)
    return {
        "a1_range": a1_range,
        "values": trimmed,
        "values_trim": trim,
        "geometry": geometry,
        "removed_merges": _intersecting_merges(desc, geometry.get("merges") or []),
    }


#: The axis a removed-dimension payload is **padded** along — the one the delete does NOT
#: consume. A ROW delete reads (deleted rows) × (the tab's declared ``column_count``), so the
#: pad is trailing empty COLUMNS; a COLUMN delete reads (declared ``row_count``) × (deleted
#: columns), so the pad is trailing empty ROWS (LD-150 / dogfood **F12**).
_PAD_AXIS = {"ROWS": "COLUMNS", "COLUMNS": "ROWS"}


def _trim_removed_values(values, desc, geometry):
    """``(trimmed_values, trim_disclosure)`` for a destructive delete's removed payload
    (LD-150 / dogfood **F12**).

    The values API never trims server-side: it answers the **full declared grid** with the pad
    as ``null``, so the seat session's 2-row delete on a 20-column tab previewed 2×20 with 18
    ``null``s per row — "on a 100-column tab the preview becomes unreadable and expensive to
    log". The payload is now narrowed to the **used** extent along the padded axis
    (:func:`~larkdocio.sheets.extent.trim_pad_along`).

    Deliberately **not** the whole :func:`~larkdocio.sheets.extent.trim_trailing_nulls`: that
    trims BOTH axes, which would drop a doomed row that happens to be empty — and a delete's
    removed payload must state the full extent of the loss, not only its interesting part.
    Interior and trailing blanks **inside** the used extent survive either way.

    The trim is **disclosed** (``values_trim``), because a silently narrowed payload would be a
    new silence in the very surface this issue is closing.
    """
    axis = _PAD_AXIS[desc["major_dimension"]]
    declared = geometry.get("column_count" if axis == "COLUMNS" else "row_count")
    trimmed = trim_pad_along(values, axis)
    used = used_extent_along(values, axis)
    return trimmed, {
        "axis": axis,
        "declared": declared,
        "used": used,
        "note": (
            f"values are TRIMMED along {axis} to the used extent ({used} of the tab's declared "
            f"{declared}): the values API answers the full declared grid with the pad as null, "
            f"which made this payload unreadable on a wide tab. Every "
            f"{desc['major_dimension'].lower()[:-1]} the delete removes is still listed (that "
            f"axis is never trimmed), and blanks INSIDE the used extent are preserved — only "
            f"the pad is gone."
        ),
    }


class _RemovedSnapshotFailed(Exception):
    """Internal: the destructive-delete removed-payload read failed (LD-150 / F20).

    A private carrier so :func:`_preview_structural` can classify the **underlying** Lark
    error (``90202`` ⇒ ``malformed-range``) instead of only learning "it did not work". Never
    escapes this module — :func:`_preview_structural` converts it to a typed refusal, exactly
    as the ``None`` return did before.
    """

    def __init__(self, a1_range, error):
        super().__init__(f"could not read removed payload for {a1_range}: {error}")
        self.a1_range = a1_range
        self.error = error



def _preview_structural(request, client, spreadsheet_token, merges=None) -> PlanEntry:
    """Preview a STRUCTURAL dimension write (LD-121/123). Insert/append preview the shift
    deterministically (no read — the shift follows from the semantic span). A **delete**
    additionally snapshots the removed payload at plan time (LD-123 / D5) so the preview
    ENUMERATES what is removed (delete-log parity) and the apply-log can reconstruct it; a
    delete whose loss cannot be snapshot REFUSES — the destructive-safe invariant that
    nothing is destroyed that cannot be recorded. The refusal names WHY: ``UNKNOWN_TAB``
    when the ``sheet_id`` is not a tab of this spreadsheet (LD-131), else ``TAB_VANISHED``.
    Zero writes."""
    desc = request.descriptor()
    shift = request.shift_preview()
    if desc["op"] == "delete":
        failed_range = failure = None
        try:
            removed = _snapshot_removed_dimension(desc, client, spreadsheet_token)
        except _RemovedSnapshotFailed as exc:
            removed, failed_range, failure = None, exc.a1_range, exc.error
        if removed is None:
            return PlanEntry.refused(
                target=None,
                after=shift,
                refusal=_unreadable_tab_refusal(
                    client, spreadsheet_token,
                    sheet_id=desc.get("sheet_id"),
                    detail=(
                        f"could not snapshot the removed payload for {desc['semantic']} "
                        f"(geometry/values unreadable) — refusing a destructive delete that "
                        f"cannot be recorded/reconstructed"
                    ),
                    a1_range=failed_range, error=failure,
                ),
            )
        shift = {**shift, "removed": removed}
        entry = PlanEntry.resolved_structural(structural=desc, after=shift)
        # LD-150 / dogfood F23 — the span vs the geometry the snapshot ALREADY read. Zero
        # extra calls: the number that catches this was in hand all along.
        note = out_of_bounds_dimension_note(desc, removed.get("geometry"))
        return entry if note is None else replace(entry, preview_note=note)
    return PlanEntry.resolved_structural(structural=desc, after=shift)


def out_of_bounds_dimension_note(desc, geometry) -> Optional[dict]:
    """The ``out-of-bounds-dimension`` preview note for a delete whose span runs past the tab's
    row/column count — or ``None`` when the span is in bounds (LD-150 / dogfood **F23**).

    ``DeleteRows(first=9999, last=10000)`` on a 200-row tab **resolved happily**, in a preview
    that reported the row count in the same breath. Nothing is refused (Lark will simply delete
    fewer rows, and the apply-log's count-mismatch check catches it *after* the write) — but the
    plan now says so **before**, which is the whole point of a plan.

    Built from ``geometry`` the delete's removed-payload snapshot already read, so the note
    costs **no extra API call** (AC7).
    """
    if not isinstance(geometry, dict):
        return None
    major = desc["major_dimension"]
    count = geometry.get("row_count" if major == "ROWS" else "column_count")
    if not isinstance(count, int) or count <= 0:
        return None
    first, last = desc["start_index"], desc["end_index"]   # 1-idx inclusive (delete convention)
    if last <= count:
        return None
    axis = "row" if major == "ROWS" else "column"
    overshoot = last - max(count, first - 1)
    wholly_past = first > count
    return {
        "kind": "out-of-bounds-dimension",
        "dimension": major,
        "span": [first, last],
        "count": count,
        ("row_count" if major == "ROWS" else "column_count"): count,
        "overshoot": overshoot,
        "wholly_out_of_bounds": wholly_past,
        "note": (
            f"OUT OF BOUNDS: this delete names {axis}s {first}..{last} (inclusive) but the tab "
            f"has only {count} {axis}(s), so "
            + (
                f"NO {axis} in that span exists and the delete will remove NOTHING"
                if wholly_past else
                f"{overshoot} of the {last - first + 1} named {axis}(s) do not exist and the "
                f"delete will remove fewer than you asked for"
            )
            + f". Nothing is refused — Lark accepts the call — but the reply's "
              f"delCount will not match the requested span, which the apply-log records as "
              f"count_mismatch AFTER the write. Re-read the geometry "
              f"(read_sheet_geometry(...)['{'row_count' if major == 'ROWS' else 'column_count'}']"
              f" == {count}) and re-plan the span if that is not what you meant."
        ),
    }



def _geometry_delta(before, after, major_dimension) -> Optional[int]:
    """The row/column-count delta between two geometry re-reads on the shifted axis
    (``ROWS`` → ``row_count``, else ``column_count``). ``None`` when either read (or the
    axis count) is missing — so the shift verification degrades honestly rather than
    fabricating a delta."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None
    key = "row_count" if major_dimension == "ROWS" else "column_count"
    b, a = before.get(key), after.get(key)
    if b is None or a is None:
        return None
    return a - b



def _apply_structural_one(entry: PlanEntry, client, spreadsheet_token, expected_revision=None):
    """Execute ONE resolved STRUCTURAL entry (LD-121). Returns ``(log_entry,
    next_expected_revision)``.

    The revision compare-and-swap already passed in :func:`_apply_one` (so this only runs
    on a fresh sheet). A structural write has **no scalar precondition** (there is no cell
    ``before`` value); instead it:

    * reads geometry **before** the write (the baseline for the shift verification);
    * writes via the dimension seam for its op — ``insert_dimension_range`` (0-idx
      half-open) / ``delete_dimension_range`` (1-idx inclusive) / ``append_dimension`` /
      ``append_values(INSERT_ROWS)`` — the native span/length coming from the plan's
      descriptor (built by the request object, never a raw caller span);
    * **trusts the reply's ``addCount``/``delCount``** (``None`` for insert, whose reply
      omits a count — the requested span width is authoritative there);
    * **mandatorily re-reads geometry** after the write and records the observed row/column
      delta, surfacing a **count mismatch** (reply count ≠ requested span) and whether the
      observed shift matched the preview — never assuming parity (D2/D3).
    """
    desc = dict(entry.structural)
    op = desc["op"]
    sheet_id = desc["sheet_id"]
    major = desc["major_dimension"]
    expected_count = desc["expected_count"]

    # geometry BEFORE (baseline) — read only after the revision check passed, so a
    # stale/ skipped write reads no geometry.
    geometry_before = client.read_sheet_geometry(spreadsheet_token, sheet_id)

    if op == "insert":
        reply = client.insert_dimension_range(
            spreadsheet_token, sheet_id, major, desc["start_index"], desc["end_index"])
        reply_count = None  # the insert reply omits a count (span width is authoritative)
    elif op == "delete":
        reply = client.delete_dimension_range(
            spreadsheet_token, sheet_id, major, desc["start_index"], desc["end_index"])
        reply_count = reply.get("delCount") if isinstance(reply, dict) else None
    elif op == "append-dim":
        reply = client.append_dimension(spreadsheet_token, sheet_id, major, desc["length"])
        reply_count = reply.get("addCount") if isinstance(reply, dict) else None
    elif op == "append-values":
        reply = client.append_values(
            spreadsheet_token, desc["a1_range"], desc["values"],
            insert_data_option="INSERT_ROWS")
        updates = reply.get("updates") if isinstance(reply, dict) else None
        reply_count = updates.get("updatedRows") if isinstance(updates, dict) else None
    else:  # pragma: no cover — the request objects are the only source of `op`
        raise LarkDocIOError(f"unknown structural op {op!r}")

    # MANDATORY geometry re-read AFTER the write (D2/D3) — never assume parity.
    geometry_after = client.read_sheet_geometry(spreadsheet_token, sheet_id)
    observed_delta = _geometry_delta(geometry_before, geometry_after, major)
    shift_delta = entry.after.get("shift_delta") if isinstance(entry.after, dict) else None

    count_mismatch = reply_count is not None and reply_count != expected_count
    count_mismatch_detail = (
        f"reply count {reply_count} != requested span {expected_count}"
        if count_mismatch else None
    )
    shift_verified = observed_delta is not None and observed_delta == shift_delta

    # Shape A: the dimension replies omit `revision` — fall back to metainfo (spike Q4).
    post_revision = _post_write_revision(
        reply, lambda: client.read_revision(spreadsheet_token))

    structural_log = {
        **desc,
        "reply_count": reply_count,
        "observed_delta": observed_delta,
        "shift_delta": shift_delta,
        "shift_verified": shift_verified,
        "count_mismatch": count_mismatch,
        "count_mismatch_detail": count_mismatch_detail,
        "geometry_before": geometry_before,
        "geometry_after": geometry_after,
    }
    # LD-123 / D5: a DELETE carries its plan-time removed payload (values + pre-write
    # geometry + intersecting merges) into the apply-log so the log ALONE can reconstruct
    # what was destroyed (docx W3 delete-log parity). Insert/append remove nothing.
    if isinstance(entry.after, dict) and entry.after.get("removed") is not None:
        structural_log["removed"] = entry.after["removed"]
    applied = ApplyLogEntry.applied_structural(
        structural=structural_log, revision=post_revision, write_kind="structure")
    return applied, post_revision
