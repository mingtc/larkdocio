"""larkdocio.sheets.ops — the ONE op-descriptor registry the sheets write engine dispatches
from (LD-125 T1, the docx ``write/ops.py`` replay).

**The problem this seam solves.** The value-write apply engine grew **two parallel per-op
dispatch ladders**, each keyed on a DIFFERENT discriminator, that had to be extended in
lockstep whenever a write family was added (the LD-119..LD-123 tranches each did this):

* :func:`_preview_one` branched on the **request-side** discriminator —
  ``request.write_kind`` (``"value"`` / ``"data-validation"`` / ``"structure"`` / ``"merge"``
  / ``"tab"``) and ``request.is_structural``;
* :func:`_apply_one` branched on the **entry-side** discriminator — ``entry.structural["op"]``
  (``"insert"`` / ``"delete"`` / … / ``"merge"`` / ``"add-tab"`` / …) and ``entry.write_kind``.

At LD-125, before this module existed, six families × two ladders keyed on different things
**was** the classic *divergent-change / shotgun-surgery* seam: adding a family meant coordinated
edits in both ladders that could silently drift (a request previewed by one ladder but
mis-served by the other corrupts a spreadsheet). That count is **history, not the current
arity** — the era is named so the sentence dates itself, because it is the one family count in
this package that must NOT track :data:`OPS` (LD-213; the guard registers it explicitly).

**The fix (this module).** One :class:`SheetsOpDescriptor` per family, gathered in the single
ordered :data:`OPS` table — *the* registration seam. Each descriptor carries **both** keyings
faithfully — ``write_kind`` (the request-side preview key) **and** ``entry_ops`` (the
entry-side apply key, the ``structural["op"]`` strings the family owns) — plus its ``preview``
and ``apply`` leaf legs. :func:`_preview_one` / :func:`_apply_one` collapse to a registry
lookup each: :func:`preview_dispatch` reads the request-side key, :func:`apply_dispatch` the
entry-side key. Adding a family is **ONE registration point** — append one
:class:`SheetsOpDescriptor` to :data:`OPS`; no edit to the dispatchers is needed.

**Layering (no lazy import needed).** Unlike the docx replay, this module sits cleanly ABOVE
its leaf modules — it imports the request classes (:mod:`larkdocio.sheets.requests`), the plan
value objects (:mod:`larkdocio.sheets.plan`) and the merge geometry
(:mod:`larkdocio.sheets.merge_geometry`), none of which import back — so a single top-level
table is a plain DAG with no circular-import remedy required. The thin
:mod:`larkdocio.sheets.write_apply` facade re-exports the public surface unchanged.

**Adding an op family — the registration checklist.** (LD-213. **Contributor**-facing, and
deliberately here rather than in a shipped consumer document: ``GUIDE.md``, ``README.md`` and
``SHEETS.md`` (that last one in the source repository, not in the wheel) are written for someone
*using* this surface, not extending it — ``larkdocio/blocks/BLOCK_TYPES.md`` § *Adding a new block type* is the precedent for text like
this.) **Dispatch** is genuinely one line; everything below is the rest of the seam, and it is
unwritten diligence no longer. LD-185 measured what a *small*, single-verb family actually cost
— the dimension-property write touched **9 src/doc files and 9 test files** (2 new, 7 edited),
3,913 insertions — so plan for that, not for one line. Each row says whether it is **HAND-KEPT**
(you must edit it) or **DERIVED** (do not — if you feel the urge, the descriptor is wrong), and
what breaks if it is forgotten.

**Where the legs live (LD-532).** This is a **package**, mirroring its sibling
:mod:`larkdocio.sheets.requests`: one module per op family, named after that package's twin
where the family has one (``_cells`` / ``_dimensions`` / ``_freeze`` / ``_merge`` /
``_structural`` / ``_styles`` / ``_tabs`` / ``_tab_presentation``) and after the family itself
where it has none (``_formula`` and ``_dropdown`` — their request classes live in the twin
package's ``_cells`` beside the value classes, so there is no twin module to be named after);
the helpers more than one family needs are in ``_shared``. A new family therefore authors its
``_preview_*`` / ``_apply_*_one`` pair, its note builders and its private helpers in a **new
module beside those**, and this ``__init__`` imports them. That is also the import direction,
in one line: ``_shared`` ← each family module ← this ``__init__``, with nothing running the
other way (the one sideways edge is ``_tabs`` → ``_tab_presentation``, because the presentation
writes are the same descriptor's other half). This ``__init__`` **re-exports every name the
family modules define**, so ``from larkdocio.sheets.ops import <name>`` reaches all of them
exactly as it did when this was one file.

* **REGISTER** ``larkdocio.sheets.ops.OPS`` — HAND-KEPT — append one
  :class:`SheetsOpDescriptor`, whose two legs are authored in the family's own module (above)
  rather than here. THE seam: preview and apply both reach the family with no other
  edit. Forget it and the family is simply unreachable — there is no second ladder left to
  half-serve it, which is the whole point of this package.
* **REGISTER** ``larkdocio.sheets.requests.WriteOpKind`` — HAND-KEPT — the op-kind vocabulary
  the write-gate fidelity legs key on. Forget it and the gate cannot name what the write
  touched, so it cannot certify the write surgical.
* **REGISTER** ``larkdocio.sheets.requests.STYLE_LEG_OP_KINDS`` — HAND-KEPT — the kinds whose
  proof needs the export-based style / number-format leg. Forget it and a style-affecting
  family is certified by a differ that never looked at style.
* **REGISTER** ``larkdocio.sheets.requests.MERGE_LEG_OP_KINDS`` — HAND-KEPT — the kinds whose
  proof needs the live v3 merges leg. Forget it and a geometry-moving family is certified
  without re-reading the merges it moved.
* **REGISTER** ``larkdocio.sheets.disposition.WRITE_SEAMS`` — HAND-KEPT — every client method
  that WRITES. Forget it and the engine reports "nothing landed" about a call that landed
  something: the worst entry on this list, because the failure reads as reassurance.
* **REGISTER** ``larkdocio.sheets.disposition.READ_SEAMS`` — HAND-KEPT — a new plan-time or
  post-write **read** the family needs. Forget it and the read/write/lifecycle split over the
  client surface stops being exhaustive, which its own invariant guard reddens on.
* **REGISTER** ``larkdocio.sheets.write_apply`` — HAND-KEPT — the facade's re-export block (it
  has no ``__all__``; it *is* the historical import path). Forget a name and a consumer's
  existing import breaks, with no other symptom.
* **REGISTER** ``tests/test_sheets_md_matrix.py::_WRITE_CLIENT_SHIPPED`` — HAND-KEPT (in the source
  repository) — the ``shipped-LD-NNN`` slug for a new write-client op. Forget it and the matrix guard
  does not recognise the row's status.
* **REGISTER** ``tests/test_sheets_md_matrix.py::_SHIPPED_STATUSES`` — HAND-KEPT (in the source
  repository) — the SAME slug, second of its three homes. Forget it and the status-honesty check
  refuses the row.
* **REGISTER** ``SHEETS.md`` — HAND-KEPT (in the source repository) — the same slug's third home, plus
  the family's own capability row. Forget it and the living-matrix guard reddens (by design:
  touch the surface, update the matrix).
* **REGISTER** ``src/larkdocio/GUIDE.md`` — HAND-KEPT, and unlike the two rows above it **ships
  in the wheel** — a recipe for the
  family. Forget it and the guide-completion guard reddens. Do **not** hand-edit the family
  arity there; it is derived (next row).
* **REGISTER** ``larkdocio.capabilities.capabilities`` — DERIVED — one projected op per
  descriptor, straight off :data:`OPS`. Nothing to edit.
* **REGISTER** ``tests/test_sheets_registration_seam.py`` — DERIVED (in the source repository) — the
  family **arity** stated in this package's module docstrings and the guide's, checked against
  :data:`OPS` on the request-family basis (one per registered op kind, plus the rich-cell
  request family folded into ``value``). Nothing to edit: it will simply tell you which
  sentences your new family has just made false.
* **REGISTER** ``larkdocio.permissions`` — HAND-KEPT — the endpoint→scope row for any endpoint
  family the table does not know yet, with its evidence pointer and verification label. Forget
  it and the permissions registry guard reddens; invent a scope string and the library starts
  lying about what a consumer must grant.
"""
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

from larkdocio.errors import LarkAPIError, LarkDocIOError, gate_refusals

if TYPE_CHECKING:  # pragma: no cover - typing only, no import cost / no cycle
    # The class the public ``client`` parameter wants. Named in the signature (as a
    # forward reference) because dogfood F8 found ``dry_run(requests, client, token)``
    # untyped, with the guide reusing the READ recipe's ``client`` variable one recipe
    # above — so a consumer had to GUESS that a write plan wants the WRITE client.
    from larkdocio.sheets.write_client import SheetsWriteClient
from larkdocio.sheets.write_range import (
    A1Cell,
    A1RangeError,
    WriteRange,
    matrix_shape,
    parse_write_range,
)
from larkdocio.sheets.extent import trim_pad_along, used_extent_along
from larkdocio.sheets.disposition import (
    WriteWatch,
    classify_apply_exception,
    disposition_refusal,
)
from larkdocio.sheets.formula import (
    COMPUTED_RENDER_OPTION,
    EXPRESSION_RENDER_OPTION,
    FormulaRenderOptionUnsupported,
    equals_prefixed_note,
    formula_expression,
    formula_preview_note,
    formula_record,
    live_formula_cells,
    overwrites_live_formula_note,
    read_render,
)
from larkdocio.sheets.merge_geometry import _normalize_merge
from larkdocio.sheets.models import FrozenPanes
from larkdocio.sheets.plan import (
    MENTION_VALIDATION_ACTIVE,
    MENTION_VALIDATION_UNAVAILABLE,
    _PLAN_TOKEN,
    ApplyLog,
    ApplyLogEntry,
    Plan,
    PlanEntry,
    Refusal,
    combine_preview_notes,
)
from larkdocio.sheets.requests import (
    AddTab,
    BatchStyleWriteRequest,
    StyleWriteRequest,
    FreezePanes,
    ReorderTab,
    RetitleTab,
    SetTabVisibility,
    AppendDimension,
    AppendRowsWithValues,
    CopyTab,
    DeleteCols,
    DeleteRows,
    DeleteTab,
    DropdownRuleWriteRequest,
    FormulaWriteRequest,
    InsertColsAt,
    InsertRowsAt,
    MergeCells,
    RichCellWriteRequest,
    SetColProperties,
    SetRowProperties,
    UnmergeCells,
    ValueWriteRequest,
)

# --------------------------------------------------------------------------- #
# THE FAMILY LEGS (LD-532) — one module per op family, mirroring the sibling  #
# ``sheets/requests/`` package. Imported here and RE-EXPORTED by this import: #
# every name below resolved at ``larkdocio.sheets.ops`` before the split, and #
# a sibling module, the test estate and a shipped capability matrix all       #
# address them by that dotted path, so they must resolve there still. The     #
# import block ABOVE is kept whole for the same reason                        #
# ``requests/__init__.py`` keeps its own: ``dir()`` reports what a module     #
# imports, so dropping a now-unused name would shrink this module's surface.  #
# --------------------------------------------------------------------------- #
from ._shared import (
    MALFORMED_RANGE_CODE,
    VerificationLeg,
    _covered_cell_hit,
    _did_you_mean,
    _is_malformed_range,
    _post_write_revision,
    _revision_of,
    _tab_pairs,
    _unreadable_tab_refusal,
)
from ._cells import (
    _apply_value_one,
    _has_formula_cell,
    _has_structured_cell,
    _live_formula_note,
    _preview_value,
    _structured_cell_refusal,
)
from ._formula import (
    _apply_formula_one,
    _entry_expression,
    _preview_formula,
)
from ._dropdown import (
    _apply_dropdown_one,
    _preview_dropdown,
)
from ._merge import (
    _apply_merge_one,
    _merge_hit,
    _preview_merge,
    no_merge_at_range_note,
)
from ._structural import (
    _PAD_AXIS,
    _RemovedSnapshotFailed,
    _apply_structural_one,
    _geometry_delta,
    _intersecting_merges,
    _preview_structural,
    _removed_dimension_range_a1,
    _snapshot_removed_dimension,
    _trim_removed_values,
    out_of_bounds_dimension_note,
)
from ._dimensions import (
    DIMENSION_VERIFICATION,
    DIMENSION_VERIFICATION_LEG,
    DIMENSION_VERIFICATION_NOTE,
    _apply_dimension_property_one,
    _preview_dimension_property,
    hidden_dimension_note,
)
from ._freeze import (
    FREEZE_VERIFICATION,
    FREEZE_VERIFICATION_LEG,
    FREEZE_VERIFICATION_NOTE,
    _apply_freeze_one,
    _preview_freeze,
    frozen_replacement_note,
)
from ._styles import (
    STYLE_LEG_SCOPE,
    STYLE_VERIFICATION,
    STYLE_VERIFICATION_LEG,
    STYLE_VERIFICATION_NOTE,
    _apply_style_one,
    _merge_a1,
    _preview_style,
    _style_reply_revision,
    style_border_not_verifiable_note,
    style_export_cost_note,
    style_partial_merge_note,
)
from ._tab_presentation import (
    TAB_PRESENTATION_OPS,
    _preview_tab_presentation,
    hidden_tab_note,
    retitle_join_note,
    tab_presentation_noop_note,
)
from ._tabs import (
    TAB_VERIFICATION,
    TAB_VERIFICATION_LEG,
    TAB_VERIFICATION_NOTE,
    _apply_tab_one,
    _observe_tab,
    _preview_tab,
)


def _malformed_target_entry(request) -> Optional[PlanEntry]:
    """The **pre-I/O** ``malformed-range`` refusal for a request whose target range is not an
    addressable rectangle (LD-150 / F20) — or ``None``.

    The reversal the seat session hit (``C3:A1``) is knowable from the range **alone**, so this
    runs at the :func:`_preview_one` seam before any leg: the refusal costs **zero** calls and
    carries the right diagnosis instead of Lark's raw ``90202`` under a ``tab-vanished`` label.
    The check IS :meth:`~larkdocio.sheets.write_range.WriteRange.validate` (no grid extent —
    inversion, sub-``1`` coordinates and the 100-column notation ceiling), so the offline model
    and the wire agree on what "malformed" means by construction.

    It runs **before** the arity check on purpose: a reversed range has a nonsense shape, and
    ``shape-mismatch`` would then explain the wrong thing.
    """
    target = getattr(request, "target", None)
    if not isinstance(target, WriteRange):
        return None
    try:
        target.validate()
    except A1RangeError as exc:
        return PlanEntry.refused(
            target=target,
            after=getattr(request, "values", None),
            refusal=Refusal.malformed_range(a1_range=target.a1(), detail=str(exc)),
        )
    return None


def _shape_mismatch_entry(request) -> Optional[PlanEntry]:
    """The **pre-I/O** ``shape-mismatch`` refusal for a request whose values matrix does not
    match its target range's arity (LD-150 / dogfood **F21**) — or ``None``.

    Checked at the :func:`_preview_one` seam (see there) rather than per leg, so **every**
    values-bearing family is covered and a future family cannot forget. It applies to a request
    that carries BOTH a range ``target`` and a ``values`` matrix and is **not** structural:

    * a plain / rich / formula write — the values ARE the target's new contents, so the arity
      must match (a rich cell and a formula are 1×1 by construction, D2, so a multi-cell target
      is a mismatch);
    * a **dropdown-rule** request has no ``values`` (it carries a ``rule``) → skipped;
    * a **merge / unmerge** carries a target but no ``values`` → skipped;
    * :class:`~larkdocio.sheets.requests.AppendRowsWithValues` is structural — its rows are
      **appended**, not written into a rectangle, so there is no arity to match → skipped.

    Zero reads: the arity is entirely a property of the caller's own payload.
    """
    target = getattr(request, "target", None)
    if getattr(request, "is_structural", False) or not isinstance(target, WriteRange):
        return None
    if not hasattr(request, "values"):
        return None
    values = request.values
    if matrix_shape(values) == (target.n_rows, target.n_cols):
        return None
    return PlanEntry.refused(
        target=target,
        after=values,
        refusal=Refusal.shape_mismatch(target=target, values=values),
    )


def _preview_one(request, client, spreadsheet_token, merges=None) -> PlanEntry:
    """One request → its plan entry (zero writes). Dispatches to the op's **preview** leg
    through the :data:`OPS` registry keyed on the **request-side** discriminator
    (``request.write_kind``; an unregistered kind falls back to the value leg, matching the
    former ``else``-is-value ladder). The former hand-branched ``write_kind`` /
    ``is_structural`` ladder is now ONE registry lookup (:func:`preview_dispatch`).

    **Two disclosures are enforced HERE, at the one seam** every request of every family
    passes through — so no family can forget either, and a future family inherits both:

    * the LD-149 ``=``-prefix warning — a plain-string value beginning with ``"="`` (which Lark
      stores as INERT TEXT, dogfood round-2 **T23**) is flagged loudly in the dry-run output no
      matter which family carries it;
    * the LD-150 ``malformed-range`` refusal (dogfood **F20**) and the LD-150
      ``shape-mismatch`` refusal (dogfood **F21**) — both decided **before** the leg runs, so
      neither costs a read and the leg never previews a write the plan cannot describe. The
      **order is load-bearing**: a malformed (e.g. reversed) range also has a nonsense arity,
      and answering "shape mismatch" would explain the wrong thing.

    Notes **compose** (LD-150): a leg's own note no longer suppresses the seam's, because a
    disclosure that displaces another disclosure is the F8 bug in miniature. See
    :func:`~larkdocio.sheets.plan.combine_preview_notes`.
    """
    entry = _malformed_target_entry(request) or _shape_mismatch_entry(request)
    if entry is None:
        entry = preview_dispatch(request, client, spreadsheet_token, merges=merges)
    note = combine_preview_notes(
        entry.preview_note, equals_prefixed_note(getattr(request, "values", None)))
    return entry if note == entry.preview_note else replace(entry, preview_note=note)


def _validate_mention_ids(entries: List[PlanEntry], client) -> Tuple[List[PlanEntry], Optional[dict]]:
    """Plan-time @mention ``open_id`` validation (LD-148 AC5) — **ONE** read call for the
    whole batch. Returns ``(entries, record)``.

    The failure class that produced the T27 Blocker was a mention id Lark answers with
    ``90204 id not found`` **at apply time**, mid-batch. This moves it to plan time: every
    mention id in the batch is collected from the previewed entries' own payloads (so the
    check is family-agnostic — see :attr:`PlanEntry.mention_open_ids`), looked up in ONE call,
    and any id Lark **proves** nonexistent turns its entry into an ``unknown-mention``
    refusal before a single write is issued.

    **Falsification-based, deliberately.** The lookup is only trusted to prove
    NON-existence — that is all Lark reliably reports (probed read-only 2026-07-28: a
    nonexistent id comes back as code ``99992351`` with the id named in
    ``error.field_violations``, while a **real** id comes back code ``0`` with ``items: []``
    when the app holds no contact *detail* scope). So "absent from ``resolved``" is never
    treated as absent from the directory; only a positively-reported invalid id refuses.

    **Never silently skipped.** A client seam without ``validate_user_ids``, or a lookup that
    raises (no scope / network / API drift), yields an ``unavailable`` record **with the WHY**
    that :class:`Plan` carries into its dry-run output — and the entries are left resolved, so
    a bad id then surfaces at apply as a typed per-entry ``api-error`` refusal (the batch
    continues) rather than a crash. Silence is the one outcome that is not allowed.
    """
    checked: List[str] = []
    for entry in entries:
        if not entry.is_resolved:
            continue
        for open_id in entry.mention_open_ids:
            if open_id not in checked:
                checked.append(open_id)
    if not checked:
        return entries, None      # nothing to validate; Plan derives "not-applicable"

    validator = getattr(client, "validate_user_ids", None)
    if not callable(validator):
        return entries, {
            "status": MENTION_VALIDATION_UNAVAILABLE,
            "detail": (
                f"@mention open_id validation is UNAVAILABLE: this client seam provides no "
                f"validate_user_ids(...), so the {len(checked)} mention id(s) in this plan "
                f"({', '.join(checked)}) are UNVERIFIED. Use "
                f"SheetsWriteClient.from_write_credentials() (which does) to have a "
                f"nonexistent id refused at plan time. Until then a bad id surfaces at apply "
                f"as a typed per-entry api-error refusal — the batch continues and every "
                f"entry is still logged, never a raised exception."
            ),
            "checked": list(checked), "resolved": {}, "invalid": [],
        }

    try:
        result = validator(checked) or {}
    except Exception as exc:   # noqa: BLE001 — a failed CHECK must never fail the PLAN
        return entries, {
            "status": MENTION_VALIDATION_UNAVAILABLE,
            "detail": (
                f"@mention open_id validation is UNAVAILABLE: the directory lookup failed "
                f"({type(exc).__name__}: {exc}), so the {len(checked)} mention id(s) in this "
                f"plan ({', '.join(checked)}) are UNVERIFIED. The usual cause is a missing "
                f"contact scope on the WRITE app — grant the scope Lark names in that message "
                f"to turn the check on. This is DISCLOSED, not skipped: a bad id still cannot "
                f"crash apply(), it surfaces as a typed per-entry api-error refusal and the "
                f"batch continues."
            ),
            "checked": list(checked), "resolved": {}, "invalid": [],
        }

    invalid = [i for i in (result.get("invalid") or ()) if i in checked]
    resolved = dict(result.get("resolved") or {})
    record = {
        "status": MENTION_VALIDATION_ACTIVE,
        "detail": (
            f"@mention open_id validation is ACTIVE: {len(checked)} id(s) checked in one "
            f"lookup, {len(invalid)} proved nonexistent by Lark and refused "
            f"(unknown-mention) at plan time — the 90204 id-not-found class can no longer "
            f"reach apply from this plan. The check proves EXISTENCE only (it does not prove "
            f"the user is reachable, and a display name is not required)."
            + (f" Invalid: {', '.join(invalid)}." if invalid else "")
        ),
        "checked": list(checked), "resolved": resolved, "invalid": invalid,
    }
    if not invalid:
        return entries, record

    bad = set(invalid)
    refused: List[PlanEntry] = []
    for entry in entries:
        hits = [i for i in entry.mention_open_ids if i in bad] if entry.is_resolved else []
        if not hits:
            refused.append(entry)
            continue
        # `replace` (not PlanEntry.refused) so the entry keeps everything it already
        # previewed — its target, its proposed `after`, and a structural descriptor if it
        # has one — and only the outcome + refusal change.
        refused.append(replace(
            entry,
            outcome="refused",
            refusal=Refusal.unknown_mention(open_id=hits[0] if len(hits) == 1 else hits),
        ))
    return refused, record


def dry_run(
    requests,
    client: "SheetsWriteClient",
    spreadsheet_token: str,
    *,
    merges=None,
) -> Plan:
    """Preview a batch of write requests against ``spreadsheet_token`` — ZERO writes.

    ``client`` is a :class:`~larkdocio.sheets.write_client.SheetsWriteClient` — the
    **WRITE**-app client (``SheetsWriteClient.from_write_credentials()``), NOT the
    :class:`~larkdocio.sheets.client.SheetsReadClient` the read recipes use. The seam is
    duck-typed (any object providing ``read_revision`` / ``read_values`` / ``put_values``
    and the structural/tab methods works, which is how the offline suites inject a fake
    gateway), but ``SheetsWriteClient`` is the shipped implementation and the annotation
    names it so ``inspect.signature`` answers the question.

    ``requests`` is any iterable of the **ten** write-request families (value / formula /
    rich-cell / dropdown-rule / structural / dimension-property / style / merge·unmerge / tab /
    freeze-panes) — each routed to its preview leg by the :data:`OPS` registry on its
    ``write_kind`` (no longer only a ``ValueWriteRequest``, which an earlier annotation wrongly
    implied). The arity is :data:`OPS`'s, guarded rather than hand-kept
    (``tests/test_sheets_registration_seam.py``); the typed request objects behind each family
    are enumerated once, in :mod:`larkdocio.sheets.requests`' own module docstring, so this
    signature does not carry a second list to drift.

    Caches the spreadsheet ``revision`` **at plan time** (the compare-and-swap anchor),
    then previews each request (a value target reads its *before*; a rule / structural / merge
    / tab op previews with the reads its own leg needs). Returns a :class:`Plan` whose entries
    are 1:1 with the input batch, in order. **No write op is involved** — ``dry_run`` has no
    write call at all, so it *structurally* cannot write.

    ``merges`` (opt-in) — the tab's merge regions (0-idx END-inclusive v3 dicts or
    4-tuples). When supplied, a plain/rich value write whose target intersects a merge's
    **covered** (non-anchor) cell refuses ``MERGED_CELL_TARGET``. Omit it (the default) and the
    value path is merge-unaware — byte-identical to the pre-merge behavior.

    **The returned plan always discloses the staleness guard's state**: a plan-time
    ``revision`` of ``0`` / ``None`` (the per-spreadsheet sentinel a live probe found) means
    the compare-and-swap cannot observe an advance, and
    :attr:`~larkdocio.sheets.plan.Plan.revision_guard` says ``"unavailable"`` (with the WHY)
    instead of letting the guard no-op invisibly. Nothing is refused for it — the value
    precondition is still enforced per entry, and any nonzero advance still refuses
    ``STALE_SHEET``.
    """
    revision = client.read_revision(spreadsheet_token)
    entries: List[PlanEntry] = [
        _preview_one(request, client, spreadsheet_token, merges=merges) for request in requests
    ]
    # LD-148 AC5 — the plan-time @mention id check (ONE read call, only when the batch
    # actually mentions someone). An id Lark proves nonexistent refuses HERE; a check that
    # cannot run is disclosed in the plan, never silently skipped.
    entries, mention_validation = _validate_mention_ids(entries, client)
    return Plan(
        entries,
        revision=revision,
        spreadsheet_token=spreadsheet_token,
        mention_validation=mention_validation,
        _token=_PLAN_TOKEN,
    )


def _apply_one(entry: PlanEntry, client, spreadsheet_token, expected_revision):
    """Execute ONE resolved entry. Returns ``(log_entry, next_expected_revision)``.

    (1) the op-agnostic D5 **compare-and-swap** — re-read ``revision`` right before the write
    and refuse ``STALE_SHEET`` (no write) if it advanced, resyncing the anchor so the rest of
    the batch still applies; then (2) dispatch to the op's **apply** leg through the
    :data:`OPS` registry keyed on the **entry-side** discriminator (``entry.structural["op"]``
    for a structural / merge / tab entry, else ``entry.write_kind`` — value vs dropdown-rule).
    The former hand-branched entry ladder is now ONE registry lookup (:func:`apply_dispatch`);
    the shared stale guard stays here because it is identical for every op."""
    # (1) compare-and-swap — re-read the revision IMMEDIATELY before this write (D5).
    # Shared by ALL write kinds, so a stale entry (value / rich / dropdown / structural)
    # skips its write and reads nothing further (no geometry re-read on a skipped write).
    live_revision = client.read_revision(spreadsheet_token)
    if live_revision != expected_revision:
        stale = ApplyLogEntry.stale(
            target=entry.target,
            refusal=Refusal.stale_sheet(cached=expected_revision, live=live_revision),
            structural=entry.structural,
        )
        # Resync the anchor to the now-current revision so a single external write does not
        # poison the whole rest of the batch — each later entry is judged afresh (and its
        # own precondition still guards its target independently).
        return stale, live_revision

    # (2) dispatch to the op's apply leg (entry-side keying), fresh-revision-guarded above.
    return apply_dispatch(entry, client, spreadsheet_token, expected_revision)


def apply(plan: Plan, client: "SheetsWriteClient", *,
          allow_partial: bool = False) -> ApplyLog:
    """Execute a dry-run ``plan`` against its spreadsheet via ``client``.

    ``client`` is the same :class:`~larkdocio.sheets.write_client.SheetsWriteClient` the
    plan was previewed with (the WRITE app — never the read client; see :func:`dry_run`).

    Only a :class:`Plan` from :func:`dry_run` is accepted — the hard gate: a non-``Plan``
    (a bag of requests / entries) raises :class:`TypeError`, so there is structurally no
    path that applies an unpreviewed write. Each entry is processed in plan order:

    * a **refused** entry (decided at dry-run) is carried into the apply-log verbatim — no
      write;
    * a **resolved** entry runs the compare-and-swap + precondition guards, then writes
      (see :func:`_apply_one`).

    Every processed entry yields exactly one :class:`ApplyLogEntry`; the returned
    :class:`ApplyLog` is 1:1 with the plan, in order. Only fresh, resolved, precondition-
    clean writes reach the transport (``put_values``); any refusal / stale skips it.

    **Every log entry carries the plan-time ``revision_guard`` status**: on a
    spreadsheet whose ``revision`` anchor is unavailable (a constant ``0`` / ``None``) the
    compare-and-swap cannot observe an advance, and the audit record says so instead of
    looking identical to a fully guarded write.

    **NO EXCEPTION ESCAPES — every entry ends in a typed, logged disposition.**
    Each per-entry step runs inside a disposition boundary. Any :class:`Exception` it raises —
    a Lark error code, a rate limit, a dead socket, a library bug — is **classified**
    (:func:`~larkdocio.sheets.disposition.classify_apply_exception`) and **recorded**, never
    propagated:

    * an **entry-scoped** error (Lark answered about THIS entry — the ``90204 id not found``
      class, or a local pre-wire validation error) refuses that entry ``api-error`` /
      ``invalid-request`` and the **batch CONTINUES** (the deliberate sheets per-entry
      doctrine);
    * a **systemic** error (a **scope denial** / rate limit / transport / anything un-modelled)
      **HALTS** the batch, and **every remaining entry is logged ``not-attempted``** — never
      silently dropped. A scope denial is systemic even though Lark answered with a ``code``:
      the answer is about the **app**, not this entry, so it would refuse every remaining entry
      identically — the one coded failure whose blast radius is *knowable*, and the refusal
      relays Lark's own missing scope and console link so the repair is a console grant, then a
      re-plan;
    * a failure **after** the write op returned is logged ``applied-unverified`` (the change IS
      on the sheet, its verification record is not) and halts, because the compare-and-swap
      anchor is then unknown.

    So ``len(log.entries) == len(plan.entries)`` for **every** run, and
    :attr:`~larkdocio.sheets.plan.ApplyLog.halt` says whether the batch stopped early and why.
    In an earlier release a raw ``LarkAPIError`` escaped this loop mid-batch and the failing
    entry AND the remainder got no disposition at all.

    **An entry that did not land RAISES** :class:`~larkdocio.errors.LarkApplyRefusedError`
    unless ``allow_partial=True`` — the same one spelling every plan-gated apply here takes. This does **not** weaken the invariant above: the log is built
    exactly as it always was, every entry still ends in a typed disposition, and the finished
    log travels **on** the exception (``err.log``) together with what landed (``err.applied``)
    and each refusal's reason + detail (``err.refusals``). What changed is that a caller who
    discards the log can no longer mistake a halted or half-refused batch for a clean run.
    """
    if not isinstance(plan, Plan):
        raise TypeError(
            "apply() accepts ONLY a dry-run plan produced by "
            "larkdocio.sheets.write_apply.dry_run(...); got "
            f"{type(plan).__name__}. Build a plan via the previewer, not raw requests."
        )

    token = plan.spreadsheet_token
    expected_revision = plan.revision
    guard = plan.revision_guard      # LD-132 — the plan-time tier-1 status (never silent)
    entries: List[ApplyLogEntry] = []
    halt: Optional[dict] = None      # LD-148 — set by the first SYSTEMIC disposition

    # The loop walks EVERY plan entry unconditionally and appends EXACTLY ONE log entry per
    # iteration — the apply-log's completeness is structural, not asserted after the fact.
    for index, entry in enumerate(plan.entries):
        if halt is not None:
            # The batch stopped earlier: this entry was never attempted, and says so.
            entries.append(
                ApplyLogEntry.not_attempted(
                    target=entry.target,
                    write_kind=entry.write_kind,
                    structural=entry.structural,
                    refusal=Refusal.not_attempted(
                        halted_at=halt["index"], reason=halt["reason"]),
                ).with_revision_guard(guard).with_preview_note(entry.preview_note)
            )
            continue

        if not entry.is_resolved:
            entries.append(
                ApplyLogEntry.refused(target=entry.target, refusal=entry.refusal)
                .with_revision_guard(guard).with_preview_note(entry.preview_note)
            )
            continue

        # THE DISPOSITION BOUNDARY. The watch is what lets the disposition tell "the write
        # never happened" from "the write happened and its verification did not" — a log that
        # guessed there would be a log that lies.
        watch = WriteWatch(client)
        try:
            log_entry, expected_revision = _apply_one(entry, watch, token, expected_revision)
        except Exception as exc:   # noqa: BLE001 — THE invariant: nothing escapes apply()
            disposition = classify_apply_exception(exc, wrote=watch.wrote)
            refusal = disposition_refusal(
                disposition, exc,
                where=_entry_label(entry),
                wrote_seams=watch.completed,
            )
            log_entry = _disposition_log_entry(entry, disposition, refusal)
            if disposition.halts:
                halt = {
                    "index": index,
                    "reason": disposition.reason,
                    "detail": refusal.detail,
                    "landed": disposition.landed,
                    "not_attempted": len(plan.entries) - index - 1,
                }
        # LD-132 + LD-150 / F8 — the ONE seam every log entry passes through, so the plan's
        # disclosure (its `preview_note`) and the plan-time guard status are CARRIED rather
        # than rebuilt per disposition arm. Before LD-150 the log built a fresh record on
        # success and the LOUD inert-string warning died right here.
        entries.append(
            log_entry.with_revision_guard(guard).with_preview_note(entry.preview_note))

    log = ApplyLog(entries=tuple(entries), halt=halt)
    return gate_refusals(log, allow_partial=allow_partial,
                         surface="larkdocio.sheets.write_apply.apply")


def _entry_label(entry: PlanEntry) -> str:
    """A short, human-readable "which entry" for a disposition detail — the op family + its
    target, so a log line is actionable without cross-referencing the plan."""
    op = (entry.structural or {}).get("op") or entry.write_kind
    where = entry.target.a1() if entry.target is not None else (
        (entry.structural or {}).get("semantic")
        or (entry.structural or {}).get("a1_range")
        or (entry.structural or {}).get("sheet_id")
        or "no A1 target"
    )
    return f"{op} on {where}"


def _disposition_log_entry(entry: PlanEntry, disposition, refusal: Refusal) -> ApplyLogEntry:
    """Build the apply-log entry for a classified per-entry failure (LD-148).

    One place maps a :class:`~larkdocio.sheets.disposition.Disposition`'s ``outcome`` to its
    :class:`ApplyLogEntry` factory, so the outcome vocabulary cannot drift from the
    classification table.
    """
    if disposition.outcome == "applied-unverified":
        return ApplyLogEntry.applied_unverified(
            target=entry.target, before=entry.before, after=entry.after,
            write_kind=entry.write_kind, structural=entry.structural, refusal=refusal,
        )
    if disposition.outcome == "failed":
        return ApplyLogEntry.failed(
            target=entry.target, write_kind=entry.write_kind,
            structural=entry.structural, refusal=refusal)
    return ApplyLogEntry.refused(
        target=entry.target, write_kind=entry.write_kind,
        structural=entry.structural, refusal=refusal)


# --------------------------------------------------------------------------- #
# The op-descriptor registry — THE single registration seam (LD-125 T1).      #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SheetsOpDescriptor:
    """One sheets write op-family's complete dispatch record — BOTH keyings + both legs.

    * ``kind`` — the family name (``"value"`` / ``"dropdown"`` / ``"structural"`` / ``"merge"``
      / ``"tab"``);
    * ``request_type`` — the concrete request classes of this family (for :func:`classify` and
      a future capability projection);
    * ``write_kind`` — the **request-side** preview discriminator (``request.write_kind``);
    * ``entry_ops`` — the **entry-side** apply discriminators: the ``structural["op"]`` strings
      this family owns (``()`` for the value / dropdown families, whose entries carry
      ``structural is None`` and route on ``entry.write_kind`` instead);
    * ``preview`` — ``(request, client, token, merges) -> PlanEntry``;
    * ``apply`` — ``(entry, client, token, expected_revision) -> (ApplyLogEntry, next_rev)`` (a
      resolved, fresh-revision-guarded entry only — the stale / refused arms are op-agnostic and
      handled once above the dispatch).

    Both keyings are carried so the preview and apply dispatchers can never disagree on a
    family. To add a family: author its two legs and append **one** ``SheetsOpDescriptor`` to
    :data:`OPS` — no dispatcher edit.
    """

    kind: str
    request_type: tuple
    write_kind: str
    entry_ops: tuple
    preview: Callable
    apply: Callable


#: The ordered registry — the ONE registration seam. ``value`` is first and also the
#: request-side fallback (an unrecognized ``write_kind`` → the value leg), matching the former
#: ``_preview_one`` ``else``-is-value ladder; ``structural`` is the entry-side fallback for a
#: structural entry with an unrecognized ``op`` (its own unknown-op raise is preserved inside
#: :func:`_apply_structural_one`), matching the former ``_apply_one`` ``else`` branch.
OPS: Tuple[SheetsOpDescriptor, ...] = (
    SheetsOpDescriptor(
        kind="value",
        request_type=(ValueWriteRequest, RichCellWriteRequest),
        write_kind="value",
        entry_ops=(),
        preview=_preview_value,
        apply=_apply_value_one,
    ),
    SheetsOpDescriptor(
        # LD-149 — the FORMULA family. Its own descriptor (not a value variant) because it is
        # the one write whose precondition and verification read by RENDER MODE: the
        # precondition compares the EXPRESSION (`Formula`) and the verification reads the
        # COMPUTED value (`UnformattedValue`). `entry_ops` is empty, so its entries route on
        # `entry.write_kind` exactly like the value / dropdown families.
        kind="formula",
        request_type=(FormulaWriteRequest,),
        write_kind="formula",
        entry_ops=(),
        preview=_preview_formula,
        apply=_apply_formula_one,
    ),
    SheetsOpDescriptor(
        kind="dropdown",
        request_type=(DropdownRuleWriteRequest,),
        write_kind="data-validation",
        entry_ops=(),
        preview=_preview_dropdown,
        apply=_apply_dropdown_one,
    ),
    SheetsOpDescriptor(
        kind="structural",
        request_type=(InsertRowsAt, InsertColsAt, DeleteRows, DeleteCols,
                      AppendDimension, AppendRowsWithValues),
        write_kind="structure",
        entry_ops=("insert", "delete", "append-dim", "append-values"),
        preview=_preview_structural,
        apply=_apply_structural_one,
    ),
    SheetsOpDescriptor(
        # LD-185 — the DIMENSION-PROPERTY family (row height / column width / hide-show).
        # Its own descriptor, not a structural variant, for two reasons that both matter: its
        # native index convention is the OPPOSITE of insert's (1-idx inclusive, characterized
        # live), and it moves nothing — so the structural leg's geometry-delta verification
        # would measure a zero and the export style leg has no business firing for a column
        # width. Verified by its own dimension leg (DIMENSION_VERIFICATION_LEG).
        kind="dimension-property",
        request_type=(SetRowProperties, SetColProperties),
        write_kind="dimension-property",
        entry_ops=("dimension-property",),
        preview=_preview_dimension_property,
        apply=_apply_dimension_property_one,
    ),
    SheetsOpDescriptor(
        # LD-188 — the CELL STYLE family (fill / font / number-format), promoted out of
        # tests/sheets_write_harness.py::SheetsStyleWriter. ONE descriptor for both wire shapes
        # (`PUT …/style` for one range, `styles_batch_update` for N in one call), deliberately:
        # they write the same thing, classify as the same reserved op kinds, and are verified by
        # the same export style leg — the only difference is how many ranges ride one call,
        # which dispatch has no business caring about. It is the only family whose verification
        # leg was wired BEFORE it existed (STYLE_LEG_OP_KINDS), so registering it here is what
        # makes that pre-built gate fire.
        kind="style",
        request_type=(StyleWriteRequest, BatchStyleWriteRequest),
        write_kind="style",
        entry_ops=("style",),
        preview=_preview_style,
        apply=_apply_style_one,
    ),
    SheetsOpDescriptor(
        kind="merge",
        request_type=(MergeCells, UnmergeCells),
        write_kind="merge",
        entry_ops=("merge", "unmerge"),
        preview=_preview_merge,
        apply=_apply_merge_one,
    ),
    SheetsOpDescriptor(
        # LD-122 (add / copy / delete) + LD-187 (the PRESENTATION half — reorder / retitle /
        # hide-show). ONE descriptor, deliberately: the presentation fields change the tab set's
        # order, naming and visibility, which is what `WriteOpKind.TAB` already denotes, and
        # they are verified by the SAME v3 tab-query leg — so a second family row here would be
        # a near-duplicate of this one, differing in nothing that dispatch or the leg matrix
        # cares about. The `updateSheet` element they put on the wire is built by the one
        # shared builder the freeze family also uses (`requests.update_sheet_element`).
        kind="tab",
        request_type=(AddTab, CopyTab, DeleteTab,
                      ReorderTab, RetitleTab, SetTabVisibility),
        write_kind="tab",
        entry_ops=("add-tab", "copy-tab", "delete-tab") + TAB_PRESENTATION_OPS,
        preview=_preview_tab,
        apply=_apply_tab_one,
    ),
    SheetsOpDescriptor(
        # LD-186 — the FREEZE-PANES family. It shares the tab family's ENDPOINT
        # (`sheets_batch_update`) and its request-element seam, but not its descriptor, because
        # what verifies it is different: a tab op is verified by the v3 tab-set diff, a freeze
        # by the `metainfo` frozen counts (FREEZE_VERIFICATION_LEG — the read leg this issue
        # had to ship first, since the counts were surfaced nowhere). Registering it as its own
        # family is also what keeps the shared endpoint honest: the two legs are visibly
        # separate, so a later tab-presentation op extends this seam instead of forking it.
        kind="freeze-panes",
        request_type=(FreezePanes,),
        write_kind="freeze-panes",
        entry_ops=("freeze-panes",),
        preview=_preview_freeze,
        apply=_apply_freeze_one,
    ),
)

#: The request-side fallback family — an unrecognized / missing ``write_kind`` routes to the
#: value leg, exactly as the former ``getattr(request, "write_kind", "value")`` ``else`` did.
_VALUE_DEFAULT = next(d for d in OPS if d.kind == "value")
#: The entry-side fallback for a structural entry with an unrecognized ``op`` — the structural
#: leg (whose own unknown-op raise is preserved), matching the former ``_apply_one`` ``else``.
_STRUCTURAL_DEFAULT = next(d for d in OPS if d.kind == "structural")


def descriptor_for_request(request) -> SheetsOpDescriptor:
    """The descriptor for ``request`` — the **request-side** keying: match ``request.write_kind``
    against the registry (an unregistered / missing kind falls back to the value leg, exactly as
    the former ``_preview_one`` ``else``-is-value ladder did)."""
    wk = getattr(request, "write_kind", "value")
    for desc in OPS:
        if desc.write_kind == wk:
            return desc
    return _VALUE_DEFAULT


def descriptor_for_entry(entry) -> SheetsOpDescriptor:
    """The descriptor for a resolved plan ``entry`` — the **entry-side** keying: a structural /
    merge / tab entry (``entry.structural is not None``) routes on ``entry.structural["op"]``
    (an unrecognized op → the structural leg, whose own unknown-op raise is preserved); a
    value / dropdown-rule entry (``structural is None``) routes on ``entry.write_kind``."""
    if entry.structural is not None:
        op = entry.structural.get("op")
        for desc in OPS:
            if op in desc.entry_ops:
                return desc
        return _STRUCTURAL_DEFAULT
    wk = entry.write_kind
    for desc in OPS:
        if not desc.entry_ops and desc.write_kind == wk:
            return desc
    return _VALUE_DEFAULT


def classify(request) -> str:
    """The op-family ``kind`` for ``request`` (via the request-side keying)."""
    return descriptor_for_request(request).kind


def preview_dispatch(request, client, spreadsheet_token, merges=None) -> PlanEntry:
    """Preview ``request`` through its op's preview leg — the ONE request-side dispatch the
    former ``_preview_one`` ``write_kind`` / ``is_structural`` ladder collapses to."""
    return descriptor_for_request(request).preview(
        request, client, spreadsheet_token, merges=merges)


def apply_dispatch(entry, client, spreadsheet_token, expected_revision):
    """Apply one **resolved, fresh-revision-guarded** ``entry`` through its op's apply leg —
    the ONE entry-side dispatch the former ``_apply_one`` ``structural["op"]`` / ``write_kind``
    ladder collapses to (the shared compare-and-swap stays in :func:`_apply_one`)."""
    return descriptor_for_entry(entry).apply(
        entry, client, spreadsheet_token, expected_revision)
