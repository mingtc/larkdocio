"""Characterization tests for the write-model subpackage split (LD-087).

The 768-line ``write/model.py`` was split into a ``write/model/`` subpackage —
``anchors`` / ``requests`` / ``refusal`` / ``applylog`` — behind a back-compat
re-export shim (the ``auth.py`` precedent). These tests pin the two invariants the
split must preserve:

* **the split happened** — ``larkdocio.write.model`` is now a *package* whose four
  concern-group submodules import cleanly (the structural goal of the refactor), and
* **zero downstream import churn** — every public name **and** the two private
  dispatchers still resolve from ``larkdocio.write.model`` as the *same objects*, and
  ``larkdocio.write`` re-exports those same objects (B1 / B2).

The internal file boundaries (which type lives in which submodule) are deliberately
NOT asserted here — only the re-export surface is (per the issue's "intentionally
unconstrained" carveout).
"""
import importlib

import pytest

# The full findings-agnostic vocabulary the shim must keep importable from
# ``larkdocio.write.model`` (B1). The public value objects + the private dispatchers
# preview.py / the tests import by name. (LD-137 added ``AnchorById`` — a new anchor shape
# joins this surface, so the shim must re-export it as the same object too.)
_PUBLIC_SURFACE = (
    "Anchor",
    "AnchorById",
    "TableLocator",
    "EditRequest",
    "InsertPosition",
    "NewParagraph",
    "InsertRequest",
    "SubSpanEditRequest",
    "DeleteRequest",
    "RefusalReason",
    "Refusal",
    "ApplyLogEntry",
    "ApplyLog",
)
_PRIVATE_DISPATCHERS = ("_anchor_from_dict", "_request_from_dict")


def test_write_model_is_a_package():
    """After the split ``larkdocio.write.model`` is a PACKAGE (has ``__path__``),
    not a single module — the structural goal of the refactor."""
    import larkdocio.write.model as m

    assert hasattr(m, "__path__"), "write.model should be a package after the split"


@pytest.mark.parametrize("submodule", ["anchors", "requests", "refusal", "applylog"])
def test_concern_submodules_exist(submodule):
    """Each of the four concern-group submodules imports cleanly."""
    mod = importlib.import_module(f"larkdocio.write.model.{submodule}")
    assert mod is not None


def test_full_public_surface_resolves_from_write_model():
    """B1 — every public name AND both private dispatchers still import from
    ``larkdocio.write.model`` (the shim re-exports the SAME objects, no churn)."""
    import larkdocio.write.model as m

    for name in _PUBLIC_SURFACE + _PRIVATE_DISPATCHERS:
        assert hasattr(m, name), f"{name} no longer importable from larkdocio.write.model"


def test_write_package_reexport_is_the_same_object():
    """B2 — ``larkdocio.write`` re-exports the identical objects the model package
    defines (same object identity, so no shadow copy / fork slipped in)."""
    import larkdocio.write as w
    import larkdocio.write.model as m

    for name in _PUBLIC_SURFACE:
        assert getattr(w, name) is getattr(m, name), f"{name} identity diverged"
