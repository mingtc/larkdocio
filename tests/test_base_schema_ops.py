"""LD-263 AC1b — THE SCHEMA-OP AGGREGATOR, and the ``read_only()`` fence it must not break.

The aggregator is the **one registration point** every schema-op family plugs into. This
story ships it plus the app/table family; LD-262 (fields) and LD-264 (views) each add their
own module and **one** line to :data:`larkdocio.base.schema_ops.FAMILY_MODULES`. That is what
makes wave 2 parallel-safe: the two later stories import a wave-1 seam instead of each other.

The fence, asserted in both directions: the schema descriptors declare ``mutates: True`` and
live in a **write** registry, so ``larkdocio.base.ops.read_only()`` keeps answering ``True``
about the **read** op set.
"""
import importlib

import pytest

from larkdocio.base import ops as read_ops
from larkdocio.base import schema_ops
from larkdocio.base import write_ops
import private_tree  # noqa: E402  (LD-685)


# --------------------------------------------------------------------------- #
# The aggregator itself                                                        #
# --------------------------------------------------------------------------- #

def test_the_aggregator_is_a_REGISTRATION_POINT_and_a_family_ADDS_ONE_LINE():
    """The seam's whole claim, checked from both ends.

    LD-263 shipped this assertion against a **single** family and predicted the shape of the
    next two: *"LD-262 and LD-264 each ADD one, they do not replace this one."* Both have now
    discharged that prediction, so the assertion sits in the shape that survives the addition
    after them too: app-and-table is still registered, still **first**, and still exactly its
    own six ops, and the number of families is the number of modules named in the registration
    point.
    """
    families = schema_ops.registered_families()
    names = [family.name for family in families]
    assert names[0] == "app-and-table", (
        "a family ADDS a line; it does not reorder or replace the ones already there")
    assert {"field", "view"} <= set(names), names
    assert len(names) == len(set(names)) == len(schema_ops.FAMILY_MODULES)
    assert schema_ops.FAMILY_MODULES[0] == "larkdocio.base.schema_ops_app_table"
    assert "larkdocio.base.schema_ops_views" in schema_ops.FAMILY_MODULES
    assert len(families[0].ops) == 6


def test_every_family_module_named_in_the_registration_point_IMPORTS_and_exposes_its_family():
    for name in schema_ops.FAMILY_MODULES:
        module = importlib.import_module(name)
        family = getattr(module, "SCHEMA_OP_FAMILY", None)
        assert family is not None, f"{name} does not expose SCHEMA_OP_FAMILY"
        assert family.module == name, (family.module, name)
        assert family.ops, f"{name} registers no op"


def test_the_flattened_op_set_is_the_families_in_registration_order():
    flattened = tuple(
        descriptor
        for family in schema_ops.registered_families()
        for descriptor in family.ops)
    assert schema_ops.schema_ops() == flattened


def test_a_family_module_can_be_imported_FIRST_without_the_aggregator_being_half_built():
    """The import-order hazard a naive aggregator has.

    The family module imports its descriptor type from the aggregator, and the aggregator
    imports the family modules. Importing the family FIRST must therefore still produce a
    complete aggregation — otherwise LD-262 and LD-264 inherit a seam that breaks depending
    on which module a consumer happens to touch first.
    """
    import subprocess
    import sys

    proof = subprocess.run(
        [sys.executable, "-c",
         "import larkdocio.base.schema_ops_app_table as f;"
         "from larkdocio.base import schema_ops as a;"
         "import importlib;"
         "whole = sum(len(importlib.import_module(m).SCHEMA_OP_FAMILY.ops)"
         "            for m in a.FAMILY_MODULES);"
         "print(len(a.schema_ops()), whole, len(f.SCHEMA_OP_FAMILY.ops))"],
        capture_output=True, text=True, check=True)
    counts = proof.stdout.split()
    assert counts[0] == counts[1] != "0", proof.stdout
    assert counts[2] == "6", proof.stdout


def test_the_six_app_and_table_ops_are_registered_by_name():
    """The family's own six, in order, and **first** in the flattened table — registration
    order is what the aggregator promises, so a family added later appends."""
    six = ["create_app", "rename_app", "copy_app",
           "create_table", "batch_create_tables", "rename_table"]
    assert [d.name for d in schema_ops.schema_ops() if d.family == "app-and-table"] == six
    assert [d.name for d in schema_ops.registered_families()[0].ops] == six
    assert [d.name for d in schema_ops.schema_ops()][:6] == six


def test_the_flattened_table_is_EVERY_family_in_order_with_no_op_lost():
    """The other half: filtering by family above must not become a way to lose an op."""
    per_family = [name for family in schema_ops.registered_families()
                  for name in (d.name for d in family.ops)]
    assert [d.name for d in schema_ops.schema_ops()] == per_family
    assert len(set(per_family)) == len(per_family), "two families registered the same op name"


def test_every_schema_descriptor_declares_MUTATES_TRUE_explicitly():
    assert schema_ops.all_mutate() is True
    for descriptor in schema_ops.schema_ops():
        assert descriptor.mutates is True, descriptor.name


def test_every_schema_descriptor_names_the_ENDPOINT_AND_VERB_THE_SDK_ACTUALLY_CALLS():
    """Not the descriptor's own strings against themselves — against the SDK request class,
    so the descriptor and the doc cannot agree with each other and both be wrong."""
    for descriptor in schema_ops.schema_ops():
        built = descriptor.request_cls.builder().build()
        assert descriptor.endpoint == built.uri, descriptor.name
        assert descriptor.http_method == built.http_method.name, descriptor.name


def test_every_schema_descriptor_names_a_REAL_client_method():
    from larkdocio.base.schema_client import BaseSchemaClient

    for descriptor in schema_ops.schema_ops():
        assert schema_ops.impl_of(descriptor) is getattr(BaseSchemaClient, descriptor.name)


@private_tree.citations
def test_every_schema_descriptor_carries_EVIDENCE_that_exists():
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    missing = []
    for descriptor in schema_ops.schema_ops():
        assert descriptor.evidence.strip(), descriptor.name
        for token in descriptor.evidence.replace("·", " ").split():
            if token.startswith("dev/") or token.startswith("tests/"):
                if not (repo / token).exists():
                    missing.append((descriptor.name, token))
    assert not missing, missing


def test_schema_op_lookup_by_name_and_the_miss():
    assert schema_ops.schema_op("copy_app").name == "copy_app"
    with pytest.raises(KeyError):
        # `delete_table` became a real op when the destructive family landed, so the miss is
        # asserted with a name no family ships — the drive-file delete that removes a Base,
        # which is deliberately still not an operation on this surface.
        schema_ops.schema_op("delete_app")


def test_the_ONE_ASYNC_op_is_flagged_and_it_is_COPY():
    settling = [d.name for d in schema_ops.schema_ops() if d.settles]
    assert settling == ["copy_app"], (
        "copy is the only non-synchronous Base operation found in three probe packs; a "
        "second one appearing here means the evidence moved")


def test_EVERY_DESTRUCTIVE_op_IS_FENCED_and_the_DRIVE_FILE_DELETE_IS_STILL_NOT_ONE():
    """The claim this guard makes, revised deliberately when LD-265 landed the deletes.

    LD-263 registered no delete at all and LD-264 added exactly one — ``DELETE …/views/{v}``,
    whose blast radius is a view and which the server floors at one view per table
    (``1254023``). LD-265 added the three that can **lose data**, and the guard's subject moves
    with them: it is no longer *"no delete that loses data exists"* but **"every delete that
    loses data is declared destructive and therefore fenced"** — a strictly stronger statement
    about a strictly larger surface, because a delete nobody declared would be a delete the
    consent fence never sees.

    The one absence that survives unchanged: **the drive-file delete that removes a Base is
    still not an operation here.**
    """
    deletes = [d.name for d in schema_ops.schema_ops()
               if d.http_method == "DELETE" or "delete" in d.name]
    assert deletes == ["delete_view", "delete_field", "delete_table", "batch_delete_tables"], \
        deletes

    fenced = schema_ops.destructive_ops()
    assert fenced == {"delete_field", "delete_table", "batch_delete_tables"}
    for descriptor in schema_ops.schema_ops():
        if descriptor.name == "delete_view":
            # The one delete that is NOT in the destructive set, and the reason is its blast
            # radius: a view carries no data of its own, and the server itself keeps a floor.
            assert descriptor.endpoint.endswith("/views/:view_id")
            continue
        lossy = descriptor.endpoint.endswith(
            ("/tables/:table_id", "/tables/batch_delete", "/fields/:field_id"))
        if lossy and (descriptor.http_method == "DELETE"
                      or descriptor.endpoint.endswith("/tables/batch_delete")):
            assert descriptor.name in fenced, (
                f"{descriptor.name} can lose data and is not declared destructive, so nothing "
                "would ask for consent before it ran")

    assert not [d for d in schema_ops.schema_ops() if "/drive/" in d.endpoint], (
        "deleting the Base itself is a live-harness primitive, not a shipped op")


# --------------------------------------------------------------------------- #
# The read_only() fence — AC1b's binding half                                  #
# --------------------------------------------------------------------------- #

def test_the_READ_registry_still_answers_read_only_TRUE_with_a_schema_write_registry_shipped():
    assert read_ops.read_only() is True
    assert schema_ops.all_mutate() is True


def test_the_schema_registry_is_a_THIRD_TABLE_not_an_append_to_either_landed_one():
    read_names = {d.name for d in read_ops.OPS}
    write_names = {d.name for d in write_ops.WRITE_OPS}
    schema_names = {d.name for d in schema_ops.schema_ops()}
    assert not (schema_names & read_names)
    assert not (schema_names & write_names)
    # The READ registry grew by ONE in LD-264 — `get_view`, a read op, `mutates: False` — and
    # by ONE again in LD-269 — `batch_get_records`, the SECOND POST read, `mutates: False`.
    # That is the point of three tables rather than one: a schema WRITE still did not touch it.
    assert len(read_ops.OPS) == 7 and len(write_ops.WRITE_OPS) == 6
    assert read_ops.read_only() is True


def test_DEFECT_appending_a_MUTATING_descriptor_to_the_READ_registry_would_flip_the_fence():
    """The falsification of the split: the fence bites, it is not merely stated."""
    contaminated = read_ops.OPS + (schema_ops.schema_ops()[0],)
    assert not all(d.mutates is False for d in contaminated)
