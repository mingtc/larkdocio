"""THE SINGLE LIVE ARM for the Base ROW HIERARCHY — sub-items, end to end (LD-296).

``@pytest.mark.live_write``, deselected by default. Run it with::

    pytest -m live_write

**Against self-provisioned disposables, and nothing else.** Every Base this arm touches it
made itself, through :func:`base_write_harness.disposable_base`, and every one is in the
harness's ledger the moment it exists. It never touches a configured Base:
``LARKDOCIO_SCRATCH_BASE`` holds the only hand-authored ``Lookup`` / ``Email`` / ``Stage``
columns in existence and this arm's verbs include **creating a column and writing rows**. This
module never reads that variable, which the offline companion checks statically.

**What it proves that no offline test can.** The spike (LD-294) established every fact this
capability rests on; this arm reproduces the whole chain **through the shipped library** rather
than through a probe script:

* **the self-referencing link column is authored by the shipped field family** — one
  ``POST …/fields`` whose ``property.table_id`` is the table's own id;
* **``hierarchy_config`` PATCHES AND READS BACK — asserted as an EFFECT, not a ``code:0``.**
  The view is patched twice and the read-back must **MOVE** from the first field id to the
  second. That is the whole argument on this route, because an unrecognised key one level in
  answers ``code:0`` and changes nothing — so the arm sends that **bogus-key control** too, and
  requires it to leave the persisted value exactly where it was;
* **a text field target is refused LOCALLY, with zero calls** — the server's own ``1254001``
  never has to be spent;
* **a 3-level tree is written through the shipped record-write path** with no hierarchy-specific
  branch, and read back as a tree in depth-first order by the shipped accessor;
* **a deliberate CYCLE terminates with the typed marker** — built live, on the wire, because a
  fixture cycle proves the traversal and not that Lark accepts one. It does: ``code:0``.

**The delete is proved by a POST-DELETE RE-QUERY, never by the delete's own ``code:0``** — and
the Base delete route is the **drive** one (``DELETE /open-apis/drive/v1/files/{app_token}
?type=bitable``; the bitable route is a bodiless HTTP 404). Both facts are the spike's, carried
here so they are not re-learned. The harness owns both.

**It writes its own capture** to ``dev/base-study/captures/ld296-01-row-hierarchy-live.json``
— the LD-256 precedent — so the evidence is committed rather than described.

**Since LD-620 the write is REDIRECTED, and the corpus path is the ADDRESS it is aimed
at.** ``capture_sink.write_capture`` lands a re-run's reading in a run-scoped directory
outside every git working tree and says so out loud, because an armed ring overwrote committed
captures belonging to closed issues four times. A genuinely new measurement is landed as a
dated supersession by a human, never by a re-run.

**Gentle.** Around thirty calls, every one through the shipped clients' limiter at the pace the
probe packs sustained (≥1.2 s). Rate limits are not probed.

**Skips loudly, never silently.** Without write credentials the module skips with a message
naming exactly what is missing.
"""
import json
from pathlib import Path

import base_write_harness
import capture_sink
import pytest

from larkdocio.base import hierarchy as hier
from larkdocio.base import view_plan
from larkdocio.base.client import BaseReadClient
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
from larkdocio.base.schema_client import BaseSchemaClient, BaseSchemaRefusal
from larkdocio.base.write_client import BaseWriteClient

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

try:  # pragma: no cover - the loader is the canary's, and is optional here
    import canary_support

    canary_support.load_env()
except Exception:  # pragma: no cover - a missing loader must not fail collection
    pass

CAPTURE = (Path(__file__).resolve().parent.parent / "tests" / "captures" / "base-study" / "captures"
           / "ld296-01-row-hierarchy-live.json")

_OBSERVED = {}

#: The self-link column this arm authors, and the view field it names.
LINK_FIELD = "ld296-parent"


def _record(name, blob):
    _OBSERVED[name] = blob
    capture_sink.write_capture(CAPTURE, json.dumps({
        "_probe": "ld296-row-hierarchy",
        "_endpoint": (".../tables/{t}/fields + .../tables/{t}/views/{v} + .../records"
                      " + .../records/search"),
        "_method": "POST + PATCH + PUT",
        "_note": ("the whole row-hierarchy chain through the SHIPPED library: the "
                  "self-referencing link column, the hierarchy_config PATCH asserted as an "
                  "EFFECT against its own bogus-key control, a 3-level tree written as link "
                  "cell values, the tree read back client-side in depth-first order, and a "
                  "deliberate cycle that Lark accepts at code:0 and the read terminates on — "
                  "all against a self-provisioned disposable"),
        "_verdict": "OK",
        "observations": _OBSERVED,
    }, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def credentials():
    reason = base_write_harness.missing_reason()
    if reason:
        pytest.skip(reason)
    return True


def _field(read, app_token, table_id, name):
    return [f for f in read.list_fields(app_token, table_id) if f.field_name == name][0]


def _persisted(read, app_token, table_id, view_id):
    return hier.hierarchy_field_id(read.get_view(app_token, table_id, view_id))


def test_the_registries_declare_this_arm_MUTATING_before_it_calls_anything():
    """The shape every Base arm ships: the ops about to run are declared writes, and the READ
    registry still answers read-only about itself in the same breath."""
    from larkdocio.base import ops as base_ops
    from larkdocio.base import schema_ops, write_ops

    assert schema_ops.all_mutate() is True
    assert write_ops.all_mutate() is True
    assert base_ops.read_only() is True
    assert "update_view" in {d.name for d in schema_ops.schema_ops()}


def test_the_WHOLE_row_hierarchy_chain_against_a_self_provisioned_disposable(credentials):
    """One disposable, one chain — because every step depends on the previous one's ids."""
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()
    write = BaseWriteClient.from_write_credentials()

    with base_write_harness.disposable_base() as (app_token, table_id, title):
        assert base_write_harness.is_disposable_title(title)

        # ---- 1. the SELF-REFERENCING link column, through the shipped field family ---- #
        schema.create_field(app_token, table_id, LINK_FIELD, 18, ui_type="SingleLink",
                            properties={"table_id": table_id})
        second = f"{LINK_FIELD}-2"
        schema.create_field(app_token, table_id, second, 18, ui_type="SingleLink",
                            properties={"table_id": table_id})
        fields = read.list_fields(app_token, table_id)
        link = _field(read, app_token, table_id, LINK_FIELD)
        other = _field(read, app_token, table_id, second)
        primary = [f for f in fields if f.is_primary][0]
        _record("self_link_create", {
            "field_id": link.field_id,
            "property_table_id": getattr(link.property, "table_id", None),
            "own_table_id": table_id,
            "multiple": getattr(link.property, "multiple", None),
        })
        assert getattr(link.property, "table_id", None) == table_id, (
            "a self-link is a link whose target is its own table")

        # ---- 2. a TEXT target is refused LOCALLY, with ZERO calls -------------------- #
        with pytest.raises(BaseSchemaRefusal) as excinfo:
            hier.hierarchy_config(primary.field_id, fields=fields)
        assert hier.HIERARCHY_FIELD_MUST_BE_A_LINK in str(excinfo.value)
        _record("text_target_refused_locally", {
            "field_id": primary.field_id, "calls_spent": 0,
            "message_quotes_the_server": hier.HIERARCHY_FIELD_MUST_BE_A_LINK in
                                         str(excinfo.value)})

        # ---- 3. hierarchy_config PATCHES, and the read-back MOVES -------------------- #
        view_id = read.list_views(app_token, table_id)[0].view_id
        before = _persisted(read, app_token, table_id, view_id)
        log = schema_apply(schema_dry_run([view_plan.set_view_hierarchy(
            app_token, table_id, view_id,
            hier.hierarchy_config(link.field_id, fields=fields, table_id=table_id))]),
            client=schema, read_client=read)
        assert [e.outcome for e in log.entries] == ["applied"], (
            log.entries[0].refusal.detail if log.entries[0].refusal else None)
        first = _persisted(read, app_token, table_id, view_id)

        log = schema_apply(schema_dry_run([view_plan.set_view_hierarchy(
            app_token, table_id, view_id,
            hier.hierarchy_config(other.field_id, fields=fields, table_id=table_id))]),
            client=schema, read_client=read)
        assert [e.outcome for e in log.entries] == ["applied"]
        moved = _persisted(read, app_token, table_id, view_id)
        _record("hierarchy_config_effect", {
            "before": before, "after_first_patch": first, "after_second_patch": moved,
            "the_effect_assertion": "the read-back MOVED from one field id to another"})
        assert before is None, "a fresh view names no hierarchy field"
        assert first == link.field_id
        assert moved == other.field_id and moved != first, (
            "code:0 proves nothing on this route; the MOVE is the evidence")

        # …and back to the real one, so the rest of the arm runs against a real hierarchy.
        schema_apply(schema_dry_run([view_plan.set_view_hierarchy(
            app_token, table_id, view_id,
            hier.hierarchy_config(link.field_id, fields=fields, table_id=table_id))]),
            client=schema, read_client=read)
        assert _persisted(read, app_token, table_id, view_id) == link.field_id

        # ---- 4. the R12 CONTROL: an unrecognised key changes NOTHING ----------------- #
        control = schema._checked(
            schema._sdk.bitable.v1.app_table_view.patch,
            _bogus_patch(app_token, table_id, view_id),
            "R12 control: an unrecognised key inside property.hierarchy_config")
        after_control = _persisted(read, app_token, table_id, view_id)
        _record("bogus_key_control", {
            "code": getattr(control, "code", 0),
            "persisted_after": after_control,
            "unchanged": after_control == link.field_id})
        assert after_control == link.field_id, (
            "the control must answer code:0 and change nothing — that is what makes the "
            "assertions above mean something")

        # ---- 5. a 3-LEVEL TREE through the SHIPPED record-write path ----------------- #
        name = primary.field_name
        root = write.create_record(app_token, table_id, {name: "ROOT-1"})
        root_id = getattr(root, "record_id", None) or root["record_id"]
        child = write.create_record(app_token, table_id,
                                    {name: "CHILD-1", LINK_FIELD: [root_id]})
        child_id = getattr(child, "record_id", None) or child["record_id"]
        leaf = write.create_record(app_token, table_id,
                                   {name: "LEAF-1", LINK_FIELD: [child_id]})
        leaf_id = getattr(leaf, "record_id", None) or leaf["record_id"]

        records = read.search_records(app_token, table_id)
        tree = hier.read_hierarchy(read.list_fields(app_token, table_id), records,
                                   field_name=LINK_FIELD)
        order = [row.record_id for row in tree.rows]
        _record("three_level_tree", {
            "root": root_id, "child": child_id, "leaf": leaf_id,
            "depth_first_order": order,
            "depths": {row.record_id: row.depth for row in tree.rows},
            "source": tree.source_detail,
        })
        assert tree.configured is True and tree.field_name == LINK_FIELD
        assert order.index(root_id) < order.index(child_id) < order.index(leaf_id)
        assert [tree.row(r).depth for r in (root_id, child_id, leaf_id)] == [0, 1, 2]

        # the view is a CITATION, and it answers the same thing
        by_view = hier.read_hierarchy(read.list_fields(app_token, table_id), records,
                                      view=read.get_view(app_token, table_id, view_id))
        assert by_view.field_id == link.field_id
        assert view_id in by_view.source_detail

        # ---- 6. the DELIBERATE DEFECT: a cycle, live, at code:0 --------------------- #
        write.update_record(app_token, table_id, root_id, {LINK_FIELD: [leaf_id]})
        cyclic = hier.read_hierarchy(read.list_fields(app_token, table_id),
                                     read.search_records(app_token, table_id),
                                     field_name=LINK_FIELD)
        _record("live_cycle", {
            "edge_written": f"{root_id} -> {leaf_id} (closing ROOT -> CHILD -> LEAF -> ROOT)",
            "lark_accepted": True,
            "cycles": [list(c) for c in cyclic.cycles],
            "placements": {row.record_id: row.placement for row in cyclic.rows},
            "terminated": True,
        })
        assert len(cyclic.rows) == len(records), "termination: every row emitted exactly once"
        assert cyclic.cycles, "the cycle is NAMED, not sorted quietly last"
        assert set(cyclic.cycles[0]) == {root_id, child_id, leaf_id}
        for record_id in (root_id, child_id, leaf_id):
            assert cyclic.row(record_id).placement == hier.PLACEMENT_CYCLE

    # ---- 7. the disposable is gone, and the RE-QUERY is what proves it -------------- #
    left = base_write_harness.close_out()
    _record("close_out", {"survivors": left})
    assert left == [], f"a disposable outlived this arm: {left}"


def _bogus_patch(app_token, table_id, view_id):
    """The R12 control's request: a key that cannot mean anything, inside the real one.

    Assembled from the pinned SDK's own builders like every other body on this route — what
    makes it a control is the KEY, not a hand-rolled request.
    """
    from lark_oapi.api.bitable.v1 import (
        AppTableViewProperty,
        AppTableViewPropertyHierarchyConfig,
        PatchAppTableViewRequest,
        PatchAppTableViewRequestBody,
    )

    config = AppTableViewPropertyHierarchyConfig.builder().build()
    config.larkdocio_not_a_real_key = "x"
    body = PatchAppTableViewRequestBody.builder().property(
        AppTableViewProperty.builder().hierarchy_config(config).build()).build()
    return PatchAppTableViewRequest.builder() \
        .app_token(app_token).table_id(table_id).view_id(view_id) \
        .request_body(body).build()
