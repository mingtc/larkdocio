"""LD-393 — a test's verdict must not depend on which neighbour ran before it.

`tests/test_cli_logging_config.py` pops `larkdocio.cli` out of `sys.modules` and
re-imports it (that IS the thing it characterizes: LD-079's no-handler-at-import
contract can only be observed on a fresh module body), and `tests/test_registry.py`
does the same for `larkdocio.blocks.*`. Left standing, that reload publishes a
SECOND live module object: modules that already hold `from larkdocio.cli import cli`
keep the first, while `monkeypatch.setattr("larkdocio.cli.<name>", ...)` — a *string*
target, resolved through `sys.modules` at patch time — writes to the second. The CLI
group then calls the unpatched real handler, `CliRunner` swallows the fallout, and the
test dies on a `KeyError` several lines away from its cause. Under `-n auto` the
scheduler decides whether the two land in one worker, so the binding gate reddens at
random on an unchanged tree.

These tests pin the invariant that removes the whole class: whatever a test does to
`sys.modules`, the next test sees the module objects it started with.
"""

import importlib
import sys

from conftest import stable_larkdocio_modules


def test_a_replaced_larkdocio_module_is_put_back_on_exit():
    original = importlib.import_module("larkdocio.cli")

    with stable_larkdocio_modules():
        sys.modules.pop("larkdocio.cli", None)
        reloaded = importlib.import_module("larkdocio.cli")
        # The reload is legitimate INSIDE the block — that is what the caller wants.
        assert reloaded is not original
        assert sys.modules["larkdocio.cli"] is reloaded

    # ...and invisible outside it, so no neighbour inherits the duplicate —
    # in `sys.modules` AND on the parent package, the two ways an importer looks.
    import larkdocio

    assert sys.modules["larkdocio.cli"] is original
    assert larkdocio.cli is original


def test_a_package_and_its_submodules_are_all_put_back():
    blocks = importlib.import_module("larkdocio.blocks")
    divider = importlib.import_module("larkdocio.blocks.divider")

    with stable_larkdocio_modules():
        for name in [n for n in list(sys.modules) if n.startswith("larkdocio.blocks")]:
            del sys.modules[name]
        importlib.import_module("larkdocio.blocks")
        assert sys.modules["larkdocio.blocks"] is not blocks

    assert sys.modules["larkdocio.blocks"] is blocks
    assert sys.modules["larkdocio.blocks.divider"] is divider


def test_an_export_that_shadows_its_own_submodule_survives():
    """`larkdocio.capabilities` is the FUNCTION, not the module of that name.

    Restoring the parent attribute blindly would overwrite the export with the
    module and break every caller of `larkdocio.capabilities()`.
    """
    import larkdocio

    before = larkdocio.capabilities

    with stable_larkdocio_modules():
        sys.modules.pop("larkdocio.capabilities", None)
        importlib.import_module("larkdocio.capabilities")

    assert larkdocio.capabilities is before
    assert callable(larkdocio.capabilities)


def test_a_first_time_import_inside_the_block_is_left_alone():
    """Only a REPLACED entry is restored — a fresh import is not unloaded."""
    sys.modules.pop("larkdocio.sheets.extent", None)

    with stable_larkdocio_modules():
        freshly = importlib.import_module("larkdocio.sheets.extent")

    assert sys.modules["larkdocio.sheets.extent"] is freshly


def test_the_autouse_fixture_hands_every_test_the_same_cli_module():
    """The end-to-end property the flake needed: the string-patch target and the
    module-level `from larkdocio.cli import cli` are one object."""
    import larkdocio.cli as cli_mod
    from larkdocio.cli import cli

    assert sys.modules["larkdocio.cli"] is cli_mod
    assert cli_mod.cli is cli
