"""Characterization + split guard for the ``sheets/requests`` package split (LD-224).

The 2,462-line ``sheets/requests.py`` was split into a ``sheets/requests/`` package along
its eight banner-delimited families, behind a re-export shim. The precedent and template is
``tests/test_write_model_package_split.py`` (the ``write/model`` split, LD-087); this guard
is the stricter sibling, because ``larkdocio.sheets.requests`` is a **consumer-reachable**
module (``tests/consumer_text.py`` enrols it by name, so ``help()`` lands on it).

Three invariants, all captured **from the baseline tag**
``refactor-baseline-2026-08-01-LD-224`` rather than hand-typed:

* **B1 — the full pre-split vocabulary still resolves** from ``larkdocio.sheets.requests``,
  all 100 names (65 public + 35 private), and each is the **same object** as the definition
  in the submodule it moved to (identity, not mere presence).
* **the public name set is EXACTLY the baseline's** — no name lost, and equally no name
  *gained*. The second half matters as much: ``consumer_text._public_names`` walks
  ``dir()`` and skips underscored names, so a submodule named without a leading underscore
  would silently enlarge the shipped-docstring corpus. Every new module is therefore
  ``_``-prefixed, and this assertion is what holds that.
* **the module docstring is byte-identical** — it is shipped prose a consumer reaches
  through ``help()``, and it is the one piece of text this refactor physically moves file.
  Pinned by SHA-256.

Written and passing (its vocabulary half) **before** the split, so it pins the pre-split
surface rather than whatever the split happened to produce.
"""
import hashlib
import importlib

import pytest

# --------------------------------------------------------------------------- #
# Baseline data — captured at refactor-baseline-2026-08-01-LD-224 with         #
#   python -c "import larkdocio.sheets.requests as m;                          #
#              print([n for n in dir(m) if not n.startswith('__')])"           #
# --------------------------------------------------------------------------- #

#: The re-exported third-party / sibling-module names. They are part of the surface
#: because ``dir()`` reports them, and the consumer-docstring corpus is built from
#: ``dir()`` — dropping them would shrink the corpus the dialect guard greps.
_INHERITED_IMPORTS = (
    "A1Cell", "LarkConfigError", "LarkDocIOError", "Optional", "WriteRange",
    "dataclass", "encode_dropdown_rule", "encode_formula", "encode_hyperlink",
    "encode_mention", "encode_multi_select", "encode_styled_runs",
    "normalize_expression", "parse_write_range", "re",
)

#: ``{name: the submodule that DEFINES it}`` for every name the split moves out of the
#: flat module. The value is what identity is asserted against (B1's "same object").
_DEFINED_IN = {
    # gate-leg certification (pre-split lines 43–169)
    "WriteOpKind": "_gates",
    "STYLE_LEG_OP_KINDS": "_gates",
    "MERGE_LEG_OP_KINDS": "_gates",
    "GateNotVerified": "_gates",
    "requires_style_leg": "_gates",
    "requires_merge_leg": "_gates",
    "effective_verify_style": "_gates",
    "certify_gate_legs": "_gates",
    # value / formula / rich / dropdown (172–457) — with its own posture mixin (AC4)
    "_CellWrite": "_cells",
    "ValueWriteRequest": "_cells",
    "FormulaWriteRequest": "_cells",
    "RichCellWriteRequest": "_cells",
    "DropdownRuleWriteRequest": "_cells",
    # structural (476–764)
    "_Structural": "_structural",
    "DimensionSpanError": "_structural",
    "InsertRowsAt": "_structural",
    "InsertColsAt": "_structural",
    "DeleteRows": "_structural",
    "DeleteCols": "_structural",
    "AppendDimension": "_structural",
    "AppendRowsWithValues": "_structural",
    "_reversed_span": "_structural",
    "_require_positive": "_structural",
    "_insert_shift": "_structural",
    "_delete_shift": "_structural",
    # dimension properties (784–1075)
    "_DimensionProperty": "_dimensions",
    "DIMENSION_PROPERTY_CONVENTION": "_dimensions",
    "MAX_DIMENSION_SPAN": "_dimensions",
    "DimensionPropertyError": "_dimensions",
    "SetRowProperties": "_dimensions",
    "SetColProperties": "_dimensions",
    "_dimension_properties": "_dimensions",
    "_dimension_band": "_dimensions",
    "_dimension_semantic": "_dimensions",
    "_property_preview": "_dimensions",
    # cell style + borders + word-wrap (1086–1651)
    "_StyleWrite": "_styles",
    "MIN_FONT_SIZE": "_styles",
    "MAX_FONT_SIZE": "_styles",
    "FONT_SIZE_REFUSAL_CODE": "_styles",
    "FONT_SIZE_REFUSAL_BODY": "_styles",
    "FONT_SIZE_LINE_SPACING": "_styles",
    "BORDER_TYPES": "_styles",
    "BORDER_CLEAR": "_styles",
    "BORDER_REFUSAL_CODE": "_styles",
    "BORDER_TYPE_REFUSAL_BODY": "_styles",
    "BORDER_COLOR_REFUSAL_BODY": "_styles",
    "BORDERS_ARE_ADDITIVE": "_styles",
    "WORD_WRAP_PROBED_FIELDS": "_styles",
    "WORD_WRAP_NOT_WRITABLE": "_styles",
    "StyleError": "_styles",
    "CellStyle": "_styles",
    "StyleSpan": "_styles",
    "StyleWriteRequest": "_styles",
    "BatchStyleWriteRequest": "_styles",
    "_HEX_COLOR_RE": "_styles",
    "_require_hex_color": "_styles",
    "_normalized_style_range": "_styles",
    "_style_preview": "_styles",
    # merge / unmerge (1670–1871)
    "MERGE_ALL": "_merge",
    "MERGE_VARIANTS_REFUSED": "_merge",
    "SUPPORTED_MERGE_TYPES": "_merge",
    "MERGE_TYPE_REFUSAL_CODE": "_merge",
    "MERGE_TYPE_REFUSAL_BODY": "_merge",
    "MERGE_VARIANTS_NOT_GATE_COVERED": "_merge",
    "MergeTypeError": "_merge",
    "MergeCells": "_merge",
    "UnmergeCells": "_merge",
    "_require_supported_merge_type": "_merge",
    "_region_of": "_merge",
    # tab CRUD (1882–1974)
    "_TabWrite": "_tabs",
    "AddTab": "_tabs",
    "CopyTab": "_tabs",
    "DeleteTab": "_tabs",
    "update_sheet_element": "_tabs",
    # freeze panes (1997–2182)
    "_FreezeWrite": "_freeze",
    "FreezeError": "_freeze",
    "FreezePanes": "_freeze",
    "_freeze_count": "_freeze",
    "_freeze_semantic": "_freeze",
    # tab presentation (2212–2460)
    "TabPresentationError": "_tab_presentation",
    "ReorderTab": "_tab_presentation",
    "RetitleTab": "_tab_presentation",
    "SetTabVisibility": "_tab_presentation",
    "_TabPresentation": "_tab_presentation",
    "_whole_index": "_tab_presentation",
}

#: The complete baseline vocabulary — 100 names.
_BASELINE_VOCABULARY = tuple(sorted(set(_DEFINED_IN) | set(_INHERITED_IMPORTS)))

#: The eight families + the two shared modules.
_SUBMODULES = tuple(sorted(set(_DEFINED_IN.values())))

#: SHA-256 of ``larkdocio.sheets.requests.__doc__`` at the baseline tag (1,707 chars).
_BASELINE_DOCSTRING_SHA256 = (
    "4fc613867905f74104b96d6d474df73ef9be50c53b445fb31cf806028f036e4c"
)


def _requests_module():
    import larkdocio.sheets.requests as m

    return m


# --------------------------------------------------------------------------- #
# Pre-split half — these pass at the baseline, and pin what must survive.      #
# --------------------------------------------------------------------------- #

def test_the_baseline_vocabulary_is_the_full_100_names():
    """The fixture data itself is the captured baseline, not a hand-typed subset."""
    assert len(_BASELINE_VOCABULARY) == 100, len(_BASELINE_VOCABULARY)


@pytest.mark.parametrize("name", _BASELINE_VOCABULARY)
def test_every_baseline_name_still_resolves(name):
    """B1 (first half) — no name importable from ``larkdocio.sheets.requests`` before the
    split stopped being importable from it after."""
    assert hasattr(_requests_module(), name), (
        f"{name} no longer importable from larkdocio.sheets.requests"
    )


def test_the_public_name_set_is_EXACTLY_the_baseline_set():
    """No name lost — and none GAINED. ``tests/consumer_text.py`` builds the shipped
    docstring corpus from this module's ``dir()`` minus underscored names, so a
    non-underscored submodule would quietly enrol a new docstring in the consumer
    corpus. Every split-out module is ``_``-prefixed; this is the assertion that holds it."""
    public = {n for n in dir(_requests_module()) if not n.startswith("_")}
    expected = {n for n in _BASELINE_VOCABULARY if not n.startswith("_")}
    assert public == expected, {
        "gained": sorted(public - expected),
        "lost": sorted(expected - public),
    }


def test_the_module_docstring_is_byte_identical_to_the_baseline():
    """The module docstring is shipped prose a consumer reaches via ``help()`` (it is
    enrolled by ``tests/consumer_text.py``), and it is the one text this refactor moves
    file. ZERO-DRIFT, pinned by digest."""
    doc = _requests_module().__doc__
    assert doc is not None
    digest = hashlib.sha256(doc.encode("utf-8")).hexdigest()
    assert digest == _BASELINE_DOCSTRING_SHA256, (
        "the sheets.requests module docstring changed — it is shipped consumer prose; "
        "LD-224 is behavior- and text-preserving"
    )


#: The names ``larkdocio.sheets`` itself re-exports out of this vocabulary, captured at the
#: baseline tag. The facade is deliberately narrower than the module — most of the
#: vocabulary is engine-internal and reaches callers through ``ops`` / ``write_apply``, not
#: through the top-level sheets facade.
_SHEETS_FACADE_OVERLAP = (
    "A1Cell", "FormulaWriteRequest", "GateNotVerified", "MERGE_VARIANTS_NOT_GATE_COVERED",
    "MergeTypeError", "SUPPORTED_MERGE_TYPES", "ValueWriteRequest", "WriteOpKind",
    "WriteRange", "certify_gate_legs", "effective_verify_style", "parse_write_range",
    "requires_merge_leg", "requires_style_leg",
)

#: ``larkdocio.sheets``' own public surface size at the baseline tag, plus the deliberate
#: additive widenings since (LD-331 added ``cell_fills`` / ``fill_disclosure_note`` /
#: ``FidelityUnavailable``, the per-cell fill disclosure; LD-346 added the ``tab_link``
#: submodule, its ``tab_url`` mint and the re-exported ``SHEETS_CELL_LINK_UI_ONLY`` negative;
#: LD-383 added the ``walk`` submodule and the six names of the spreadsheet walk's result
#: vocabulary — ``SpreadsheetRead`` / ``TabOutcome`` / ``TabSkip`` / ``TAB_READ`` /
#: ``TAB_SKIPPED`` and the ``skipped_tabs_disclosure`` note, exported because a caller that must
#: branch on a PARTIAL read needs them by name).
#: LD-405 added the ``read`` submodule and its three names — the URL-first ``read_spreadsheet``
#: / ``read_spreadsheet_markdown`` front door and the ``resolve_spreadsheet`` rule they share
#: (the twin of ``read_base`` / ``read_base_markdown``, which the walk had no equivalent of).
#: LD-447 added the ``media`` submodule — the in-cell image write (``put_image_in_sheet``, the
#: download-only ``SheetsMediaClient``, the ``InCellImage`` result and its error family). ONE
#: name, because what ``dir()`` gains is the submodule itself: the op is imported by its full
#: path, exactly as the drive folder-upload op is, and the read-facing facade re-exports no
#: write symbol.
#: LD-457 added TWO names — ``RefusalReason`` and ``REFUSAL_REASONS``, the refusal-reason
#: vocabulary a retry guard compares against. Signed-off growth of the same kind: the facade
#: already re-exports ``Refusal``, whose ``reason`` is a plain string, and a vocabulary that is
#: not importable is one every consumer hand-types (which is how a guard copied out of the
#: shipped guide came to compare against a spelling the wire never carries).
#: LD-583 added TWO names — ``CreatedSpreadsheet`` and ``CAPTURE_THE_TOKEN``, the create's own
#: typed answer and the orphan disclosure carried on it. Signed-off growth of exactly the kind
#: the two blocks above describe: the facade already re-exports ``SheetsWriteClient`` and its
#: teardown vocabulary, and a returned type nobody can import is one nobody can ``isinstance``
#: against — which is how round 5 came to hold a workbook it could not name (the orphaned
#: spreadsheet, ``dev/dogfood5/DIGEST.md`` § 3 #8, in the dev repo).
#: The pin guards against a name LOST to a refactor, not against growth an issue signed off on.
_SHEETS_FACADE_PUBLIC_NAMES = 118


def test_the_sheets_facade_is_unchanged_and_re_exports_the_same_objects():
    """B4/B5-adjacent — ``larkdocio.sheets`` exposes the same-sized public surface as at
    the baseline, and every name it re-exports out of this vocabulary resolves to the
    IDENTICAL object, so no shadow copy slipped in behind the shim."""
    import larkdocio.sheets as s

    m = _requests_module()
    public = {n for n in dir(s) if not n.startswith("_")}
    assert len(public) == _SHEETS_FACADE_PUBLIC_NAMES, sorted(public)

    overlap = tuple(n for n in _BASELINE_VOCABULARY if hasattr(s, n))
    assert overlap == _SHEETS_FACADE_OVERLAP, overlap
    for name in overlap:
        assert getattr(s, name) is getattr(m, name), f"{name} identity diverged"


# --------------------------------------------------------------------------- #
# Post-split half — RED before the split, GREEN after. The structural goal.    #
# --------------------------------------------------------------------------- #

def test_sheets_requests_is_a_package():
    """After the split ``larkdocio.sheets.requests`` is a PACKAGE (has ``__path__``)."""
    assert hasattr(_requests_module(), "__path__"), (
        "sheets.requests should be a package after the split"
    )


@pytest.mark.parametrize("submodule", _SUBMODULES)
def test_each_family_submodule_imports_cleanly(submodule):
    """AC4 — each banner-delimited family is its own module, plus the two shared ones."""
    assert importlib.import_module(f"larkdocio.sheets.requests.{submodule}") is not None


@pytest.mark.parametrize("name,submodule", sorted(_DEFINED_IN.items()))
def test_each_name_is_the_SAME_OBJECT_as_its_split_out_definition(name, submodule):
    """B1 (second half) — identity, not presence: the shim re-exports the very object the
    family module defines, so no duplicate definition can drift behind it."""
    mod = importlib.import_module(f"larkdocio.sheets.requests.{submodule}")
    assert getattr(_requests_module(), name) is getattr(mod, name), (
        f"{name} is not the same object as larkdocio.sheets.requests.{submodule}.{name}"
    )


def test_every_submodule_name_is_underscore_prefixed():
    """The mitigation the migration plan chose, asserted directly: the package's internals
    are private, so none of them can join the consumer-reachable ``dir()`` surface."""
    for submodule in _SUBMODULES:
        assert submodule.startswith("_"), submodule
