"""larkdocio.sheets.ops._dimensions — the DIMENSION-PROPERTY family — row height / column width / hide-show.

Its own family and not a structural variant: a property write moves nothing, so it carries
its own verification leg (the xlsx export's dimension read). Named after
``requests/_dimensions.py``.

Split out of the flat 3,019-line ``sheets/ops.py`` by LD-532, **verbatim**. The
package's ``__init__`` holds the ``OPS`` registry, the dispatchers and the engine
loop, and re-exports every name defined here, so
``from larkdocio.sheets.ops import <name>`` is unchanged.
"""
from dataclasses import replace

from larkdocio.sheets.write_range import A1Cell
from larkdocio.sheets.plan import ApplyLogEntry, PlanEntry, Refusal

from ._shared import VerificationLeg, _post_write_revision, _unreadable_tab_refusal



# --------------------------------------------------------------------------- #
# Dimension PROPERTIES (LD-185) — the fourth verb's preview + apply legs.        #
#                                                                              #
# Its OWN family, and deliberately NOT the structural one: a property write     #
# moves nothing (no shift, no merge reshape, no value change), so the           #
# structural leg's geometry-delta verification has nothing to measure and the   #
# export style leg has no business being auto-triggered by a column width.      #
# --------------------------------------------------------------------------- #

#: The name of this family's **own** verification leg — the xlsx export's row/column
#: dimension read (:class:`~larkdocio.sheets.export_reader.ExportedDimension`).
#:
#: **Why this leg, decided on evidence (LD-185 AC4).** A dimension property is readable
#: **nowhere else**: probed live after eleven dimension writes, ``metainfo`` reports only
#: sheet-level ``frozen*`` / ``rowCount`` / ``columnCount`` and the v3 tab query only
#: ``grid_properties`` plus the **tab's** own ``hidden`` flag — neither carries a single row
#: height, column width, or row/column hidden state. So the cheap-read option (a) does not
#: exist, and the export is the only read that can see what a dimension write actually did —
#: the same position style is in.
DIMENSION_VERIFICATION = VerificationLeg(
    id="xlsx-export-dimension-leg",
    # Why that leg is NOT run inside `apply` (recorded in every dimension apply-log entry, so
    # the record states its own verification posture instead of leaving it to be assumed).
    note=(
        "verified by its own dimension leg — the xlsx export's <row ht/hidden> + <col "
        "width/hidden> read (export_reader.ExportedDimension), which is the ONLY read that can "
        "see a dimension property at all (metainfo and the v3 tab query carry none — probed). "
        "That leg is deliberately NOT run per apply: an export is an async whole-workbook task "
        "(~1.2s, up to ~30s), which is an absurd price for a column width, and this op is "
        "correspondingly kept out of STYLE_LEG_OP_KINDS / MERGE_LEG_OP_KINDS (the TAB / "
        "DATA_VALIDATION posture). The live_write ring runs the leg "
        "(tests/test_live_sheets_dimension_write_gate.py); a caller who wants it in-process "
        "runs SheetsExportReader.read_workbook(...) and reads row_dimensions / col_dimensions."
    ),
)

#: Authored on :data:`DIMENSION_VERIFICATION` above; these two names are references to it.
DIMENSION_VERIFICATION_LEG = DIMENSION_VERIFICATION.id
DIMENSION_VERIFICATION_NOTE = DIMENSION_VERIFICATION.note


def hidden_dimension_note(desc, geometry=None) -> dict:
    """The ``hidden-dimension-fidelity`` preview note for a **hide** — or ``None`` when the
    write hides nothing.

    **Hiding is a fidelity event, not a formatting detail.** A hidden row's data is still
    there and larkdocio's reader still emits it, so after this write the Markdown a consumer
    gets shows rows **no human looking at the spreadsheet can see** — the same silent-fidelity
    class the filter disclosure closed for filter-hidden rows, arriving this time through a
    write we perform ourselves. The plan therefore says so before the write, in the **shipped
    disclosure vocabulary** rather than a newly-coined one: the standard preview-note shape (a
    ``kind`` + a ``note``, composing through
    :func:`~larkdocio.sheets.plan.combine_preview_notes` so it can never displace another
    warning) carrying the filter disclosure's own wording
    (:data:`~larkdocio.sheets.table._FILTER_NOTE_HIDDEN`) — *"Hidden from anyone viewing this
    spreadsheet: … (numbered as the spreadsheet numbers them, where the first row is 1)"*.

    It fires **only** for ``visible=False``. A pure height/width change hides nothing, and a
    disclosure that rode every plan would be noise that teaches a consumer to skip notes.
    """
    if not desc.get("hides"):
        return None
    first, last = desc["start_index"], desc["end_index"]
    rows_axis = desc["major_dimension"] == "ROWS"
    axis = "row" if rows_axis else "column"
    labels = list(range(first, last + 1))
    if rows_axis:
        clause = (f"spreadsheet row {first}" if first == last
                  else f"spreadsheet rows {', '.join(str(r) for r in labels)}")
        addressed = {"hidden_rows": labels}
    else:
        names = [A1Cell(c, 1).a1().rstrip("1") for c in labels]
        clause = (f"spreadsheet column {names[0]}" if first == last
                  else f"spreadsheet columns {', '.join(names)}")
        addressed = {"hidden_columns": names}
    count = last - first + 1
    count_clause = f"1 {axis}" if count == 1 else f"{count} {axis}s"
    note = {
        "kind": "hidden-dimension-fidelity",
        "dimension": desc["major_dimension"],
        "span": [first, last],
        "count": count,
        "note": (
            f"HIDE — a fidelity event, not a formatting change. Hidden from anyone viewing "
            f"this spreadsheet: {clause} ({count_clause}, numbered as the spreadsheet numbers "
            f"them, where the first row is 1). The data is NOT deleted and larkdocio's reader "
            f"still emits it, so a Markdown read of this tab will still include what a human "
            f"can no longer see — the same silence the filter disclosure closes for "
            f"filter-hidden rows, arriving here through a write you are about to make. Show it "
            f"again with visible=True on the same band."
        ),
    }
    note.update(addressed)
    if isinstance(geometry, dict):
        key = "row_count" if rows_axis else "column_count"
        if isinstance(geometry.get(key), int):
            note[key] = geometry[key]
    return note


def _preview_dimension_property(request, client, spreadsheet_token, merges=None) -> PlanEntry:
    """Preview a DIMENSION-PROPERTY write (LD-185) — height / width / hide-show.

    **One read, three jobs.** The tab's geometry is read once and pays for all of:

    * the **tab-identity** refusal — ``UNKNOWN_TAB`` when the ``sheet_id`` is not a tab of this
      spreadsheet (with a did-you-mean), else ``TAB_VANISHED`` (the LD-131 split);
    * the **out-of-bounds band** refusal (AC6) — a band past the tab's declared row/column
      count cannot succeed (Lark answers ``90202 … endIndex must less than or equal to
      sheetMaxRowCount``), so it is refused **before any write**, naming the count and both
      repairs;
    * the **hide disclosure** (AC5) — the fidelity note, which reports the tab's own count
      alongside the hidden band.

    The band's own faults (reversed, no property, a non-positive ``fixed_size``, over the
    ≤5000 ceiling) never arrive here at all: they are refused at **construction**, so they cost
    zero API calls. Zero writes.
    """
    desc = request.descriptor()
    preview = request.property_preview()
    sheet_id = desc["sheet_id"]
    geometry = client.read_sheet_geometry(spreadsheet_token, sheet_id)
    if not isinstance(geometry, dict):
        return PlanEntry.refused(
            target=None,
            after=preview,
            refusal=_unreadable_tab_refusal(
                client, spreadsheet_token, sheet_id=sheet_id,
                detail=(
                    f"could not read the tab's geometry for {desc['semantic']}, so the band "
                    f"cannot be checked against the tab's row/column count — refusing rather "
                    f"than writing a property onto a band that may not exist"
                ),
            ),
        )
    key = "row_count" if desc["major_dimension"] == "ROWS" else "column_count"
    count = geometry.get(key)
    if isinstance(count, int) and count > 0 and desc["end_index"] > count:
        return PlanEntry.refused(
            target=None,
            after=preview,
            refusal=Refusal.out_of_bounds_dimension(
                dimension=desc["major_dimension"], first=desc["start_index"],
                last=desc["end_index"], count=count, sheet_id=sheet_id),
        )
    entry = PlanEntry.resolved_structural(
        structural=desc, after=preview, write_kind="dimension-property")
    note = hidden_dimension_note(desc, geometry)
    return entry if note is None else replace(entry, preview_note=note)


def _apply_dimension_property_one(entry: PlanEntry, client, spreadsheet_token,
                                  expected_revision=None):
    """Execute ONE resolved DIMENSION-PROPERTY entry (LD-185). Returns ``(log_entry,
    next_expected_revision)``.

    The revision compare-and-swap already passed in :func:`_apply_one`. A property write has
    **no scalar precondition** (there is no cell ``before`` value) and **no geometry delta** to
    verify (it moves nothing — the probed ``row_count`` is unchanged by it), so this:

    * writes via the dimension-property seam ``set_dimension_properties`` — the native
      **1-indexed inclusive** span coming from the plan's descriptor, never a caller's span;
    * reads the post-write ``revision`` back from ``metainfo`` (the reply carries none);
    * records **which leg verifies this op and why that leg is not run here** — see
      :data:`DIMENSION_VERIFICATION_NOTE`. Naming it in the log is the honest alternative to a
      silent "applied" that a reader might mistake for "verified".
    """
    desc = dict(entry.structural)
    reply = client.set_dimension_properties(
        spreadsheet_token, desc["sheet_id"], desc["major_dimension"],
        desc["start_index"], desc["end_index"], desc["properties"])

    # Shape A: the dimension replies omit `revision` — fall back to metainfo (spike Q4).
    post_revision = _post_write_revision(
        reply, lambda: client.read_revision(spreadsheet_token))

    record = DIMENSION_VERIFICATION.stamp({
        **desc,
        "reply": reply if isinstance(reply, dict) else None,
        "preview": entry.after,
    })
    applied = ApplyLogEntry.applied_structural(
        structural=record, revision=post_revision, write_kind="dimension-property")
    return applied, post_revision
