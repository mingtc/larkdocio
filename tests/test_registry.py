# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""Registration completeness tests.

Background: an earlier audit found a latent bug where the divider handler
(type 22) was imported only inside ``get_registry()`` (a lazy
``import larkdocio.blocks.divider``), not by the eager ``from . import ...``
block in ``larkdocio/blocks/__init__.py``. That made the registry incomplete
immediately after ``import larkdocio.blocks`` until something called
``get_registry()`` — a call-order dependence a registration guard catches.

That bug is FIXED: every handler module (divider included) is imported eagerly
in ``larkdocio/blocks/__init__.py``, so the registry is complete right after
``import larkdocio.blocks`` without ever calling ``get_registry()``. These are
REGRESSION GUARDS that assert exactly that fixed state and keep it that way.
"""
import importlib
import sys

# Every block type the tool intends to support (one registered handler each).
# Verified against the handlers in larkdocio/blocks/*.py and the official Feishu
# enum as documented in BLOCK_TYPES.md.
EXPECTED_SUPPORTED_TYPES = {
    1,                              # page
    2,                              # text
    3, 4, 5, 6, 7, 8, 9, 10, 11,    # heading1-9
    12,                             # bullet
    13,                             # ordered
    14,                             # code
    15,                             # quote
    16,                             # equation
    17,                             # todo
    18,                             # bitable (embedded-Base placeholder — LD-048)
    19,                             # callout
    22,                             # divider
    23,                             # file
    24,                             # grid
    25,                             # grid_column
    26,                             # iframe (url-as-link — LD-047)
    27,                             # image
    30,                             # sheet (embedded-Sheet placeholder — LD-048)
    31,                             # table
    32,                             # table_cell
    33,                             # view (transparent wrapper — LD-040)
    34,                             # quote_container
    40,                             # add_ons (mermaid)
    43,                             # board
    44,                             # agenda (transparent wrapper — LD-046)
    45,                             # agenda_item (transparent wrapper — LD-046)
    46,                             # agenda_item_title (title from elements — LD-046)
    47,                             # agenda_item_content (transparent wrapper — LD-046)
    49,                             # source_synced
    50,                             # reference_synced
    53,                             # reference_base (embedded-Base named-view placeholder — LD-048)
}


def _fresh_registry_after_import_only():
    """Re-import larkdocio.blocks from scratch and return BLOCK_REGISTRY WITHOUT
    ever calling get_registry(). Drops cached block submodules first so the
    eager import side effects run again."""
    for name in list(sys.modules):
        if name == "larkdocio.blocks" or name.startswith("larkdocio.blocks."):
            del sys.modules[name]
    mod = importlib.import_module("larkdocio.blocks")
    return mod.BLOCK_REGISTRY, mod


def test_divider_registered_eagerly():
    """Regression guard: divider (22) must register eagerly on import — the
    hardening fix removed the lazy get_registry()-only registration."""
    registry, _ = _fresh_registry_after_import_only()
    assert 22 in registry, (
        "Divider (type 22) is not registered immediately after "
        "`import larkdocio.blocks` — it only registers when get_registry() is "
        "called. Make larkdocio/blocks/__init__.py import the divider module "
        "eagerly like the others."
    )


def test_all_supported_types_registered_eagerly():
    """Full completeness guard: every supported type present right after import,
    without calling get_registry()."""
    registry, _ = _fresh_registry_after_import_only()
    missing = EXPECTED_SUPPORTED_TYPES - set(registry)
    assert not missing, (
        f"Block types {sorted(missing)} are not registered immediately after "
        f"`import larkdocio.blocks`."
    )


def test_registry_matches_get_registry():
    """BLOCK_REGISTRY and get_registry() must describe the same set of types.
    Since every handler now registers eagerly on import, get_registry() only
    returns the already-populated registry, so the two always agree."""
    from larkdocio.blocks import BLOCK_REGISTRY, get_registry

    got = get_registry()
    assert set(BLOCK_REGISTRY) == set(got)


def test_get_registry_is_complete():
    """Sanity: once get_registry() runs, every supported type is present
    (this is the path the live Parser uses, so it should always be green)."""
    from larkdocio.blocks import get_registry

    registry = get_registry()
    missing = EXPECTED_SUPPORTED_TYPES - set(registry)
    assert not missing, f"get_registry() missing types {sorted(missing)}"
