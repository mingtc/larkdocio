"""larkdocio.sheets.requests — the findings-agnostic write-request family.

Extracted from ``write_apply.py`` (behavior-preserving): the write op-kind vocabulary +
fidelity-leg triggers (``WriteOpKind`` / ``requires_style_leg`` / ``effective_verify_style``
/ ``certify_gate_legs`` / ``GateNotVerified``) and the typed write-request objects
across ten families — value / formula / rich / dropdown-rule (the range/cell-targeted family
sharing the :class:`_CellWrite` base), structural dimension writes (``_Structural`` mixin),
row/column dimension PROPERTIES — height / width / hide-show (``_DimensionProperty`` mixin),
CELL STYLE — fill / font / number-format over one range or N in one call (``_StyleWrite``
mixin, with :class:`CellStyle` carrying the validated payload), merge / unmerge, tab
add/copy/delete + tab PRESENTATION — reorder / retitle / hide-show (``_TabWrite`` mixin, the
``_TabPresentation`` sub-mixin), and FREEZE PANES (``_FreezeWrite`` mixin — ``updateSheet``
objects riding the tab family's own already-shipped ``sheets_batch_update`` endpoint).

Both ``updateSheet`` families build their wire element through the ONE
:func:`update_sheet_element` builder, so the seam is shared rather than forked.

**Findings-agnostic**: a request is only a target + a payload — the library learns NO
consumer findings / approval / status vocabulary — a constraint the test suite guards. Each
request carries its own dispatch discriminators — ``write_kind`` (the request-side preview
key) and, for structural/dimension-property/style/merge/tab/freeze, its
``descriptor()["op"]`` (the entry-side apply key) —
which the :mod:`larkdocio.sheets.ops` registry reads off to dispatch. Nothing here opens a
socket.
"""
import re
from dataclasses import dataclass
from typing import Optional

from larkdocio.errors import LarkConfigError, LarkDocIOError
from larkdocio.sheets.formula import encode_formula, normalize_expression
from larkdocio.sheets.rich_encode import (
    encode_dropdown_rule,
    encode_hyperlink,
    encode_mention,
    encode_multi_select,
    encode_styled_runs,
)
from larkdocio.sheets.write_range import A1Cell, WriteRange, parse_write_range

# --------------------------------------------------------------------------- #
# The re-export shim (LD-224). This module was a flat 2,462-line file         #
# until the split; every name it carried then is re-exported here,            #
# resolving to the SAME object its family module defines — so all eighteen    #
# importers keep their import statements verbatim.                            #
# tests/test_sheets_requests_package_split.py pins the full baseline          #
# vocabulary (100 names) and the identity of every one of them.               #
#                                                                             #
# The imports ABOVE are re-exports too: they were importable from this        #
# module before the split, so dropping them here would silently shrink the    #
# surface `help()` (and the `dir()`-built docstring corpus) reaches.          #
# --------------------------------------------------------------------------- #

from ._gates import (
    WriteOpKind,
    STYLE_LEG_OP_KINDS,
    MERGE_LEG_OP_KINDS,
    GateNotVerified,
    requires_style_leg,
    requires_merge_leg,
    effective_verify_style,
    certify_gate_legs,
)

from ._cells import (
    _CellWrite,
    ValueWriteRequest,
    FormulaWriteRequest,
    RichCellWriteRequest,
    DropdownRuleWriteRequest,
)

from ._structural import (
    DimensionSpanError,
    _Structural,
    InsertRowsAt,
    InsertColsAt,
    DeleteRows,
    DeleteCols,
    AppendDimension,
    AppendRowsWithValues,
    _reversed_span,
    _require_positive,
    _insert_shift,
    _delete_shift,
)

from ._dimensions import (
    DIMENSION_PROPERTY_CONVENTION,
    MAX_DIMENSION_SPAN,
    DimensionPropertyError,
    _DimensionProperty,
    _dimension_properties,
    _dimension_band,
    _dimension_semantic,
    SetRowProperties,
    SetColProperties,
    _property_preview,
)

from ._styles import (
    MIN_FONT_SIZE,
    MAX_FONT_SIZE,
    FONT_SIZE_REFUSAL_CODE,
    FONT_SIZE_REFUSAL_BODY,
    FONT_SIZE_LINE_SPACING,
    _HEX_COLOR_RE,
    BORDER_TYPES,
    BORDER_CLEAR,
    BORDER_REFUSAL_CODE,
    BORDER_TYPE_REFUSAL_BODY,
    BORDER_COLOR_REFUSAL_BODY,
    BORDERS_ARE_ADDITIVE,
    WORD_WRAP_PROBED_FIELDS,
    WORD_WRAP_NOT_WRITABLE,
    StyleError,
    _require_hex_color,
    CellStyle,
    _normalized_style_range,
    _StyleWrite,
    StyleSpan,
    StyleWriteRequest,
    BatchStyleWriteRequest,
    _style_preview,
)

from ._merge import (
    MERGE_ALL,
    MERGE_VARIANTS_REFUSED,
    SUPPORTED_MERGE_TYPES,
    MERGE_TYPE_REFUSAL_CODE,
    MERGE_TYPE_REFUSAL_BODY,
    MERGE_VARIANTS_NOT_GATE_COVERED,
    MergeTypeError,
    _require_supported_merge_type,
    _region_of,
    MergeCells,
    UnmergeCells,
)

from ._tabs import (
    _TabWrite,
    AddTab,
    CopyTab,
    DeleteTab,
    update_sheet_element,
)

from ._freeze import (
    FreezeError,
    _FreezeWrite,
    _freeze_count,
    _freeze_semantic,
    FreezePanes,
)

from ._tab_presentation import (
    TabPresentationError,
    _TabPresentation,
    _whole_index,
    ReorderTab,
    RetitleTab,
    SetTabVisibility,
)
