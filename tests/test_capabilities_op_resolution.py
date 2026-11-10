"""LD-320 — every ``capabilities()`` op row maps to code without a ``dir()``.

The consumer's report said op names "don't always map to Python entry points". Measured, the
premise was wrong and the defect was real: every one of the 88 op rows already carries a
``projected_from`` (it is a required dataclass field), but **39 of them named a path the op
name could not be reached through** — 36 named a descriptor table whose op name is a
descriptor *field*, and 3 named a module the op name is simply not in while the row's own
``impl`` held the true callable.

The fix is not a new string per row: it is a **declared, closed set of projection shapes**
(:mod:`larkdocio.capabilities._resolution`), published per row as ``resolves_by``, plus an
``entry_point`` + ``note`` on the rows that are internal ops. This module is the guard that
makes it un-rottable.

**Reverse (source → registry) coverage, stated rather than implied.**

*Covered* — every source that is a real, enumerable collection of ops:

* ``larkdocio.write.ops.OPS`` (docx write descriptors, keyed ``.kind``)
* ``larkdocio.sheets.ops.OPS`` (sheets write descriptors, keyed ``.kind``)
* ``larkdocio.base.write_ops.WRITE_OPS`` (Base record-write descriptors, keyed ``.name``)
* ``larkdocio.base.schema_ops.schema_ops()`` (Base schema-write descriptors, keyed ``.name``)
* ``larkdocio.model.tree.__all__`` (the tree helpers)

*Not covered, and why* — the remaining sources are not op collections, so a reverse assertion
over them would be a fabricated claim rather than a check:

* rows whose ``projected_from`` is a **module** (e.g. ``larkdocio.base.read``,
  ``larkdocio.comments.read``): the module's public surface is models, errors and helpers as
  well as ops, so "every public symbol needs a row" is simply false.
* rows whose ``projected_from`` is a **client class** projected by ``_read_operations`` /
  ``_lifecycle_operations``: the forward direction is already total there (the projection
  enumerates the class itself, and a lifecycle row naming a missing method raises at
  projection time), so a reverse test would restate the projection rather than guard it.
"""
import importlib

import pytest

import larkdocio
from larkdocio.capabilities import _resolution as R

#: The three row-bearing keys a surface can carry.
ROW_KEYS = ("operations", "lifecycle", "legs")


def _op_rows():
    """``[(surface_key, row_key, row), ...]`` for every op row in ``capabilities()``."""
    caps = larkdocio.capabilities(full=True)
    rows = []
    for surface_key, surface in caps["surfaces"].items():
        for row_key in ROW_KEYS:
            for row in surface.get(row_key, ()) or ():
                rows.append((surface_key, row_key, row))
    return rows


def test_the_walk_covers_every_row_bearing_key():
    rows = _op_rows()
    assert len(rows) >= 88, f"expected at least the 88 measured rows, walked {len(rows)}"
    assert {rk for _s, rk, _r in rows} <= set(ROW_KEYS)


def test_every_row_declares_a_shape_from_the_closed_set():
    for surface_key, row_key, row in _op_rows():
        shape = row.get("resolves_by")
        assert shape in R.PROJECTION_SHAPES, (
            f"{surface_key}.{row_key}.{row['name']} declares resolves_by={shape!r}, "
            f"which is not one of {sorted(R.PROJECTION_SHAPES)}")


def test_every_row_resolves_to_real_code_by_its_declared_shape():
    """The forward direction: name + projected_from + resolves_by reach an object."""
    for surface_key, row_key, row in _op_rows():
        resolved = R.resolve(
            row["name"], row["projected_from"], row["resolves_by"],
            entry_point=row.get("entry_point"))
        assert resolved is not None, (
            f"{surface_key}.{row_key}.{row['name']} did not resolve at "
            f"{row['projected_from']!r} by {row['resolves_by']!r}")


@pytest.mark.parametrize("shape,path,name", [
    (R.ATTRIBUTE, "larkdocio.base.media", "upload_attachment_media"),
    (R.DESCRIPTORS_BY_KIND, "larkdocio.sheets.ops.OPS", "no_such_kind"),
    (R.DESCRIPTORS_BY_NAME, "larkdocio.base.write_ops.WRITE_OPS", "no_such_name"),
    (R.CALLED_DESCRIPTORS_BY_NAME, "larkdocio.base.schema_ops.schema_ops", "nope"),
    (R.ATTRIBUTE, "larkdocio.no.such.module", "anything"),
])
def test_a_row_that_stops_resolving_reddens(shape, path, name):
    """The guard's teeth: exactly the rows that were broken before this issue now raise."""
    with pytest.raises(R.UnresolvableOp):
        R.resolve(name, path, shape)


def test_entry_point_rows_say_use_x_and_the_x_is_reachable():
    """AC1(ii): an internal op names the symbol a consumer should actually call."""
    seen = {}
    for _s, _rk, row in _op_rows():
        if row["resolves_by"] != R.ENTRY_POINT:
            continue
        assert row["entry_point"], f"{row['name']} has no entry_point"
        assert row["note"].startswith("internal op — use "), row["note"]
        assert row["entry_point"] in row["note"]
        assert R.resolve(row["name"], row["projected_from"], R.ENTRY_POINT,
                         entry_point=row["entry_point"]) is not None
        seen[row["name"]] = row["entry_point"]
    assert seen == {
        "upload_attachment_media": "larkdocio.base.media.BaseMediaClient.upload",
        "download_attachment_media": "larkdocio.base.media.BaseMediaClient.download",
        "permalink_attachment_media": "larkdocio.base.media.BaseMediaClient.permalink",
        "migrate_field_type": "larkdocio.base.field_migration.apply_field_migration",
    }, seen


@pytest.mark.parametrize("path,key", [
    ("larkdocio.write.ops.OPS", "kind"),
    ("larkdocio.sheets.ops.OPS", "kind"),
    ("larkdocio.base.write_ops.WRITE_OPS", "name"),
    ("larkdocio.base.schema_ops.schema_ops", "name"),
])
def test_no_descriptor_collection_member_is_missing_a_registry_row(path, key):
    """The reverse direction, where it is cheap: a descriptor with no row reddens."""
    table = R.object_at(path)
    if callable(table):
        table = table()
    members = {getattr(descriptor, key) for descriptor in table}
    rows = {row["name"] for _s, _rk, row in _op_rows() if row["projected_from"] == path}
    assert members - rows == set(), f"{path}: members with no capabilities() row"


def test_no_tree_helper_is_missing_a_registry_row():
    tree = importlib.import_module("larkdocio.model.tree")
    rows = {row["name"] for _s, _rk, row in _op_rows()
            if row["projected_from"] == "larkdocio.model.tree"}
    assert set(tree.__all__) - rows == set()


def test_docs_block_states_guide_section_addressability():
    """AC4 (Friction 8's other half): the docs block says the sections are addressable."""
    doc = larkdocio.capabilities(full=True)["docs"]["guide()"]
    assert doc["sections"], "the guide row lost its section index"
    addressing = doc["section_addressing"]
    assert "guide(section=" in addressing
    assert "###" in addressing
    assert "slug" in addressing
    # A document with no section index makes no addressability claim.
    for label, other in larkdocio.capabilities(full=True)["docs"].items():
        if other.get("sections") is None:
            assert "section_addressing" not in other, label
