"""larkdocio.sheets.write_apply — the plan-gated Sheets write apply engine (thin facade).

The Sheets **write surface**: a block-/range-level, **plan-gated** apply engine — the sheets
parity of the docx :mod:`larkdocio.write` engine. A **non-forgeable** :class:`Plan` (a
module-private construction token; **no** ``Plan.from_dict``) is produced ONLY by the mandatory
:func:`dry_run` previewer, and :func:`apply` accepts a :class:`Plan` and nothing else — so there
is no direct-apply path. Each write re-reads ``metainfo.properties.revision`` immediately before
it and refuses a typed ``STALE_SHEET`` (no write) if it advanced (the compare-and-swap staleness
anchor), while the rest of the batch still applies. **Ten** findings-agnostic write-request
families (value / formula / rich-cell / dropdown-rule / structural / dimension-property /
style / merge·unmerge / tab / freeze-panes) flow through the ONE gate. The arity is
:data:`larkdocio.sheets.ops.OPS`'s — every family named here is a registered op kind, plus the
rich-cell request family folded into ``value`` — and it is guarded, not typed twice
(``tests/test_sheets_registration_seam.py``; the count word in this very sentence was once
``**Sevenfindings-agnostic**``, a corrupted marker that hid a stale six-vs-seven claim from
every reader for two releases).

**Formulas.** A formula is its own family
(:class:`~larkdocio.sheets.requests.FormulaWriteRequest`), because it is the one write whose
precondition and verification read by **render mode**: the precondition compares the
**EXPRESSION** (``valueRenderOption=Formula``) and the post-write verification reads the
**COMPUTED** value (``UnformattedValue``). A ``=``-prefixed **plain string** never evaluates —
Lark has no ``valueInputOption`` — so it earns a loud dry-run note
(:data:`~larkdocio.sheets.formula.INERT_STRING_NOTE`) instead of silently shipping inert text.
See :mod:`larkdocio.sheets.formula` for the live probe evidence.

**Staleness has TWO TIERS and tier 1 is never silently off.** Some spreadsheets report
a constant ``0`` (or no) ``revision``, which made the compare-and-swap compare ``0 == 0`` and
no-op invisibly. Every plan (and its dry-run output, and every apply-log entry) now carries
``revision_guard`` — ``"active"`` / ``"unavailable"`` with the WHY — while the **value
precondition** stays the always-on second tier, disclosed per entry as ``value_precondition``.
See :mod:`larkdocio.sheets.plan` for the full contract.

**Module layout.** This module was a 2,057-line god module; it is now a
thin facade re-exporting the public surface from four concern modules — **unchanged import
paths**, so ``from larkdocio.sheets.write_apply import …`` still resolves every historical name:

* :mod:`larkdocio.sheets.requests` — the write-request families + the ``WriteOpKind`` / gate-leg
  vocabulary (the value/rich/dropdown trio share a ``_CellWrite`` base; structural / tab use the
  ``_Structural`` / ``_TabWrite`` mixins, tab PRESENTATION the ``_TabPresentation`` sub-mixin,
  and both ``updateSheet`` families the one ``update_sheet_element`` builder);
* :mod:`larkdocio.sheets.merge_geometry` — the merge-fate model (``predict_merge_fate``);
* :mod:`larkdocio.sheets.plan` — the ``Plan`` / ``PlanEntry`` / ``ApplyLog`` / ``Refusal`` value
  objects;
* :mod:`larkdocio.sheets.ops` — the op-descriptor registry (``OPS``) the engine dispatches from,
  plus :func:`dry_run` / :func:`apply`.
"""
from larkdocio.sheets.merge_geometry import (
    MergeFate,
    predict_merge_fate,
    predict_merge_fates,
)
from larkdocio.sheets.formula import (
    COMPUTED_RENDER_OPTION,
    EXPRESSION_RENDER_OPTION,
    INERT_STRING_NOTE,
    FormulaExpressionError,
    FormulaRenderOptionUnsupported,
    encode_formula,
    formula_expression,
)
from larkdocio.sheets.requests import (
    AddTab,
    BORDERS_ARE_ADDITIVE,
    BORDER_CLEAR,
    BORDER_COLOR_REFUSAL_BODY,
    BORDER_REFUSAL_CODE,
    BORDER_TYPES,
    BORDER_TYPE_REFUSAL_BODY,
    BatchStyleWriteRequest,
    CellStyle,
    FONT_SIZE_LINE_SPACING,
    FONT_SIZE_REFUSAL_BODY,
    FONT_SIZE_REFUSAL_CODE,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    WORD_WRAP_NOT_WRITABLE,
    WORD_WRAP_PROBED_FIELDS,
    StyleError,
    StyleSpan,
    StyleWriteRequest,
    AppendDimension,
    AppendRowsWithValues,
    CopyTab,
    DIMENSION_PROPERTY_CONVENTION,
    DeleteCols,
    DeleteRows,
    DeleteTab,
    DimensionPropertyError,
    FreezeError,
    FreezePanes,
    DimensionSpanError,
    DropdownRuleWriteRequest,
    FormulaWriteRequest,
    GateNotVerified,
    InsertColsAt,
    InsertRowsAt,
    MAX_DIMENSION_SPAN,
    MERGE_LEG_OP_KINDS,
    MergeCells,
    ReorderTab,
    RetitleTab,
    RichCellWriteRequest,
    STYLE_LEG_OP_KINDS,
    SetColProperties,
    SetRowProperties,
    SetTabVisibility,
    TabPresentationError,
    UnmergeCells,
    ValueWriteRequest,
    WriteOpKind,
    certify_gate_legs,
    effective_verify_style,
    requires_merge_leg,
    requires_style_leg,
    update_sheet_element,
)
from larkdocio.sheets.disposition import (
    ENTRY_SCOPED,
    FILE_LIFECYCLE_SEAMS,
    READ_SEAMS,
    SYSTEMIC,
    WRITE_SEAMS,
    Disposition,
    WriteWatch,
    classify_apply_exception,
)
from larkdocio.sheets.plan import (
    MENTION_VALIDATION_ACTIVE,
    MENTION_VALIDATION_NOT_APPLICABLE,
    MENTION_VALIDATION_UNAVAILABLE,
    REVISION_GUARD_ACTIVE,
    REVISION_GUARD_UNAVAILABLE,
    REFUSAL_REASONS,
    VALUE_PRECONDITION_ENFORCED,
    VALUE_PRECONDITION_NONE,
    ApplyLog,
    ApplyLogEntry,
    Plan,
    PlanEntry,
    Refusal,
    RefusalReason,
    mention_validation_semantics,
    revision_guard_semantics,
    revision_guard_status,
)
from larkdocio.sheets.ops import (
    DIMENSION_VERIFICATION_LEG,
    STYLE_VERIFICATION_LEG,
    STYLE_VERIFICATION_NOTE,
    FREEZE_VERIFICATION_LEG,
    TAB_VERIFICATION_LEG,
    OPS,
    SheetsOpDescriptor,
    apply,
    dry_run,
)
