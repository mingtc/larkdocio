"""THE SINGLE LIVE SCHEMA ARM for Base FIELD authoring (LD-262).

``@pytest.mark.live_write``, deselected by default. Run it with::

    pytest -m live_write

**Against self-provisioned disposables, and nothing else.** Every Base this arm touches it made
itself, through :func:`base_write_harness.disposable_base`, and every one is in the harness's
ledger the moment it exists. It never touches a configured Base: ``LARKDOCIO_SCRATCH_BASE``
holds the only hand-authored ``Lookup`` / ``Email`` / ``Stage`` columns in existence and the API
**cannot** recreate them — and this arm's verbs include *convert a column's kind*, which rewrites
every value in it. This module never reads that variable, which the offline companion checks
statically.

**What it proves that no offline test can.**

* **The DuplexLink CROSS-TABLE CREATE, live** — one ``POST …/fields`` in table A puts a second
  column in table B, named ``<source table>-<source column>``, and the dry run said so first;
* **the conversion's effect ON THE CELLS** — the one captured pair (``Text`` → ``Barcode``) run
  over a column that **holds a value**, with the value read back afterwards. That is what makes
  the pair table evidence-keyed rather than ``code:0``-keyed, and it is the probe the pair table
  was missing;
* **the ``Formula`` authoring answer** — the one real, cheap, un-taken probe. Whether Lark
  authors a ``Formula`` column through ``POST …/fields`` with a ``formula_expression`` was
  observed by no pack. **Either outcome is a pass and both are recorded**: on success the shape
  is captured, on refusal the code and body are. Silence is not;
* **what the anchor actually reads on a NEW Base** — ``…/tables`` answers ``revision: 0`` for a
  table nothing has touched yet, which is the sentinel meaning *no anchor available*, and ``1``
  after the first field op. So the guard is ``unavailable`` at plan time on a fresh disposable
  and the identity read-back stands alone there. The arm asserts what it observes rather than
  what would be convenient, and both branches are written down.

**It writes its own capture.** Every probe's request and answer is written to
``tests/captures/base-study/captures/ld262-01-field-authoring-probes.json`` — the LD-256 precedent — so the
evidence this story rests on is committed rather than described.

**Gentle.** Around twenty calls, every one through a limiter at the pace the probe packs
sustained (≥1.2 s). Rate limits are not probed.

**Skips loudly, never silently.** Without write credentials the module skips with a message
naming exactly what is missing.
"""
import json
from pathlib import Path

import base_write_harness
import capture_sink
import pytest
from lark_oapi.core import json as lark

from larkdocio.base import field_authoring as fa
from larkdocio.base import schema_ops_fields as sof
from larkdocio.base.client import BaseReadClient
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
from larkdocio.base.schema_client import BaseSchemaClient
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
           / "ld262-01-field-authoring-probes.json")

_OBSERVED = {}


def _record(name, blob):
    _OBSERVED[name] = blob
    capture_sink.write_capture(CAPTURE, json.dumps({
        "_probe": "ld262-field-authoring",
        "_endpoint": ".../tables/{t}/fields",
        "_method": "POST + PUT",
        "_note": ("the DuplexLink cross-table mirror, the Text -> Barcode conversion's effect "
                  "ON A POPULATED CELL, the Formula authoring probe, and table.revision's "
                  "+1-per-field-op — all against a self-provisioned disposable"),
        "_verdict": "OK",
        "observations": _OBSERVED,
    }, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


LD280_CAPTURE = (Path(__file__).resolve().parent.parent / "tests" / "captures" / "base-study" / "captures"
                 / "ld280-01-formula-evaluation-probe.json")

_LD280_OBSERVED = {}

#: How many times the probe re-reads the records looking for the formula's cell. Every read
#: passes through the read client's own limiter (≥1.2 s apart), so the settle window is paid
#: for by the reads themselves — no test sleeps, and a cell that appears late is still seen.
LD280_POLLS = 8


def _record_ld280(name, blob):
    _LD280_OBSERVED[name] = blob
    capture_sink.write_capture(LD280_CAPTURE, json.dumps({
        "_probe": "ld280-formula-evaluation",
        "_endpoint": ".../tables/{t}/fields + .../records/search + .../records/batch_get",
        "_method": "POST",
        "_note": ("THE CELL READ the ld262 probe never took: a Formula column authored through "
                  "POST .../fields, then its CELLS read on two routes, over a record written "
                  "before the column and a record written after it, re-read until a bounded "
                  "poll budget is spent — all against a self-provisioned disposable"),
        "_verdict": "OK",
        "observations": _LD280_OBSERVED,
    }, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def credentials():
    reason = base_write_harness.missing_reason()
    if reason:
        pytest.skip(reason)
    return True


def _revision(read, app_token, table_id):
    return sof.table_revision(read, app_token, table_id)


def test_the_schema_registry_declares_the_whole_arm_MUTATING_before_it_calls_anything():
    """The shape every Base arm ships: the ops this arm is about to run are declared writes,
    and the READ registry still answers read-only about itself in the same breath."""
    from larkdocio.base import ops as base_ops
    from larkdocio.base import schema_ops
    from larkdocio.base import write_ops

    assert schema_ops.all_mutate() is True
    assert write_ops.all_mutate() is True
    assert base_ops.read_only() is True
    assert {"create_field", "update_field", "convert_field"} <= {
        d.name for d in schema_ops.schema_ops()}


def test_the_live_field_lifecycle_creates_edits_and_moves_the_anchor(credentials):
    """Create → non-type edit, each verified by a read-back and by the anchor moving +1."""
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()

    with base_write_harness.disposable_base() as (app_token, table_id, title):
        assert base_write_harness.is_disposable_title(title)
        before = _revision(read, app_token, table_id)

        plan = schema_dry_run([
            sof.create_field(app_token, table_id, "ld262-note", 1, ui_type="Text",
                             revision=before),
        ])
        log = schema_apply(plan, client=schema, read_client=read)
        created = log.entries[0].read_back
        after_create = _revision(read, app_token, table_id)
        _record("field_lifecycle_anchor", {
            "revision_before_create": before,
            "revision_after_create": after_create,
            "read_back": {k: v for k, v in (created or {}).items() if k != "how"},
        })
        assert [e.outcome for e in log.entries] == ["applied"], (
            log.entries[0].refusal.detail if log.entries[0].refusal else None)
        # The anchor is asserted for what it IS, not for what would be convenient. On a Base
        # this arm just created, `…/tables` answers with **no revision at all** — the 0/None
        # sentinel — so the guard is `unavailable` and the identity read-back stands alone.
        # Where the anchor IS available it must have moved by exactly one.
        if created["revision_moved"] is None:
            assert created["revision_at_plan"] in (None, 0), created
            assert "unavailable" in created["anchor"], created
        else:
            assert created["revision_moved"] == 1, created
        assert created["identity_confirmed"] is True, created

        field_id = [f.field_id for f in read.list_fields(app_token, table_id)
                    if f.field_name == "ld262-note"][0]
        plan = schema_dry_run([
            sof.update_field(app_token, table_id, field_id, "ld262-renamed", 1,
                             revision=after_create),
        ])
        log = schema_apply(plan, client=schema, read_client=read)
        assert [e.outcome for e in log.entries] == ["applied"], (
            log.entries[0].refusal.detail if log.entries[0].refusal else None)

        assert [f.field_name for f in read.list_fields(app_token, table_id)
                if f.field_name == "ld262-renamed"], "the non-type edit reads back"


def test_the_DUPLEX_LINK_create_puts_a_column_IN_ANOTHER_TABLE_as_the_dry_run_said(
        credentials):
    """AC3, live and end to end: the plan names the second table and the mirror's predicted
    name **before** the call, and the mirror is there afterwards under exactly that name."""
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()

    with base_write_harness.disposable_base() as (app_token, table_id, title):
        target_id = schema.create_table(app_token, "ld262-target", primary_field_name="Title")
        source_name = [t.name for t in read.list_tables(app_token)
                       if t.table_id == table_id][0]
        before_target = {f.field_name for f in read.list_fields(app_token, target_id)}

        request = sof.create_field(app_token, table_id, "ld262-link", 21,
                                   ui_type="DuplexLink",
                                   properties={"table_id": target_id},
                                   source_table_name=source_name,
                                   revision=_revision(read, app_token, table_id))
        plan = schema_dry_run([request])
        disclosure = plan.entries[0].to_dict()["cross_table_create"]
        assert disclosure["table_id"] == target_id
        predicted = disclosure["predicted_field_name"]
        assert predicted == fa.duplex_mirror_name(source_name, "ld262-link")

        log = schema_apply(plan, client=schema, read_client=read)
        assert [e.outcome for e in log.entries] == ["applied"], (
            log.entries[0].refusal.detail if log.entries[0].refusal else None)

        after_target = {f.field_name for f in read.list_fields(app_token, target_id)}
        mirror = after_target - before_target
        _record("duplex_mirror", {
            "source_table": source_name, "target_table_id": target_id,
            "predicted_field_name": predicted, "new_fields_in_target": sorted(mirror),
        })
        assert predicted in mirror, (
            "the dry run named the mirror before the call; the target table must now hold it")


def test_the_ONE_CAPTURED_CONVERSION_pair_over_a_POPULATED_cell(credentials):
    """AC5's own probe — the evidence the pair table was missing.

    ``p1-q2-02`` showed ``Text`` → ``Barcode`` answering ``code:0`` on an **empty** column.
    This runs the same conversion over a column that HOLDS A VALUE and reads the value back, so
    the pair is keyed on what happened to the cells rather than on the response code.
    """
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()
    write = BaseWriteClient.from_write_credentials()

    with base_write_harness.disposable_base() as (app_token, table_id, title):
        schema.create_field(app_token, table_id, "ld262-conv", 1, ui_type="Text")
        field_id = [f.field_id for f in read.list_fields(app_token, table_id)
                    if f.field_name == "ld262-conv"][0]
        write.create_record(app_token, table_id, {"ld262-conv": "LD262-VALUE"})
        before = [dict(r.fields or {}) for r in read.search_records(app_token, table_id)]

        plan = schema_dry_run([
            sof.convert_field(app_token, table_id, field_id, "ld262-conv", 1,
                              from_ui_type="Text", to_ui_type="Barcode",
                              revision=_revision(read, app_token, table_id)),
        ])
        assert plan.entries[0].to_dict()["conversion"]["to"] == "Barcode"
        log = schema_apply(plan, client=schema, read_client=read)
        assert [e.outcome for e in log.entries] == ["applied"], (
            log.entries[0].refusal.detail if log.entries[0].refusal else None)

        after_fields = read.list_fields(app_token, table_id)
        converted = [f for f in after_fields if f.field_id == field_id][0]
        after = [dict(r.fields or {}) for r in read.search_records(app_token, table_id)]
        _record("text_to_barcode_over_a_populated_cell", {
            "cells_before": before, "cells_after": after,
            "type_after": converted.type, "ui_type_after": converted.ui_type,
        })
        assert converted.ui_type == "Barcode" and converted.type == 1
        assert "LD262-VALUE" in json.dumps(after, ensure_ascii=False), (
            "THE CELL EVIDENCE: the value must survive the conversion, or the pair does not "
            "belong in the table")


def test_the_FORMULA_authoring_probe_records_whichever_way_it_goes(credentials):
    """AC7 — the one real, cheap, un-taken probe. Success or refusal, it is recorded."""
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()

    with base_write_harness.disposable_base() as (app_token, table_id, title):
        outcome = {"requested": {"field_name": "ld262-formula", "type": 20,
                                 "ui_type": "Formula",
                                 "property": {"formula_expression": "1+1"}}}
        try:
            field = schema.create_field(app_token, table_id, "ld262-formula", 20,
                                        ui_type="Formula",
                                        properties={"formula_expression": "1+1"})
            outcome.update({
                "status": "captured", "code": 0,
                "created": {"type": field.type, "ui_type": field.ui_type,
                            "property": json.loads(lark.JSON.marshal(field.property))},
            })
        except Exception as exc:              # noqa: BLE001 — a refusal is the answer too
            outcome.update({"status": "refused", "error": repr(exc)[:800]})
        _record("formula_authoring_probe", outcome)
        print(f"\nFORMULA AUTHORING PROBE: {outcome['status']}")

        # WHICHEVER WAY IT WENT: a Formula CELL stays refused. Two constants, two questions.
        from larkdocio.base.write_vocabulary import NON_WRITABLE_PAIRS

        assert (20, "Formula") in NON_WRITABLE_PAIRS
        listed = {f.ui_type for f in read.list_fields(app_token, table_id)}
        assert outcome["status"] in ("captured", "refused")
        if outcome["status"] == "captured":
            assert "Formula" in listed


def test_LD280_the_FORMULA_probe_READS_THE_CELLS_and_the_shipped_row_matches(credentials):
    """LD-280 — the half of the probe ld262 never took: **does the column compute?**

    ``create_field``'s read-back proves a column EXISTS. It cannot tell a computing column
    from a dead one, and the dogfood session found four authored formulas whose cell key was
    absent from every record. So this probe reads the CELLS, on two routes, over a record
    written **before** the formula column and one written **after** it, and re-reads until
    every formula's key has arrived or a bounded poll budget is spent.

    **Three expressions, because the boundary is inside the kind, not around it.** A
    CONSTANT depends on no cell and so cannot be blamed on a mis-bound reference; a
    NAME-REFERENCE (``CurrentValue.[column]``) is the shape every real formula has; and the
    server's own REBOUND form, sent back verbatim, separates *"Lark rebinds names badly"*
    from *"a referencing formula never computes on this route at all"*.

    Whichever way each goes it is recorded, and the shipped
    :data:`~larkdocio.base.field_authoring.FORMULA_EVALUATION` row must AGREE with what is
    observed here — so the day Lark starts computing these columns this arm reddens and
    forces a re-capture rather than letting a stale refusal outlive its evidence.
    """
    schema = BaseSchemaClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()
    write = BaseWriteClient.from_write_credentials()

    provisioner = base_write_harness._Provisioner()
    with base_write_harness.disposable_base(provisioner=provisioner) as (
            app_token, table_id, _title):
        schema.create_field(app_token, table_id, "ld280-input", 2, ui_type="Number")
        input_id = [f.field_id for f in read.list_fields(app_token, table_id)
                    if f.field_name == "ld280-input"][0]
        write.create_record(app_token, table_id, {"ld280-input": 21})

        # The server's own binding syntax, assembled from ids it just handed us — no id
        # literal is written down here, and none could be: they are minted per Base.
        bound = f"CurrentValue.bitable::$table[{table_id}].$field[{input_id}]*2"
        wanted = {
            "ld280-const": "1+1",
            "ld280-ref": "CurrentValue.[ld280-input] * 2",
            "ld280-bound": bound,
        }
        created = {}
        for name, expression in wanted.items():
            if name == "ld280-const":
                # The one class the library still authors — through the shipped seam, so the
                # probe re-proves the fence lets the captured shape through.
                field = schema.create_field(app_token, table_id, name, 20, ui_type="Formula",
                                            properties={"formula_expression": expression})
            else:
                # Refused by the shipped builder on THIS capture's own evidence, so the probe
                # sends it through the harness's own seam instead — a measurement of the
                # server has to be able to send the body the library will not.
                with pytest.raises(fa.RefutedFieldAuthoringError):
                    schema.create_field(app_token, table_id, name, 20, ui_type="Formula",
                                        properties={"formula_expression": expression})
                field = provisioner.raw_create_field(
                    app_token, table_id, field_name=name, field_type=20, ui_type="Formula",
                    formula_expression=expression)
            created[name] = {
                "requested_expression": expression,
                "type": field.type, "ui_type": field.ui_type,
                "property_read_back": json.loads(lark.JSON.marshal(field.property)),
                "authored_through": ("the shipped client" if name == "ld280-const"
                                     else "the harness probe seam (the library refuses it)"),
            }

        # A record written AFTER every formula column exists — the "it only computes on the
        # next write" hypothesis, tested rather than assumed.
        write.create_record(app_token, table_id, {"ld280-input": 5})

        # Every poll passes through the read client's own limiter (≥1.2 s apart), so the
        # settle window is paid for by the reads themselves and the arm never sleeps. The
        # loop stops EARLY only when every formula has arrived — stopping when *any* one has
        # is how a slow sibling gets mistaken for a dead one.
        polls = []
        for _ in range(LD280_POLLS):
            rows = [dict(record.fields or {})
                    for record in read.search_records(app_token, table_id)]
            polls.append(rows)
            if all(any(name in row for row in rows) for name in wanted):
                break

        record_ids = [record.record_id
                      for record in read.search_records(app_token, table_id)]
        batch = read.batch_get_records(app_token, table_id, record_ids)
        batch_rows = [dict(getattr(record, "fields", None) or {})
                      for record in (getattr(batch, "records", None) or ())]

        seen = {name: any(name in row for row in (polls[-1] + batch_rows)) for name in wanted}
        _record_ld280("formula_cell_read", {
            "created": created,
            "polls": len(polls),
            "cells_present_per_expression": seen,
            "constant_computes": seen["ld280-const"],
            "reference_computes": seen["ld280-ref"] or seen["ld280-bound"],
            "search_rows_final": polls[-1],
            "batch_get_rows": batch_rows,
            "keys_present_search": sorted({key for row in polls[-1] for key in row}),
            "keys_present_batch_get": sorted({key for row in batch_rows for key in row}),
            "listed_ui_types": sorted({field.ui_type or ""
                                       for field in read.list_fields(app_token, table_id)}),
        })
        print(f"\nLD280 FORMULA CELL PROBE after {len(polls)} polls, two read routes: {seen}")

        # The shipped row is bound to this observation, in BOTH directions.
        row = fa.FORMULA_EVALUATION
        assert row["constant_computes"] is seen["ld280-const"], (
            "the shipped FORMULA_EVALUATION row disagrees with the live probe — re-capture "
            "the row rather than editing this assertion")
        assert row["reference_computes"] is (seen["ld280-ref"] or seen["ld280-bound"]), (
            "a REFERENCING formula's cells now behave differently from the capture this "
            "library refuses on — re-capture the row")
        assert row["evidence"] == LD280_CAPTURE.name


def test_the_arm_stays_within_its_call_budget(credentials):
    """Gentleness is an assertion, not an intention."""
    schema = BaseSchemaClient.from_write_credentials()
    with base_write_harness.disposable_base() as (app_token, table_id, _title):
        schema.create_field(app_token, table_id, "ld262-budget", 1, ui_type="Text")
    assert schema.api_calls == 1, schema.api_calls
    assert schema.limiter is not None


def test_the_teardown_LEDGER_is_swept_and_every_survivor_is_NAMED(credentials):
    """The last word on cleanup, the shape every Base write arm ships."""
    left = base_write_harness.close_out()
    for entry in left:
        assert entry["app_token"] and entry["title"], entry
        assert base_write_harness.is_disposable_title(entry["title"]), entry
    remaining = base_write_harness.survivors()
    assert {e["app_token"] for e in remaining} == {e["app_token"] for e in left}
    if left:
        print(f"\nUNSWEPT DISPOSABLE BASES ({len(left)}) — re-run the sweep later:")
        for entry in left:
            print(f"  {entry['app_token']}  {entry['title']}  last code {entry['last_code']}")
    else:
        assert base_write_harness.orphans() == [], (
            "the orphan oracle must answer zero when the ledger is clean")
