"""THE SINGLE LIVE ARM for the guided column-type migration (LD-291).

``@pytest.mark.live_write``, deselected by default. Run it with::

    pytest -m live_write

**Against self-provisioned disposables, and nothing else.** Every Base this arm touches it made
itself, through :func:`base_write_harness.disposable_base`, and every one is in the harness's
ledger the moment it exists. It never touches a configured Base — ``LARKDOCIO_SCRATCH_BASE``
holds the only hand-authored ``Lookup`` / ``Email`` / ``Stage`` columns in existence and this
arm's whole subject is *deleting a populated column*, which is the last verb that should ever
meet a specimen the API cannot recreate. This module reads no such variable, which the offline
companion checks statically.

**What it proves that no offline test can.**

* **the whole sequence, live** — a populated ``Text`` column really becomes a populated
  ``Number`` column: values in, values out, the old column gone, the new one carrying the old
  name, and no staging column left behind;
* **the fence holds against a REAL defect** — the second arm forces the copy to write the wrong
  values (a wrapper over the shipped write client, so everything else is the real transport) and
  proves the delete is never attempted and the **source column is still standing with its
  original values**. That is the claim the whole operation rests on, and it is not one a fake
  client can settle;
* **the plan-time refusal costs nothing live either** — a column of prose asked to become a
  number refuses before a single call, on a real Base.

**It writes its own capture.** Both arms' observations go to
``dev/base-study/captures/ld291-01-guided-migration.json`` — the LD-262 precedent — so the
evidence is committed rather than described.

**Since LD-620 the write is REDIRECTED, and the corpus path is the ADDRESS it is aimed
at.** ``capture_sink.write_capture`` lands a re-run's reading in a run-scoped directory
outside every git working tree and says so out loud, because an armed ring overwrote committed
captures belonging to closed issues four times. A genuinely new measurement is landed as a
dated supersession by a human, never by a re-run.

**Gentle.** Under forty calls across both arms, every one through the shipped clients' own
limiter at the pace the probe packs sustained. Rate limits are not probed, and nothing here
sleeps.

**Skips loudly, never silently.** Without write credentials the module skips with a message
naming exactly what is missing.
"""
import json
from pathlib import Path

import base_write_harness
import capture_sink
import pytest

from larkdocio.base import field_migration as fm
from larkdocio.base import schema_ops_fields as sof
from larkdocio.base.client import BaseReadClient
from larkdocio.base.schema_apply import consent_to_destroy, schema_apply, schema_dry_run
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
           / "ld291-01-guided-migration.json")

_OBSERVED = {}

#: The column this arm authors, populates and then migrates. Named for the story so a survivor
#: in a swept ledger is traceable to it.
SOURCE_COLUMN = "ld291-estimate"

#: What goes into it — text that IS a number, which is the consumer's own case.
SOURCE_VALUES = ("11", "22", "33")


def _record(name, blob):
    _OBSERVED[name] = blob
    capture_sink.write_capture(CAPTURE, json.dumps({
        "_probe": "ld291-guided-column-type-migration",
        "_endpoint": ".../tables/{t}/fields + .../records/batch_update + .../records/search",
        "_method": "POST + PUT + DELETE",
        "_note": ("the five-step guided migration run end to end against a self-provisioned "
                  "disposable, and the SAME migration with the copy forced to write the wrong "
                  "values — which must leave the source column standing"),
        "_verdict": "OK",
        "observations": _OBSERVED,
    }, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def credentials():
    reason = base_write_harness.missing_reason()
    if reason:
        pytest.skip(reason)
    return True


class _MangledCopy:
    """The shipped write client with ONE defect injected: every value it is asked to write is
    written **one greater**.

    A wrapper rather than a stand-in, deliberately — every other call, every credential and the
    whole transport are the real ones, so what this arm forces is a *copy that did not
    round-trip* and nothing else.
    """

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def batch_update_records(self, app_token, table_id, updates):
        mangled = [(record_id, {name: (value + 1 if isinstance(value, (int, float))
                                       else str(value) + "!")
                                for name, value in (fields or {}).items()})
                   for record_id, fields in updates]
        return self._real.batch_update_records(app_token, table_id, mangled)


def _populated_base(schema, write, read):
    """A disposable Base whose one table carries a populated ``Text`` column.

    Returns ``(app_token, table_id)`` — the caller owns the ``disposable_base`` context.
    """
    def setup(app_token, table_id):
        plan = schema_dry_run([
            sof.create_field(app_token, table_id, SOURCE_COLUMN, 1, ui_type="Text",
                             revision=sof.table_revision(read, app_token, table_id))])
        log = schema_apply(plan, client=schema, read_client=read)
        assert [entry.outcome for entry in log.entries] == ["applied"], (
            log.entries[0].refusal.detail if log.entries[0].refusal else None)
        write.batch_create_records(
            app_token, table_id, [{SOURCE_COLUMN: value} for value in SOURCE_VALUES])
    return setup


def _cells(read, app_token, table_id, column):
    out = {}
    for record in (read.search_records(app_token, table_id) or ()):
        body = getattr(record, "fields", None) or {}
        if column in body:
            out[record.record_id] = body[column]
    return out


def _identity(read, app_token, table_id, column):
    for field in (read.list_fields(app_token, table_id) or ()):
        if getattr(field, "field_name", None) == column:
            return (getattr(field, "type", None), getattr(field, "ui_type", None))
    return None


def test_the_live_migration_rebuilds_a_populated_TEXT_column_as_a_NUMBER_column(credentials):
    """AC11's main arm: values in, values out, old column gone, new column named as the old."""
    schema = BaseSchemaClient.from_write_credentials()
    write = BaseWriteClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()

    with base_write_harness.disposable_base() as (app_token, table_id, title):
        assert base_write_harness.is_disposable_title(title)
        _populated_base(schema, write, read)(app_token, table_id)

        plan = fm.plan_field_migration(read, app_token, table_id, field_name=SOURCE_COLUMN,
                                       to_field_type=2, to_ui_type="Number")
        assert len(plan.values) == len(SOURCE_VALUES), plan.to_dict()
        assert plan.loss_preview["columns"][0]["cells_with_data"] == len(SOURCE_VALUES)
        assert plan.staging_name != SOURCE_COLUMN

        log = fm.apply_field_migration(plan, schema_client=schema, client=write,
                                       read_client=read, consent=consent_to_destroy(plan))
        outcomes = [entry.outcome for entry in log.entries]
        after = _cells(read, app_token, table_id, SOURCE_COLUMN)
        names = [getattr(f, "field_name", None) for f in read.list_fields(app_token, table_id)]
        identity = _identity(read, app_token, table_id, SOURCE_COLUMN)
        _record("migration_end_to_end", {
            "source_values": list(SOURCE_VALUES),
            "staging_column": plan.staging_name,
            "outcomes": outcomes,
            "halt": log.halt,
            "columns_after": names,
            "identity_after": list(identity) if identity else None,
            "cells_after": {k: str(v) for k, v in after.items()},
        })

        assert outcomes == ["applied"] * 5, log.to_dict()
        assert log.halt is None
        assert SOURCE_COLUMN in names, names
        assert plan.staging_name not in names, "the staging column must not survive"
        assert identity == (2, "Number"), identity
        assert sorted(float(value) for value in after.values()) == [11.0, 22.0, 33.0], after


def test_a_copy_that_did_NOT_round_trip_leaves_the_SOURCE_COLUMN_STANDING(credentials):
    """AC4, live and against a forced defect: nothing is destroyed on an unverified copy."""
    schema = BaseSchemaClient.from_write_credentials()
    write = BaseWriteClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()

    with base_write_harness.disposable_base() as (app_token, table_id, _title):
        _populated_base(schema, write, read)(app_token, table_id)
        before = _cells(read, app_token, table_id, SOURCE_COLUMN)

        plan = fm.plan_field_migration(read, app_token, table_id, field_name=SOURCE_COLUMN,
                                       to_field_type=2, to_ui_type="Number")
        log = fm.apply_field_migration(plan, schema_client=schema,
                                       client=_MangledCopy(write), read_client=read,
                                       consent=consent_to_destroy(plan))
        outcomes = [entry.outcome for entry in log.entries]
        names = [getattr(f, "field_name", None) for f in read.list_fields(app_token, table_id)]
        after = _cells(read, app_token, table_id, SOURCE_COLUMN)
        _record("forced_mismatch_halts", {
            "outcomes": outcomes,
            "verification_refusal": (log.entries[2].refusal.reason
                                     if log.entries[2].refusal else None),
            "columns_after": names,
            "source_cells_before": {k: str(v) for k, v in before.items()},
            "source_cells_after": {k: str(v) for k, v in after.items()},
            "recovery": (log.halt or {}).get("recovery"),
        })

        assert outcomes[:2] == ["applied", "applied"], log.to_dict()
        assert outcomes[2] == "refused", log.to_dict()
        assert outcomes[3:] == ["not-attempted", "not-attempted"], log.to_dict()
        assert "does not hold" in log.entries[2].refusal.detail
        # THE CLAIM: nothing was destroyed. The source column is listed, with its own values.
        assert SOURCE_COLUMN in names, names
        assert {k: str(v) for k, v in after.items()} == {
            k: str(v) for k, v in before.items()}, "the source column's values must be intact"
        assert (log.halt or {})["recovery"]["source_column_present"] is True


def test_a_column_of_PROSE_asked_to_become_a_NUMBER_refuses_live_before_any_call(credentials):
    """AC8 on a real Base: the refusal happens at plan time and costs nothing."""
    schema = BaseSchemaClient.from_write_credentials()
    write = BaseWriteClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()

    with base_write_harness.disposable_base() as (app_token, table_id, _title):
        plan = schema_dry_run([
            sof.create_field(app_token, table_id, "ld291-prose", 1, ui_type="Text",
                             revision=sof.table_revision(read, app_token, table_id))])
        assert [e.outcome for e in schema_apply(plan, client=schema,
                                                read_client=read).entries] == ["applied"]
        write.batch_create_records(app_token, table_id,
                                   [{"ld291-prose": "not a number"}])

        with pytest.raises(fm.UntranscodableValueError) as caught:
            fm.plan_field_migration(read, app_token, table_id, field_name="ld291-prose",
                                    to_field_type=2, to_ui_type="Number")
        _record("plan_time_refusal", {"message": str(caught.value)[:400]})
        assert "not a number" in str(caught.value)
        # And the column is untouched — a refusal that had sent anything would show here.
        assert "ld291-prose" in [getattr(f, "field_name", None)
                                 for f in read.list_fields(app_token, table_id)]
