"""Characterization + split guard for the ``sheets/ops`` package split (LD-532).

The 3,019-line ``sheets/ops.py`` is split into a ``sheets/ops/`` package along its own
descriptor seams — one module per op family, mirroring the sibling ``sheets/requests/``
package — with the registry (:data:`~larkdocio.sheets.ops.OPS`), the dispatchers and the
engine loop staying in the package ``__init__``. The precedent and template is
``tests/test_sheets_requests_package_split.py`` (the ``sheets/requests`` split, LD-224).

Three invariants, all captured **from the baseline commit** rather than
hand-typed:

* **B1 — the full pre-split vocabulary still resolves** from ``larkdocio.sheets.ops``, all
  150 names (97 public + 53 private, both counts derived from the tuples below), and each
  name that MOVED is the **same object** as the definition in the submodule it moved to
  (identity, not mere presence). This is the invariant AC2 turns on: every symbol another
  module imports from ``larkdocio.sheets.ops`` must still import from
  ``larkdocio.sheets.ops``.
* **the public name set is EXACTLY the baseline's** — no name lost, and equally no name
  *gained*. The second half matters as much: ``consumer_text._public_names`` walks
  ``dir()`` and skips underscored names, so a submodule named without a leading underscore
  would silently enlarge the shipped-docstring corpus. Every new module is therefore
  ``_``-prefixed, and this assertion is what holds that.
* **the module docstring's PRE-CHECKLIST half is byte-identical** — pinned by SHA-256. The
  checklist half is deliberately excluded: it is contributor-facing law that AC1 requires
  the split to UPDATE (a checklist describing the old layout is a rotted guard), and its
  substance is already held by ``tests/test_sheets_registration_seam.py``. Pinning the half
  the split must not touch is a real constraint; pinning the half it must touch would only
  force this file to be edited by the change it is here to police.

Written and passing (its vocabulary, public-set and docstring halves) **before** the split,
so it pins the pre-split surface rather than whatever the split happened to produce.
"""
import hashlib
import importlib

import pytest

import larkdocio.sheets.ops as ops

# --------------------------------------------------------------------------- #
# Baseline data — captured at the baseline with                                  #
#   python -c "import larkdocio.sheets.ops as m;                               #
#              print(sorted(n for n in dir(m) if not n.startswith('__')))"     #
# --------------------------------------------------------------------------- #

_BASELINE_PUBLIC = (
    "A1Cell", "A1RangeError", "AddTab", "AppendDimension", "AppendRowsWithValues",
    "ApplyLog", "ApplyLogEntry", "BatchStyleWriteRequest", "COMPUTED_RENDER_OPTION",
    "Callable", "CopyTab", "DIMENSION_VERIFICATION", "DIMENSION_VERIFICATION_LEG",
    "DIMENSION_VERIFICATION_NOTE", "DeleteCols", "DeleteRows", "DeleteTab",
    "DropdownRuleWriteRequest", "EXPRESSION_RENDER_OPTION", "FREEZE_VERIFICATION",
    "FREEZE_VERIFICATION_LEG", "FREEZE_VERIFICATION_NOTE", "FormulaRenderOptionUnsupported",
    "FormulaWriteRequest", "FreezePanes", "FrozenPanes", "InsertColsAt", "InsertRowsAt",
    "LarkAPIError", "LarkDocIOError", "List", "MALFORMED_RANGE_CODE",
    "MENTION_VALIDATION_ACTIVE", "MENTION_VALIDATION_UNAVAILABLE", "MergeCells", "OPS",
    "Optional", "Plan", "PlanEntry", "Refusal", "ReorderTab", "RetitleTab",
    "RichCellWriteRequest", "STYLE_LEG_SCOPE", "STYLE_VERIFICATION",
    "STYLE_VERIFICATION_LEG", "STYLE_VERIFICATION_NOTE", "SetColProperties",
    "SetRowProperties", "SetTabVisibility", "SheetsOpDescriptor", "StyleWriteRequest",
    "TAB_PRESENTATION_OPS", "TAB_VERIFICATION", "TAB_VERIFICATION_LEG",
    "TAB_VERIFICATION_NOTE", "TYPE_CHECKING", "Tuple", "UnmergeCells", "ValueWriteRequest",
    "VerificationLeg", "WriteRange", "WriteWatch", "apply", "apply_dispatch", "classify",
    "classify_apply_exception", "combine_preview_notes", "dataclass",
    "descriptor_for_entry", "descriptor_for_request", "disposition_refusal", "dry_run",
    "equals_prefixed_note", "formula_expression", "formula_preview_note", "formula_record",
    "frozen_replacement_note", "gate_refusals", "hidden_dimension_note", "hidden_tab_note",
    "live_formula_cells", "matrix_shape", "no_merge_at_range_note",
    "out_of_bounds_dimension_note", "overwrites_live_formula_note", "parse_write_range",
    "preview_dispatch", "read_render", "replace", "retitle_join_note",
    "style_border_not_verifiable_note", "style_export_cost_note",
    "style_partial_merge_note", "tab_presentation_noop_note", "trim_pad_along",
    "used_extent_along",
)
_BASELINE_PRIVATE = (
    "_PAD_AXIS", "_PLAN_TOKEN", "_RemovedSnapshotFailed", "_STRUCTURAL_DEFAULT",
    "_VALUE_DEFAULT", "_apply_dimension_property_one", "_apply_dropdown_one",
    "_apply_formula_one", "_apply_freeze_one", "_apply_merge_one", "_apply_one",
    "_apply_structural_one", "_apply_style_one", "_apply_tab_one", "_apply_value_one",
    "_covered_cell_hit", "_did_you_mean", "_disposition_log_entry", "_entry_expression",
    "_entry_label", "_geometry_delta", "_has_formula_cell", "_has_structured_cell",
    "_intersecting_merges", "_is_malformed_range", "_live_formula_note",
    "_malformed_target_entry", "_merge_a1", "_merge_hit", "_normalize_merge",
    "_observe_tab", "_post_write_revision", "_preview_dimension_property",
    "_preview_dropdown", "_preview_formula", "_preview_freeze", "_preview_merge",
    "_preview_one", "_preview_structural", "_preview_style", "_preview_tab",
    "_preview_tab_presentation", "_preview_value", "_removed_dimension_range_a1",
    "_revision_of", "_shape_mismatch_entry", "_snapshot_removed_dimension",
    "_structured_cell_refusal", "_style_reply_revision", "_tab_pairs",
    "_trim_removed_values", "_unreadable_tab_refusal", "_validate_mention_ids",
)

#: The submodules the split introduces — the ONLY private names ``dir()`` may gain, because
#: importing a submodule binds its name on the parent package. Named after their
#: ``sheets/requests/`` twins where one exists; ``_formula`` / ``_dropdown`` have none (both
#: request classes live in ``requests/_cells.py``) and are named after their own op family.
_SUBMODULES = (
    "_cells", "_dimensions", "_dropdown", "_formula", "_freeze", "_merge", "_shared",
    "_structural", "_styles", "_tab_presentation", "_tabs",
)

#: The whole pre-split vocabulary, both halves. 150 names — the number is ``len()`` of the
#: two tuples above, never a literal, so it cannot disagree with them.
_BASELINE_VOCABULARY = _BASELINE_PUBLIC + _BASELINE_PRIVATE

#: The module docstring's pre-checklist half, SHA-256 at the baseline. The heading is the
#: same split point ``test_sheets_registration_seam._checklist`` uses, so the two files cut
#: the docstring in the same place.
_CHECKLIST_HEADING = "**Adding an op family — the registration checklist.**"
_DOCSTRING_HEAD_SHA = "f9fca53dd80a55832811b03f8aa55053299be0d8b76f78d2b67d38db328c659a"


def _docstring_head() -> str:
    doc = ops.__doc__
    assert _CHECKLIST_HEADING in doc, (
        "the registration checklist heading is gone from the module docstring — the "
        "docstring pin below would be measuring a different string")
    return doc[:doc.index(_CHECKLIST_HEADING)]


def test_b1_every_pre_split_name_still_resolves_on_the_package():
    """AC2's core: 150 names, one namespace. A name that stopped resolving here is a
    consumer's (or a sibling module's) ``ImportError``, whatever the package looks like."""
    missing = [name for name in _BASELINE_VOCABULARY if not hasattr(ops, name)]
    assert missing == [], (
        f"{len(missing)} name(s) no longer resolve on larkdocio.sheets.ops: {missing}")


def test_the_public_name_set_is_EXACTLY_the_baseline():
    """Both directions. A lost name breaks an importer; a GAINED public name enlarges the
    consumer-docstring corpus ``consumer_text._public_names`` builds off ``dir()``."""
    live = tuple(sorted(n for n in dir(ops) if not n.startswith("_")))
    assert live == tuple(sorted(_BASELINE_PUBLIC)), (
        f"lost: {sorted(set(_BASELINE_PUBLIC) - set(live))}; "
        f"gained: {sorted(set(live) - set(_BASELINE_PUBLIC))}")


def test_the_private_name_set_is_EXACTLY_the_baseline_TOO():
    """The private half is a real contract here, not housekeeping: the test estate imports
    private legs by name (``_RemovedSnapshotFailed``, ``_apply_structural_one``,
    ``_validate_mention_ids``) and ``SHEETS.md`` cites one of them as a dotted path. Only
    the submodule names the split introduces may be added, and they are listed."""
    live = {n for n in dir(ops) if n.startswith("_") and not n.startswith("__")}
    lost = sorted(set(_BASELINE_PRIVATE) - live)
    gained = sorted(live - set(_BASELINE_PRIVATE))
    assert lost == [], f"private names lost from larkdocio.sheets.ops: {lost}"
    assert all(name in _SUBMODULES for name in gained), (
        f"gained a private name that is not one of the split's own submodules: {gained}")


def test_validate_mention_ids_keeps_its_SHIPPED_DOTTED_PATH():
    """``SHEETS.md`` cites ``larkdocio.sheets.ops._validate_mention_ids`` by dotted path and
    ``tests/test_sheets_md_matrix.py`` holds the matrix against real code, so this one name is
    a documented address, not an internal detail."""
    assert callable(ops._validate_mention_ids)


def test_the_module_docstrings_pre_checklist_half_is_byte_identical():
    """The half the split may not touch. Shipped prose moved between files is exactly where
    a "while I was here" edit hides."""
    head = _docstring_head()
    assert hashlib.sha256(head.encode()).hexdigest() == _DOCSTRING_HEAD_SHA, (
        "the module docstring's pre-checklist half changed; a split is a pure move and this "
        "prose is not part of it")


# --------------------------------------------------------------------------- #
# B1's identity half — added once the submodules exist, so it asserts against   #
# the real tree rather than a plan. ``{name: the submodule that DEFINES it}``.   #
# --------------------------------------------------------------------------- #

_DEFINED_IN = {
    # _shared
    "MALFORMED_RANGE_CODE": "_shared",
    "VerificationLeg": "_shared",
    "_covered_cell_hit": "_shared",
    "_did_you_mean": "_shared",
    "_is_malformed_range": "_shared",
    "_post_write_revision": "_shared",
    "_revision_of": "_shared",
    "_tab_pairs": "_shared",
    "_unreadable_tab_refusal": "_shared",
    # _cells
    "_apply_value_one": "_cells",
    "_has_formula_cell": "_cells",
    "_has_structured_cell": "_cells",
    "_live_formula_note": "_cells",
    "_preview_value": "_cells",
    "_structured_cell_refusal": "_cells",
    # _formula
    "_apply_formula_one": "_formula",
    "_entry_expression": "_formula",
    "_preview_formula": "_formula",
    # _dropdown
    "_apply_dropdown_one": "_dropdown",
    "_preview_dropdown": "_dropdown",
    # _merge
    "_apply_merge_one": "_merge",
    "_merge_hit": "_merge",
    "_preview_merge": "_merge",
    "no_merge_at_range_note": "_merge",
    # _structural
    "_PAD_AXIS": "_structural",
    "_RemovedSnapshotFailed": "_structural",
    "_apply_structural_one": "_structural",
    "_geometry_delta": "_structural",
    "_intersecting_merges": "_structural",
    "_preview_structural": "_structural",
    "_removed_dimension_range_a1": "_structural",
    "_snapshot_removed_dimension": "_structural",
    "_trim_removed_values": "_structural",
    "out_of_bounds_dimension_note": "_structural",
    # _dimensions
    "DIMENSION_VERIFICATION": "_dimensions",
    "DIMENSION_VERIFICATION_LEG": "_dimensions",
    "DIMENSION_VERIFICATION_NOTE": "_dimensions",
    "_apply_dimension_property_one": "_dimensions",
    "_preview_dimension_property": "_dimensions",
    "hidden_dimension_note": "_dimensions",
    # _freeze
    "FREEZE_VERIFICATION": "_freeze",
    "FREEZE_VERIFICATION_LEG": "_freeze",
    "FREEZE_VERIFICATION_NOTE": "_freeze",
    "_apply_freeze_one": "_freeze",
    "_preview_freeze": "_freeze",
    "frozen_replacement_note": "_freeze",
    # _styles
    "STYLE_LEG_SCOPE": "_styles",
    "STYLE_VERIFICATION": "_styles",
    "STYLE_VERIFICATION_LEG": "_styles",
    "STYLE_VERIFICATION_NOTE": "_styles",
    "_apply_style_one": "_styles",
    "_merge_a1": "_styles",
    "_preview_style": "_styles",
    "_style_reply_revision": "_styles",
    "style_border_not_verifiable_note": "_styles",
    "style_export_cost_note": "_styles",
    "style_partial_merge_note": "_styles",
    # _tab_presentation
    "TAB_PRESENTATION_OPS": "_tab_presentation",
    "_preview_tab_presentation": "_tab_presentation",
    "hidden_tab_note": "_tab_presentation",
    "retitle_join_note": "_tab_presentation",
    "tab_presentation_noop_note": "_tab_presentation",
    # _tabs
    "TAB_VERIFICATION": "_tabs",
    "TAB_VERIFICATION_LEG": "_tabs",
    "TAB_VERIFICATION_NOTE": "_tabs",
    "_apply_tab_one": "_tabs",
    "_observe_tab": "_tabs",
    "_preview_tab": "_tabs",
}


@pytest.mark.parametrize("submodule", _SUBMODULES)
def test_every_submodule_imports_on_its_own(submodule):
    """The DAG arm: each family module imports without the package ``__init__`` having run
    first. A module that only imports as a side effect of ``__init__`` is a cycle waiting for
    the first consumer who reaches for the submodule directly."""
    assert importlib.import_module(f"larkdocio.sheets.ops.{submodule}") is not None


def test_b1_identity_every_moved_name_is_the_SAME_OBJECT_as_its_definition():
    """Presence is not enough: a re-export that rebuilt the value rather than binding the one
    definition would pass ``hasattr`` and still be a second copy. Identity is what makes the
    re-export block a pure address, and it is what a caller comparing ``is`` relies on."""
    wrong = []
    for name, submodule in sorted(_DEFINED_IN.items()):
        module = importlib.import_module(f"larkdocio.sheets.ops.{submodule}")
        if getattr(ops, name) is not getattr(module, name):
            wrong.append(f"{name} (declared in {submodule})")
    assert wrong == [], wrong


def test_the_definition_MAP_covers_every_name_that_left_the_flat_module():
    """Anti-vacuity, both ways: every mapped name is in the pinned vocabulary, and every name
    the package no longer defines in ``__init__`` is mapped. A name that quietly slipped out of
    the map would make the identity test above blind to exactly that name."""
    assert set(_DEFINED_IN) <= set(_BASELINE_VOCABULARY), (
        sorted(set(_DEFINED_IN) - set(_BASELINE_VOCABULARY)))
    init_own = {
        name for name in _BASELINE_VOCABULARY
        if getattr(getattr(ops, name), "__module__", None) == "larkdocio.sheets.ops"
    }
    unmapped = sorted(
        name for name in _BASELINE_VOCABULARY
        if name not in _DEFINED_IN and name not in init_own
        and getattr(getattr(ops, name), "__module__", "").startswith("larkdocio.sheets.ops."))
    assert unmapped == [], unmapped
