"""larkdocio.sheets.ops._formula — the FORMULA family — the render-mode-sensitive write.

The one write whose precondition reads the EXPRESSION and whose verification reads the
COMPUTED value. No ``requests/`` twin of its own: ``FormulaWriteRequest`` lives in
``requests/_cells.py`` beside the value classes, so this module is named after its own op
family instead.

Split out of the flat 3,019-line ``sheets/ops.py`` by LD-532, **verbatim**. The
package's ``__init__`` holds the ``OPS`` registry, the dispatchers and the engine
loop, and re-exports every name defined here, so
``from larkdocio.sheets.ops import <name>`` is unchanged.
"""
from dataclasses import replace

from larkdocio.errors import LarkAPIError
from larkdocio.sheets.formula import (
    COMPUTED_RENDER_OPTION,
    EXPRESSION_RENDER_OPTION,
    FormulaRenderOptionUnsupported,
    formula_expression,
    formula_preview_note,
    formula_record,
    read_render,
)
from larkdocio.sheets.plan import ApplyLogEntry, PlanEntry, Refusal

from ._shared import _covered_cell_hit, _post_write_revision, _unreadable_tab_refusal


def _preview_formula(request, client, spreadsheet_token, merges=None) -> PlanEntry:
    """Preview a FORMULA write (LD-149). Reads the target under **both** render legs, ZERO
    writes.

    * the ``Formula`` leg is the **precondition basis** — it becomes ``entry.before``, so
      apply compares the **EXPRESSION** (AC3: a computed value drifts whenever the referenced
      data changes, so comparing it would refuse writes nobody made);
    * the ``UnformattedValue`` leg is the **computed value**, carried in the entry's
      :attr:`~larkdocio.sheets.plan.PlanEntry.preview_note` for the reviewer and deliberately
      **not** compared.

    Refusals mirror the value leg exactly: a merge-**covered** target (only when ``merges``
    was supplied — the merge ANCHOR is writable, probed live) refuses ``MERGED_CELL_TARGET``,
    and an unreadable range is classified ``UNKNOWN_TAB`` (the tab listing proves the
    ``sheet_id`` never existed, LD-131) or ``TAB_VANISHED``. A client seam that cannot serve a
    render-mode read refuses ``INVALID_REQUEST`` naming the requirement, rather than letting
    a ``TypeError`` escape ``dry_run`` (which has no disposition boundary).
    """
    target_a1 = request.target.a1()

    if merges:
        covered = _covered_cell_hit(request.target, merges)
        if covered is not None:
            return PlanEntry.refused(
                target=request.target,
                after=request.values,
                refusal=Refusal.merged_cell_target(covered),
            )

    try:
        before = read_render(client, spreadsheet_token, target_a1, EXPRESSION_RENDER_OPTION)
        computed = read_render(client, spreadsheet_token, target_a1, COMPUTED_RENDER_OPTION)
    except FormulaRenderOptionUnsupported as e:
        return PlanEntry.refused(
            target=request.target, after=request.values,
            refusal=Refusal.invalid_request(str(e)),
        )
    except LarkAPIError as e:
        return PlanEntry.refused(
            target=request.target,
            after=request.values,
            refusal=_unreadable_tab_refusal(
                client, spreadsheet_token,
                sheet_id=request.target.sheet_id,
                detail=f"could not read formula target range {target_a1}: {e}",
                a1_range=target_a1, error=e,
            ),
        )

    entry = PlanEntry.resolved(
        target=request.target, before=before, after=request.values, write_kind="formula")
    return replace(entry, preview_note=formula_preview_note(
        request.expression, current_expression=before, current_computed_value=computed))


def _apply_formula_one(entry: PlanEntry, client, spreadsheet_token, expected_revision):
    """Apply ONE resolved FORMULA entry (LD-149) — the **expression** precondition, the
    object-form ``put_values`` write, then the two-leg verification read-back.

    The compare-and-swap already passed in :func:`_apply_one`. Then:

    1. **precondition** — re-read the target's ``Formula``-mode value and refuse
       ``PRECONDITION_MISMATCH`` unless it still equals the plan's capture. This compares the
       **EXPRESSION**, the maintainer-adopted choice (AC3): a computed value moves whenever the
       referenced data moves (probed: one operand edit took ``21``→``120``), so comparing it
       would manufacture refusals for edits nobody made. An unreadable range here is genuine
       staleness — ``TAB_VANISHED`` — because the preview read this exact range successfully;
    2. **write** the ``{"type":"formula","text":…}`` object form through ``put_values``;
    3. **verify** — re-read BOTH legs and record :func:`formula_record`. The ``evaluated``
       flag is the ONLY way to catch an unparsable expression: Lark **accepts** ``"=SUM("``
       with ``code 0`` and stores it as inert text, so there is no error to catch. The write
       DID land either way, so the outcome stays ``applied`` and the record carries the truth
       (surfaced as :attr:`~larkdocio.sheets.plan.ApplyLogEntry.formula_evaluated` /
       :attr:`~larkdocio.sheets.plan.ApplyLog.formula_not_evaluated`).

    A failure in step 3 happens **after** the write returned, so the LD-148 disposition
    boundary records it ``applied-unverified`` (the change IS on the spreadsheet) and halts —
    exactly the semantics that arm was built for.
    """
    target_a1 = entry.target.a1()

    try:
        live_before = read_render(
            client, spreadsheet_token, target_a1, EXPRESSION_RENDER_OPTION)
    except LarkAPIError as e:
        refused = ApplyLogEntry.refused(
            target=entry.target,
            write_kind="formula",
            refusal=Refusal.tab_vanished(
                f"could not read formula target range {target_a1} at apply time (it WAS "
                f"readable at plan time — the tab vanished mid-flight): {e}"
            ),
        )
        return refused, expected_revision

    if live_before != entry.before:
        refused = ApplyLogEntry.refused(
            target=entry.target,
            write_kind="formula",
            refusal=Refusal.precondition_mismatch(expected=entry.before, live=live_before),
        )
        return refused, expected_revision

    reply = client.put_values(spreadsheet_token, target_a1, entry.after)
    post_revision = _post_write_revision(
        reply, lambda: client.read_revision(spreadsheet_token))

    # The verification read-back — the expression Lark stored + the value it computed.
    stored = read_render(client, spreadsheet_token, target_a1, EXPRESSION_RENDER_OPTION)
    computed = read_render(client, spreadsheet_token, target_a1, COMPUTED_RENDER_OPTION)

    applied = ApplyLogEntry.applied(
        target=entry.target,
        before=live_before,     # the live EXPRESSION actually replaced (truthful)
        after=entry.after,
        revision=post_revision,
        write_kind="formula",
        formula=formula_record(
            expression=_entry_expression(entry),
            stored_expression=stored,
            computed_value=computed,
        ),
    )
    return applied, post_revision


def _entry_expression(entry: PlanEntry):
    """The expression a resolved formula entry writes — read off its own proposed payload
    (``after`` carries the encoded object form), so the record never depends on the request
    object still being around."""
    for row in entry.after or []:
        cells = row if isinstance(row, list) else [row]
        for cell in cells:
            expression = formula_expression(cell)
            if expression is not None:
                return expression
    return None
