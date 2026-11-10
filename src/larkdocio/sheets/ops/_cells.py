"""larkdocio.sheets.ops._cells — the VALUE family — plain and rich cell writes.

``ValueWriteRequest`` / ``RichCellWriteRequest``: the ``value`` descriptor's preview and apply
legs plus the structured-cell detection they refuse malformed rich input with. Named after
``requests/_cells.py``, which defines both request classes.

Split out of the flat 3,019-line ``sheets/ops.py`` by LD-532, **verbatim**. The
package's ``__init__`` holds the ``OPS`` registry, the dispatchers and the engine
loop, and re-exports every name defined here, so
``from larkdocio.sheets.ops import <name>`` is unchanged.
"""
from dataclasses import replace

from larkdocio.errors import LarkAPIError, LarkDocIOError
from larkdocio.sheets.write_range import A1Cell, WriteRange
from larkdocio.sheets.formula import (
    EXPRESSION_RENDER_OPTION,
    FormulaRenderOptionUnsupported,
    formula_expression,
    live_formula_cells,
    overwrites_live_formula_note,
    read_render,
)
from larkdocio.sheets.plan import ApplyLogEntry, PlanEntry, Refusal

from ._shared import _covered_cell_hit, _post_write_revision, _unreadable_tab_refusal


# --------------------------------------------------------------------------- #
# Structured-cell detection — a "rich" cell is a segment array (list) or a       #
# mention / multi-select object (dict); a plain value is a scalar (str / int /  #
# float / bool / None).                                                         #
# --------------------------------------------------------------------------- #

def _has_structured_cell(matrix) -> bool:
    """True iff any cell in ``matrix`` is a **structured** (rich) cell — a segment
    array or a mention / multi-select object. Row lists are the matrix's own shape,
    never a "cell"; only a value *inside* a row that is a ``list``/``dict`` is rich."""
    for row in matrix or []:
        cells = row if isinstance(row, list) else [row]
        for cell in cells:
            if isinstance(cell, (list, dict)):
                return True
    return False


def _has_formula_cell(matrix) -> bool:
    """True iff any cell in ``matrix`` is the **formula object form** (LD-149).

    Used only to make the plain-value path's structured-cell refusal name the RIGHT request
    class: before LD-149 a hand-assembled ``{"type":"formula",…}`` in a
    :class:`ValueWriteRequest` was told to "use a RichCellWriteRequest", which cannot write a
    formula. The refusal reason is unchanged; only the advice is corrected."""
    for row in matrix or []:
        cells = row if isinstance(row, list) else [row]
        for cell in cells:
            if formula_expression(cell) is not None:
                return True
    return False


def _structured_cell_refusal(matrix, detail: str, *, formula_detail: str) -> Refusal:
    """The ``RICH_CELL_TARGET`` refusal for a structured **proposed** cell, with
    **formula-aware advice** (LD-149). A non-formula structured cell keeps its pre-LD-149
    detail byte-for-byte.

    Only the **plan-time proposed-values** site needs this: a *current* target that holds a
    formula is invisible to the precondition read (which is ``UnformattedValue``, so a formula
    answers its computed scalar), so there is no apply-time formula case to advise on."""
    return Refusal.rich_cell_target(
        formula_detail if _has_formula_cell(matrix) else detail)


def _preview_value(request, client, spreadsheet_token, merges=None) -> PlanEntry:
    """Preview a plain / rich value write (LD-111 / LD-119) — reads the target's current
    values (the *before*) and pairs them with the proposed values, ZERO writes.

    The structured-cell refusals apply to a **plain**
    :class:`~larkdocio.sheets.requests.ValueWriteRequest` only; a
    :class:`~larkdocio.sheets.requests.RichCellWriteRequest` (``is_rich``) carries an encoded
    rich cell and LIFTS them — the structured proposed value IS the write, a structured current
    target IS the expected form, still guarded by the precondition compare-and-swap at apply.
    ``merges`` (opt-in, LD-122 / D4): a value/rich write whose target intersects a merge's
    **covered** (non-anchor) cell refuses ``MERGED_CELL_TARGET``; default ``None`` ⇒
    merge-unaware, byte-identical to LD-111."""
    target_a1 = request.target.a1()

    # A value/rich write into a merge-COVERED cell refuses (D4) — only when the plan was
    # given the tab's merges (opt-in); a covered cell holds no value of its own, so the
    # write would be dropped or corrupt the merge.
    if merges:
        covered = _covered_cell_hit(request.target, merges)
        if covered is not None:
            return PlanEntry.refused(
                target=request.target,
                after=request.values,
                refusal=Refusal.merged_cell_target(covered),
            )

    rich = request.is_rich

    # A structured *proposed* value cannot be expressed as a PLAIN value write;
    # a rich request's encoded cell is exactly that structured value and is allowed.
    if not rich and _has_structured_cell(request.values):
        return PlanEntry.refused(
            target=request.target,
            after=request.values,
            refusal=_structured_cell_refusal(
                request.values,
                "proposed values contain a structured (rich) cell — use a RichCellWriteRequest",
                formula_detail=(
                    "proposed values contain a FORMULA cell "
                    "({\"type\":\"formula\",\"text\":\"=...\"}) — use a FormulaWriteRequest "
                    "(FormulaWriteRequest.for_a1(range, \"=SUM(...)\")), which owns the "
                    "expression precondition and the computed-value read-back. A "
                    "hand-assembled formula object in a plain value write is refused so it "
                    "cannot bypass that verification."
                ),
            ),
        )

    try:
        before = client.read_values(spreadsheet_token, target_a1)
    except LarkAPIError as e:
        # LD-131: classify the unreadable range — an id that is not a tab of this
        # spreadsheet is an UNKNOWN_TAB (with a did-you-mean), never the staleness story.
        # LD-150 / F20: a `90202` is about the RANGE, so it lands `malformed-range`.
        return PlanEntry.refused(
            target=request.target,
            after=request.values,
            refusal=_unreadable_tab_refusal(
                client, spreadsheet_token,
                sheet_id=request.target.sheet_id,
                detail=f"could not read target range {target_a1}: {e}",
                a1_range=target_a1, error=e,
            ),
        )

    # A structured *current* target would be flattened to a scalar by a plain value write;
    # a rich write EXPECTS the structured form, so it is not refused here.
    if not rich and _has_structured_cell(before):
        return PlanEntry.refused(
            target=request.target,
            after=request.values,
            refusal=Refusal.rich_cell_target(
                f"current target {target_a1} holds a structured (rich) cell — use a RichCellWriteRequest"
            ),
        )

    entry = PlanEntry.resolved(
        target=request.target, before=before, after=request.values, rich=rich)
    # LD-150 / dogfood F9 — ONE extra `Formula`-mode read discloses the live formulas this
    # write will destroy. The `before` above cannot: it is `UnformattedValue`, under which a
    # formula answers its computed scalar and reads exactly like data.
    note = _live_formula_note(client, spreadsheet_token, request.target, before)
    return entry if note is None else replace(entry, preview_note=note)


def _live_formula_note(client, spreadsheet_token, target: WriteRange, before):
    """The ``overwrites-live-formula`` note for a resolved value/rich write — or ``None``
    (LD-150 / dogfood **F9**).

    Costs **one** ``Formula``-mode read, beside the precondition read the previewer already
    made (AC2 — the ``MergeCells.loss_preview`` precedent: a destructive sheets write pays for
    a read). Placed after the entry resolves, so a refused entry (shape / rich / unreadable)
    buys nothing.

    **Degrades, never crashes.** This is a *diagnostic* read on an otherwise-successful path —
    the same posture as :func:`_tab_pairs` — so a seam that cannot serve a render-mode read
    (:class:`~larkdocio.sheets.formula.FormulaRenderOptionUnsupported`; the shipped
    :class:`~larkdocio.sheets.write_client.SheetsWriteClient` always can) or a read that fails
    yields no note rather than turning a good plan into a refusal. The value write itself is
    unaffected either way.
    """
    try:
        expressions = read_render(
            client, spreadsheet_token, target.a1(), EXPRESSION_RENDER_OPTION)
    except (FormulaRenderOptionUnsupported, LarkAPIError, LarkDocIOError):
        return None
    return overwrites_live_formula_note(
        live_formula_cells(
            expressions, before,
            ref=lambda r, c: A1Cell(target.start.col + c, target.start.row + r).a1(),
        ),
        a1_range=target.a1(),
    )



def _apply_value_one(entry: PlanEntry, client, spreadsheet_token, expected_revision):
    """Apply ONE resolved plain / rich value entry — the precondition re-read + the
    ``put_values`` write (LD-111 / LD-119). The compare-and-swap already passed in
    :func:`_apply_one`; this re-reads the target's current raw value and refuses
    ``PRECONDITION_MISMATCH`` (or ``RICH_CELL_TARGET`` if it became structured,
    ``TAB_VANISHED`` if unreadable) unless it still equals the plan's capture. On a refusal no
    write is issued and the anchor is unchanged (``expected_revision`` carried through).

    **This is the ``TAB_VANISHED`` site LD-131 reserved the reason FOR:** the plan-time
    preview already read this exact range successfully (that read produced ``entry.before``),
    so an unreadable range HERE means the tab was there and is gone mid-flight — genuine
    staleness, never an identifier-kind error. The plan-time sites classify (``UNKNOWN_TAB``
    when the tab never existed); this one does not, deliberately."""
    target_a1 = entry.target.a1()

    # (2) precondition — the target's current raw value must still match the plan capture.
    try:
        live_before = client.read_values(spreadsheet_token, target_a1)
    except LarkAPIError as e:
        refused = ApplyLogEntry.refused(
            target=entry.target,
            refusal=Refusal.tab_vanished(
                f"could not read target range {target_a1} at apply time (it WAS readable at "
                f"plan time — the tab vanished mid-flight): {e}"
            ),
        )
        return refused, expected_revision

    # A plain value write refuses a target that became structured (it would flatten a
    # rich cell); a rich write EXPECTS the structured form, so this guard is lifted for it
    # (the precondition equality below still guards the target read-to-read).
    # NOTE (LD-149): this guard cannot fire for a target that became a FORMULA. The
    # precondition read is `UnformattedValue`, under which a formula cell answers its
    # COMPUTED value — a scalar — so a formula is invisible here and a plain value write
    # silently replaces it with a static value. That asymmetry is documented in the shipped
    # guide's formula recipe — and, in the source repository rather than in the wheel, in SHEETS.md
    # § Notes — rather than papered over: catching it would cost a second `Formula`-mode
    # read on EVERY value entry.
    if not entry.rich and _has_structured_cell(live_before):
        refused = ApplyLogEntry.refused(
            target=entry.target,
            refusal=Refusal.rich_cell_target(
                f"target {target_a1} became a structured (rich) cell since plan time — "
                "use a RichCellWriteRequest"
            ),
        )
        return refused, expected_revision

    if live_before != entry.before:
        refused = ApplyLogEntry.refused(
            target=entry.target,
            refusal=Refusal.precondition_mismatch(expected=entry.before, live=live_before),
        )
        return refused, expected_revision

    # (3) all clear → write, then record the post-write revision (reply, else metainfo).
    reply = client.put_values(spreadsheet_token, target_a1, entry.after)
    post_revision = _post_write_revision(
        reply, lambda: client.read_revision(spreadsheet_token))
    applied = ApplyLogEntry.applied(
        target=entry.target,
        before=live_before,   # the live values actually replaced (truthful)
        after=entry.after,
        revision=post_revision,
    )
    return applied, post_revision
