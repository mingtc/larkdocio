"""larkdocio.sheets.ops._dropdown — the DROPDOWN-RULE family — data-validation writes.

No ``requests/`` twin of its own: ``DropdownRuleWriteRequest`` lives in ``requests/_cells.py``
beside the value classes, so this module is named after its own op family instead.

Split out of the flat 3,019-line ``sheets/ops.py`` by LD-532, **verbatim**. The
package's ``__init__`` holds the ``OPS`` registry, the dispatchers and the engine
loop, and re-exports every name defined here, so
``from larkdocio.sheets.ops import <name>`` is unchanged.
"""
from larkdocio.sheets.plan import ApplyLogEntry, PlanEntry

from ._shared import _post_write_revision


def _preview_dropdown(request, client, spreadsheet_token, merges=None) -> PlanEntry:
    """Preview a dropdown (``dataValidation``) rule write (LD-120). A rule is not a cell
    value — there is no scalar ``before`` to read/compare — so the preview carries the encoded
    rule as its ``after`` with **zero reads**; the ``revision`` compare-and-swap (at apply) is
    the sole guard. The write step (apply) is ``set_data_validation``, not ``put_values``."""
    return PlanEntry.resolved(
        target=request.target, before=None, after=request.rule,
        write_kind="data-validation",
    )


def _apply_dropdown_one(entry: PlanEntry, client, spreadsheet_token, expected_revision=None):
    """Apply ONE resolved dropdown-rule entry (LD-120). The compare-and-swap already passed in
    :func:`_apply_one`; a rule has **no scalar precondition** (no ``before`` cell value), so
    this writes the rule via the ``set_data_validation`` seam (``POST …/dataValidation``, never
    ``put_values``) and records the post-write revision (the POST reply omits it, so it always
    falls back to metainfo)."""
    target_a1 = entry.target.a1()
    reply = client.set_data_validation(spreadsheet_token, target_a1, entry.after)
    post_revision = _post_write_revision(
        reply, lambda: client.read_revision(spreadsheet_token))
    applied = ApplyLogEntry.applied(
        target=entry.target,
        before=entry.before,   # None — a rule has no cell-value before (destructive-safe
                               # removed-rule payload is LD-123's story)
        after=entry.after,
        revision=post_revision,
        write_kind="data-validation",
    )
    return applied, post_revision
