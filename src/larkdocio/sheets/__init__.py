"""larkdocio.sheets — the Sheets surface: a values→Markdown **reader** (L1) + a plan-gated
**write** engine.

Built as a ladder parallel to ``write/``. The **read** side (L1) delivers a
standalone Sheets values→Markdown reader plus an opt-in deep-read of docx embedded sheets,
on the same disciplined surface as the docx reader (throttled transport, typed errors,
byte-identical determinism, a credential-gated live canary); schema-faithful L2 fidelity
(the xlsx-export style/format reader, :mod:`larkdocio.sheets.export_reader`) adds per-cell
bold/italic/fill/numFmt. The **write** side is a block-/range-level, plan-gated
apply engine — the sheets parity of the docx :mod:`larkdocio.write` engine.

Mostly a **client** package, not a docx block handler — the per-block registry
(``larkdocio.blocks``) is untouched.

**Read surface.** The read client + its typed response models
(:mod:`larkdocio.sheets.client`, :mod:`larkdocio.sheets.models`); used-range
discovery + the trailing-null trim (:mod:`larkdocio.sheets.extent`);
value→Markdown cell rendering (:mod:`larkdocio.sheets.render`); table assembly +
the merge join (:mod:`larkdocio.sheets.table`) — one titled GFM table per tab, merged regions
as anchor-value-plus-blanks; and the opt-in docx embedded-sheet deep-read **bridge**
(:mod:`larkdocio.sheets.embed`); plus the L2 export-fidelity reader
(:mod:`larkdocio.sheets.export_reader`).

**Write surface.** A **non-forgeable** ``Plan`` — produced ONLY by the mandatory
``dry_run`` previewer — → ``apply``, with a ``revision`` compare-and-swap ``STALE_SHEET`` guard,
findings-agnostic requests, and a JSON-serializable apply-log. **Ten** write-request families
(value / formula / rich-cell / dropdown-rule / structural / dimension-property / style /
merge·unmerge / tab / freeze-panes) flow through the ONE gate — the arity is
:data:`larkdocio.sheets.ops.OPS`'s, not a hand-kept number, and
``tests/test_sheets_registration_seam.py`` holds this sentence to it.
The write engine lives under :mod:`larkdocio.sheets.write_apply` (a thin
facade over :mod:`larkdocio.sheets.requests` / :mod:`~larkdocio.sheets.merge_geometry` /
:mod:`~larkdocio.sheets.plan` / :mod:`~larkdocio.sheets.ops` — the op-descriptor registry,
the write client + A1 model (:mod:`larkdocio.sheets.write_client`,
:mod:`~larkdocio.sheets.write_range`), and the rich-cell / dropdown-rule encoders
(:mod:`larkdocio.sheets.rich_encode`). ``SHEETS.md`` — in the source repository, not in the wheel —
is the living capability matrix; a wheel-only reader gets the same answer from
``larkdocio.capabilities()`` and ``larkdocio.guide()``.

**Verifying a write.** :mod:`larkdocio.sheets.verify` is the read-back comparator
(:func:`~larkdocio.sheets.verify.values_equivalent`) — the sheets parity of the docx side's
compose-equivalence recipe, because a sheet's numeric read-back is normalized (``18.0`` reads
back as ``18``) and a string comparison therefore phantom-diffs. Pure comparison: no client,
no credentials, no transport.
"""

from larkdocio.sheets.client import (
    DEFAULT_MAX_READS_PER_SEC,
    SheetsReadClient,
)
from larkdocio.sheets.embed import (
    deep_read_embedded_sheet,
    split_compound_token,
)
from larkdocio.sheets.extent import (
    UsedRange,
    a1_column_to_number,
    column_number_to_a1,
    declared_grid_range,
    trim_trailing_nulls,
    used_range_a1,
)
from larkdocio.sheets.models import (
    FILTER_ACTIVE,
    FILTER_NONE,
    FILTER_NOT_READ,
    FILTER_UNAVAILABLE,
    FROZEN_ACTIVE,
    FROZEN_NONE,
    FROZEN_NOT_READ,
    FROZEN_UNAVAILABLE,
    FilterColumn,
    FilterCondition,
    FrozenPanes,
    Merge,
    SheetFilter,
    SheetTab,
    SpreadsheetMeta,
    ValueRange,
    parse_frozen_panes,
)
from larkdocio.sheets.export_reader import (
    ExportedCell,
    ExportedSheet,
    ParsedWorkbook,
    SheetsExportReader,
    XlsxParseError,
    exported_by_sheet_id,
    parse_xlsx,
)
from larkdocio.common.url import SHEETS_CELL_LINK_UI_ONLY
from larkdocio.sheets.render import render_cell
from larkdocio.sheets.tab_link import tab_url
from larkdocio.sheets.write_client import (
    CAPTURE_THE_TOKEN,
    FILE_ALREADY_DELETED_CODE,
    SPREADSHEET_GONE_CODE,
    CreatedSpreadsheet,
    SheetsWriteClient,
    normalize_write_range,
    spreadsheet_is_gone,
)
from larkdocio.sheets.write_range import (
    MAX_A1_COLUMN,
    A1Cell,
    WriteRange,
    parse_write_range,
    write_range_from_used_range,
)
from larkdocio.sheets.write_apply import (
    REFUSAL_REASONS,
    ApplyLog,
    ApplyLogEntry,
    FormulaExpressionError,
    FormulaWriteRequest,
    GateNotVerified,
    Plan,
    PlanEntry,
    Refusal,
    RefusalReason,
    ValueWriteRequest,
    WriteOpKind,
    apply,
    certify_gate_legs,
    dry_run,
    effective_verify_style,
    requires_merge_leg,
    requires_style_leg,
)
from larkdocio.sheets.requests import (
    MERGE_VARIANTS_NOT_GATE_COVERED,
    SUPPORTED_MERGE_TYPES,
    MergeTypeError,
)
from larkdocio.sheets.rich_encode import DROPDOWN_COLORS_NOT_READ_BACK
from larkdocio.sheets.verify import (
    NUMERIC_READ_BACK_NORMALIZED,
    cells_equivalent,
    value_differences,
    values_equivalent,
)
from larkdocio.sheets.table import (
    FidelityUnavailable,
    cell_fills,
    escape_cell,
    fill_disclosure_note,
    filter_disclosure_note,
    matrix_to_gfm_table,
    merge_covered_cells,
    render_matrix,
    render_spreadsheet,
    render_tab,
    tab_heading,    skipped_tabs_disclosure,
)
from larkdocio.sheets.read import (
    read_spreadsheet,
    read_spreadsheet_markdown,
    resolve_spreadsheet,
)
from larkdocio.sheets.walk import (
    TAB_READ,
    TAB_SKIPPED,
    SpreadsheetRead,
    TabOutcome,
    TabSkip,
)

__all__ = [
    "DEFAULT_MAX_READS_PER_SEC",
    "SheetsReadClient",
    "deep_read_embedded_sheet",
    "split_compound_token",
    "UsedRange",
    "a1_column_to_number",
    "column_number_to_a1",
    "declared_grid_range",
    "trim_trailing_nulls",
    "used_range_a1",
    "Merge",
    "SheetTab",
    "SpreadsheetMeta",
    "ValueRange",
    "FILTER_ACTIVE",
    "FILTER_NONE",
    "FILTER_NOT_READ",
    "FILTER_UNAVAILABLE",
    "FilterColumn",
    "FilterCondition",
    "SheetFilter",
    # LD-186 — the FROZEN-panes read leg: the same additive, deliberate widening as the
    # filter-state slugs directly above. The four state slugs are what a consumer BRANCHES on
    # (`not-read` vs `none` vs `active` vs `unavailable`) and a state machine whose constants
    # are private forces the consumer to hard-code string literals; `FrozenPanes` and
    # `parse_frozen_panes` live in `models` beside `SheetTab` / `SheetFilter`, which this
    # facade already re-exports, so omitting them would hand a consumer half of one module.
    "FROZEN_ACTIVE",
    "FROZEN_NONE",
    "FROZEN_NOT_READ",
    "FROZEN_UNAVAILABLE",
    "FrozenPanes",
    "parse_frozen_panes",
    "render_cell",
    # The one click-proven mintable spreadsheet deep link — a pure, offline string function
    # whose tenant host is an INPUT (read off the sheet's own URL), never the API domain.
    "tab_url",
    # The loud cell-link negative, authored once in larkdocio.common.url and re-exported here
    # so a consumer reading the Sheets surface meets it beside tab_url.
    "SHEETS_CELL_LINK_UI_ONLY",
    "ExportedCell",
    "ExportedSheet",
    "ParsedWorkbook",
    "SheetsExportReader",
    "XlsxParseError",
    "exported_by_sheet_id",
    "parse_xlsx",
    "SheetsWriteClient",
    # LD-583 — the create's typed answer, and the orphan disclosure it carries.
    "CreatedSpreadsheet",
    "CAPTURE_THE_TOKEN",
    "normalize_write_range",
    # The FILE-lifecycle teardown vocabulary (LD-176): the two already-gone codes and the one
    # predicate over them. Re-exported for the same reason the filter-state slugs are — it is
    # what a consumer BRANCHES on inside a `finally`, and the client it belongs to already
    # rides this facade.
    "SPREADSHEET_GONE_CODE",
    "FILE_ALREADY_DELETED_CODE",
    "spreadsheet_is_gone",
    "MAX_A1_COLUMN",
    "A1Cell",
    "WriteRange",
    "parse_write_range",
    "write_range_from_used_range",
    "ApplyLog",
    "ApplyLogEntry",
    "FormulaExpressionError",
    "FormulaWriteRequest",
    "GateNotVerified",
    "Plan",
    "PlanEntry",
    "Refusal",
    # The refusal-reason vocabulary a retry guard compares against — exported so nobody
    # hand-types a spelling (`reason` is a plain string; only the wire value matches).
    "RefusalReason",
    "REFUSAL_REASONS",
    "ValueWriteRequest",
    "WriteOpKind",
    "apply",
    "certify_gate_legs",
    "dry_run",
    "effective_verify_style",
    "requires_merge_leg",
    "requires_style_leg",
    "FidelityUnavailable",
    "cell_fills",
    "escape_cell",
    "fill_disclosure_note",
    "filter_disclosure_note",
    "matrix_to_gfm_table",
    "merge_covered_cells",
    "render_matrix",
    "render_spreadsheet",
    "render_tab",
    "skipped_tabs_disclosure",
    "tab_heading",
    # LD-405 — the walk's FRONT DOOR: the URL-first one-call twin of `read_base`, plus its
    # Markdown twin and the resolver they share. A consumer holding a link should not have to
    # know that the entry point is a client METHOD wanting a TOKEN.
    "read_spreadsheet",
    "read_spreadsheet_markdown",
    "resolve_spreadsheet",
    # LD-383 — the spreadsheet walk's result vocabulary. A caller that must branch on a
    # PARTIAL read (some tab was refused) needs the types by name, not by tuple position.
    "TAB_READ",
    "TAB_SKIPPED",
    "SpreadsheetRead",
    "TabOutcome",
    "TabSkip",
    # LD-190 — the three shipped-op truth riders. The two loud statements ride the facade for
    # the same reason the filter-state slugs do: a consumer BRANCHES on the limit (there is no
    # colors read-back; there is no MERGE_ROWS) and the statement is the one authored copy of
    # it. `values_equivalent` is the sheets parity of docx's compose-equivalence comparator —
    # the verification a self-check needs, and pure (no client, no credentials).
    "DROPDOWN_COLORS_NOT_READ_BACK",
    "MERGE_VARIANTS_NOT_GATE_COVERED",
    "MergeTypeError",
    "NUMERIC_READ_BACK_NORMALIZED",
    "SUPPORTED_MERGE_TYPES",
    "cells_equivalent",
    "value_differences",
    "values_equivalent",
]
