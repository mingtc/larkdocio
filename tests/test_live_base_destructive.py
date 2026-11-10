"""THE SINGLE LIVE DESTRUCTIVE ARM — the cross-table loss preview, proved on a real Base.

``@pytest.mark.live_write``, deselected by default. Run it with::

    pytest -m live_write

**Against a self-provisioned disposable, and nothing else — and on this arm that fence is the
sharpest in the suite.** The verbs here are ``DELETE …/fields/{f}``, ``DELETE …/tables/{t}`` and
``POST …/tables/batch_delete``: one misdirected app token would destroy specimens no probe can
regenerate. The configured Scratch Base holds the only hand-authored ``Lookup`` / ``Email`` /
``Stage`` columns in existence, **the API cannot recreate any of the three**, and it is a READ
fixture. Every Base this arm writes it made itself: most through
:func:`base_write_harness.disposable_base`, and one by **copying** that read fixture — the Lookup
leg, because the field API cannot author a ``Lookup`` at all, so no Base built from scratch will
ever carry one. A copy creates a *new* app: the template is a copy source and a read source, is
never handed to a mutating verb, and the copy is ledgered the instant its token exists like every
other disposable. The first test below asserts the token it writes is not the configured one
whatever that variable holds. The offline companion checks the same claims statically.

**What it proves that no offline test can.**

* **THE TWO-TABLE DUPLEX DELETE, WITH THE MIRROR'S DISAPPEARANCE ASSERTED IN THE *OTHER*
  TABLE.** A ``DuplexLink`` is built live between two tables the arm creates, the preview is read
  before anything is deleted — it must name **both** columns and **both** tables — and after the
  delete the mirror is asserted **gone from the second table**, which is the whole reason this
  rung's preview is app-scoped;
* **A TABLE DELETE WHOSE PREVIEW NAMES AN INBOUND LINK IN A THIRD TABLE**, and the dangling that
  follows it: the surviving link keeps the dead table's ``table_id``, loses its ``table_name``,
  and the table it lives in still reads ``code:0`` with no error anywhere;
* **A TABLE DELETE THAT BLANKS AN INBOUND *LOOKUP*, PREDICTED BEFORE IT HAPPENS.** A Lookup
  mirrors another table without carrying a link into it, so this is the loss a link-only scan
  could not see: the preview names the column and the count it holds **before** the delete, and
  afterwards the column is still there, still naming the dead table, and empty on every row —
  the predicted loss and the observed one, measured on the same column;
* **THE OUT-OF-BAND REFUSAL.** A delete plan is built, the referenced table is removed **behind
  the plan's back**, and the arm asserts the engine **refuses** rather than applying half of it;
* **THE PROTECTED-LAST FLOOR**, live: the Base's last table answers ``1254034`` and the batch
  continues past it;
* **THE SELECT-OPTION SHRINK, BOTH SIDES AND ITS CONTROL.** ``PUT …/fields/{f}`` replaces a
  select column's option set, so a body keeping every survivor's ``id`` and omitting one destroys
  the cells that held it — the shape the structural fence passes. The populated shrink is
  **refused** from a default apply, with every cell asserted still in place; with consent it
  applies and the loss is compared to the preview **record for record**; the unpopulated shrink
  applies with a measured-EMPTY preview and no token; and the same body sent through the
  unplanned client route — **the gate removed** — destroys the cells silently, which is what
  makes the gate a gate over a real defect;
* **THE OBJECT-GONE ORACLE AGREES WITH THE HARNESS'S OWN.** The shipped
  ``OBJECT_GONE_CODES`` and the harness's zero-orphan codes are asserted equal here rather than
  imported across the boundary — the library cannot import from ``tests/``.

**Nothing here uploads media.** An uploaded ``bitable_file`` / ``bitable_image`` token has no
purge verb at all, so a live arm that minted one would leave residue nothing can remove.

**Gentle.** Around sixty calls at ≥1.2 s spacing. Rate limits are not probed.

**Skips loudly, never silently.**
"""
import os
import time

import base_write_harness
import pytest

from log_reading_apply import reading_the_log
from larkdocio.base import computed
from larkdocio.base import schema_ops_destructive as destructive
from larkdocio.base import schema_ops_fields as sof
from larkdocio.base.client import BaseReadClient
from larkdocio.base.loss_preview import OBJECT_GONE_CODES
from larkdocio.base.plan import Refusal
from larkdocio.base.schema_apply import (
    DestructiveConsentRequired,
    consent_to_destroy,
    schema_apply,
    schema_dry_run,
)
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.base.schema_plan import batch_create_tables, create_table
from larkdocio.base.schema_settle import settle
from larkdocio.base.write_client import BaseWriteClient

# This gate's subject is the LOG — which entry landed, which refused, with which typed
# reason — not the return-vs-raise policy (pinned offline in
# tests/test_apply_refusal_policy.py, proved live in
# tests/test_live_write_refusal_policy_gate.py). So it opts into partial application
# once, here, the same way the offline log-reading suites do.
schema_apply = reading_the_log(schema_apply)

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


@pytest.fixture(scope="module")
def credentials():
    reason = base_write_harness.missing_reason()
    if reason:
        pytest.skip(reason)
    return True


@pytest.fixture(scope="module")
def template_app_token():
    """The app token of the Base the Lookup leg COPIES FROM — a template and a read source.

    Nothing in this module writes to it: the copy creates a new app, that app is the only thing
    the leg reads, deletes inside, or deletes, and the companion checks statically that the
    template never reaches a mutating verb. It is needed at all because the field API cannot
    author a ``Lookup`` column, so no Base this arm builds from scratch will ever contain one.
    """
    url = canary_support.scratch_base_url()
    if not url:
        pytest.skip(
            "no template Base configured — set LARKDOCIO_SCRATCH_BASE to a Base that carries "
            "a hand-authored Lookup column. The field API cannot author one, so without a "
            "template there is no live Lookup whose silent blanking can be measured.")
    _domain, token = canary_support.parse_base_url(url)
    return token


def _clients():
    return BaseSchemaClient.from_write_credentials(), BaseReadClient.from_read_credentials()


def _column_reading(read, app_token, table_id, field_name):
    """One column, in ONE read: ``(rows whose key is present, rows a reader would SEE a value
    in)``.

    The two measures are kept apart on purpose, and they are no longer the same number. A
    computed cell arrives as a typed wrapper, so an emptied one can read as an absent key *or*
    as a wrapper carrying nothing — both are blank to a reader, and the visible half is what
    the blanking claim is about. The preview's ``cells_with_data`` is asserted against **that**
    half: since the wrapper over-count was fixed, a present key holding an empty wrapper is no
    longer counted as data, so the number the preview reports is how many cells a reader would
    see a value in, not how many keys are present.
    """
    present, visible = 0, []
    for record in read.search_records(app_token, table_id):
        fields = getattr(record, "fields", None) or {}
        if field_name not in fields:
            continue
        present += 1
        value = fields[field_name]
        if isinstance(value, dict):
            value = value.get("value")
        if value:
            visible.append(value)
    return present, visible


def _await_column(read, app_token, table_id, field_name, *, holding,
                  attempts=6, spacing=8.0):
    """Read one column until it HOLDS values (``holding=True``) or holds none, bounded.

    A computed column's cells are the server's own recomputation and they move on the server's
    schedule, in both directions: a copy answers ``code:0`` for the app before the mirrored
    values are back, and the blanking that follows a delete lands the same way. Neither is an
    op *still in flight* — there is no ``1254036`` to poll on — so the shipped settle contract
    does not cover this and a bounded wait does. Measured on this tenant: the copy's Lookup
    cells were there on the second look, about eight seconds after the copy settled.

    The budget is small and the caller reports the reading it ended with, so a spent budget is
    a visible disagreement rather than a silent pass.
    """
    present, visible = _column_reading(read, app_token, table_id, field_name)
    for attempt in range(2, attempts + 1):
        if bool(visible) is holding:
            break
        time.sleep(spacing)
        present, visible = _column_reading(read, app_token, table_id, field_name)
    return present, visible


def _table_ids(read, app_token):
    return {table.table_id: table.name for table in read.list_tables(app_token)}


def _fields(read, app_token, table_id):
    return {field.field_id: field.field_name
            for field in read.list_fields(app_token, table_id)}


def _make_tables(schema, read, app_token, names):
    """Create tables and hand back ``{name: table_id}``, verified through the plan gate."""
    log = schema_apply(schema_dry_run([batch_create_tables(app_token, list(names),
                                                  accept_locale_default_primary=True)]),
                       client=schema, read_client=read)
    assert log.entries[0].outcome == "applied", log.entries[0].refusal
    listed = _table_ids(read, app_token)
    return {listed[table_id]: table_id for table_id in log.entries[0].created_table_ids}


def test_this_arm_NEVER_TOUCHES_THE_CONFIGURED_SCRATCH_BASE(credentials):
    """The binding fence, asserted at runtime as well as statically. This is the arm whose
    verbs could destroy the hand-authored specimens, so the check is not ceremony."""
    configured = (os.environ.get("LARKDOCIO_SCRATCH_BASE") or "").strip()
    with base_write_harness.disposable_base() as (app_token, _table_id, title):
        assert base_write_harness.is_disposable_title(title)
        assert app_token, "the harness always yields a token"
        if configured:
            assert app_token not in configured and configured not in app_token, (
                "the destructive arm must never write the configured READ fixture")


def test_THE_OBJECT_GONE_ORACLE_is_the_HARNESSS_OWN_and_not_a_second_opinion(credentials):
    """The shipped codes and the zero-orphan oracle's codes are one set. Asserted rather than
    imported: ``src/larkdocio`` cannot import from ``tests/``, so agreement is a test's job."""
    assert set(OBJECT_GONE_CODES) == (set(base_write_harness.DELETED_CODES)
                                      | set(base_write_harness.TABLE_DELETED_CODES))


def test_THE_TWO_TABLE_DUPLEX_DELETE_takes_the_MIRROR_IN_THE_OTHER_TABLE(credentials):
    """The rung's headline, end to end: the preview names both columns before anything happens,
    and the mirror really disappears from the table the caller never named."""
    schema, read = _clients()
    with base_write_harness.disposable_base() as (app_token, main_id, _title):
        made = _make_tables(schema, read, app_token, ["ld265-ref"])
        ref_id = made["ld265-ref"]

        # A two-way link from the default table into the one just made. The mirror lands in
        # ld265-ref by itself, in this same call.
        source = schema.create_field(app_token, main_id, "DLink", 21, ui_type="DuplexLink",
                                     properties={"table_id": ref_id, "multiple": True})
        source_id = source.field_id
        mirror_ids = set(_fields(read, app_token, ref_id))
        assert mirror_ids, "the mirror column must exist before the delete is planned"

        plan = schema_dry_run(
            [destructive.delete_field(app_token, main_id, source_id)], read_client=read)
        loss = plan.entries[0].loss_preview
        assert loss is not None, plan.entries[0].refusal
        tables = [column["table_id"] for column in loss["columns"]]
        assert tables == [main_id, ref_id], (
            "THE PREVIEW NAMES BOTH TABLES — the mirror is in the one the caller did not name")
        print(f"\ncross-table loss preview: {[c['field_name'] for c in loss['columns']]} "
              f"in tables {tables}, cells "
              f"{[c['cells_with_data'] for c in loss['columns']]}")

        mirror_id = loss["mirror"]["field_id"]
        log = schema_apply(plan, client=schema, read_client=read,
                           consent=consent_to_destroy(plan))
        assert log.entries[0].outcome == "applied", log.entries[0].refusal
        assert source_id not in _fields(read, app_token, main_id)
        assert mirror_id not in _fields(read, app_token, ref_id), (
            "THE MIRROR IS GONE FROM THE OTHER TABLE — the measured two-table delete")


def test_A_TABLE_DELETE_PREVIEWS_AN_INBOUND_LINK_IN_A_THIRD_TABLE_and_DANGLES_IT(credentials):
    """The silent half. The preview names a link living in a table the caller never mentioned,
    and afterwards that link survives, dangling, with no error anywhere."""
    schema, read = _clients()
    with base_write_harness.disposable_base() as (app_token, main_id, _title):
        made = _make_tables(schema, read, app_token, ["ld265-target", "ld265-third"])
        target_id, third_id = made["ld265-target"], made["ld265-third"]

        schema.create_field(app_token, main_id, "MainLink", 18, ui_type="SingleLink",
                            properties={"table_id": target_id, "multiple": True})
        third_link = schema.create_field(app_token, third_id, "ThirdLink", 18,
                                         ui_type="SingleLink",
                                         properties={"table_id": target_id, "multiple": True})

        plan = schema_dry_run([destructive.delete_table(app_token, target_id)],
                              read_client=read)
        loss = plan.entries[0].loss_preview
        assert loss is not None, plan.entries[0].refusal
        inbound = {(row["table_id"], row["field_name"]) for row in loss["inbound_links"]}
        assert (third_id, "ThirdLink") in inbound and (main_id, "MainLink") in inbound, inbound
        print(f"\ninbound links previewed in {len(loss['other_tables'])} other table(s): "
              f"{sorted(inbound)}")

        log = schema_apply(plan, client=schema, read_client=read,
                           consent=consent_to_destroy(plan))
        assert log.entries[0].outcome == "applied", log.entries[0].refusal

        survivors = [field for field in read.list_fields(app_token, third_id)
                     if field.field_id == third_link.field_id]
        assert survivors, "the inbound link SURVIVES a target-table delete"
        prop = survivors[0].property
        assert getattr(prop, "table_id", None) == target_id
        assert not getattr(prop, "table_name", None), (
            "and it DANGLES: table_id kept, table_name dropped — the detector, live")
        assert read.search_records(app_token, third_id) is not None, (
            "and the table it lives in still reads with no error at all")


def test_AN_OUT_OF_BAND_REMOVAL_makes_the_NEXT_PLAN_REFUSE_rather_than_half_apply(credentials):
    """The plan is built against a Base that then moves underneath it. The engine refuses,
    typed, with zero writes — it does not delete what it can and report the rest."""
    schema, read = _clients()
    with base_write_harness.disposable_base() as (app_token, _main_id, _title):
        made = _make_tables(schema, read, app_token, ["ld265-doomed"])
        doomed = made["ld265-doomed"]

        # Removed out of band, exactly as another client would.
        schema.delete_table(app_token, doomed)

        plan = schema_dry_run([destructive.delete_table(app_token, doomed)], read_client=read)
        assert plan.entries[0].refusal is not None
        assert plan.entries[0].refusal.reason == Refusal.LOSS_NOT_ENUMERABLE
        with pytest.raises(DestructiveConsentRequired):
            consent_to_destroy(plan)
        print(f"\nout-of-band removal → typed refusal: "
              f"{plan.entries[0].refusal.detail[:120]}…")


def test_THE_PROTECTED_LAST_TABLE_answers_1254034_and_the_BATCH_CONTINUES(credentials):
    """``1254034`` live, and its entry-scoped classification exercised through the engine: the
    refusal is about that table and the next entry still runs."""
    schema, read = _clients()
    with base_write_harness.disposable_base() as (app_token, main_id, _title):
        made = _make_tables(schema, read, app_token, ["ld265-spare"])
        spare = made["ld265-spare"]
        # Reduce to one table so the next delete meets the floor.
        schema.delete_table(app_token, spare)
        remaining = list(_table_ids(read, app_token))
        assert remaining == [main_id], remaining

        plan = schema_dry_run([destructive.delete_table(app_token, main_id),
                               create_table(app_token, "ld265-after", primary_field_name="Title")], read_client=read)
        log = schema_apply(plan, client=schema, read_client=read,
                           consent=consent_to_destroy(plan))
        assert log.entries[0].outcome == "refused"
        assert "1254034" in (log.entries[0].refusal.detail or "")
        assert log.entries[1].outcome == "applied", "the batch CONTINUED past the floor"
        assert log.halt is None
        print(f"\nprotected-last floor, live: {log.entries[0].refusal.detail[:110]}…")


def test_A_BATCH_DELETE_is_verified_in_ONE_read_back_over_every_id(credentials):
    schema, read = _clients()
    with base_write_harness.disposable_base() as (app_token, _main_id, _title):
        made = _make_tables(schema, read, app_token, ["ld265-a", "ld265-b"])
        ids = [made["ld265-a"], made["ld265-b"]]

        plan = schema_dry_run([destructive.batch_delete_tables(app_token, ids)],
                              read_client=read)
        assert plan.loss_preview_cost["read_calls"] >= 4
        log = schema_apply(plan, client=schema, read_client=read,
                           consent=consent_to_destroy(plan))
        assert log.entries[0].outcome == "applied", log.entries[0].refusal
        assert log.entries[0].read_back["still_listed"] == []
        assert not (set(ids) & set(_table_ids(read, app_token)))


def test_A_TABLE_DELETE_BLANKS_AN_INBOUND_LOOKUP_and_THE_PREVIEW_NAMES_IT_FIRST(
        credentials, template_app_token):
    """The COMPUTED half of the blast radius, live — the class a link-only scan could not see.

    A Lookup mirrors another table **without carrying a link into it**, so deleting the table it
    rolls up from leaves the column standing and empties it, on every row, with no error
    anywhere. That was measured behind a preview that named only link columns; this leg is the
    inversion of it, and it is the one leg here whose Base is a COPY rather than a fresh
    disposable, because the field API cannot author a Lookup at all — copying a Base that has
    one is the only route to a live one.

    **The template is a copy SOURCE and a read source, and nothing else.** The copy is a
    disposable: ledgered the instant its token exists, deleted in a ``finally``, and swept with
    the rest. Every verb below takes the copy's token.

    Three things are asserted that no offline test can: the preview NAMES the inbound Lookup
    **before** anything is deleted, with the count it read at plan time; the column SURVIVES
    the delete still naming the dead table; and the values it held are gone afterwards — the
    observed loss matching the predicted one, which is the whole claim a preview makes.
    """
    schema, read = _clients()
    title = base_write_harness.disposable_title()
    ledger = base_write_harness.Ledger()
    dest_folder = canary_support.require_disposables_folder()
    token = schema.copy_app(template_app_token, title, folder_token=dest_folder).app_token
    # Recorded BEFORE anything else can fail: an unrecorded disposable is a lost one.
    ledger.record_create(token, title)
    try:
        assert token and token != template_app_token, (
            "the copy answered with the template's own token — this leg would then be "
            "DELETING A TABLE OF THE TEMPLATE, which is the one thing it must never do")
        outcome = settle(lambda: read.get_app(token))
        assert outcome.settled, outcome.detail

        host_id = doomed_id = lookup = None
        for table_id in _table_ids(read, token):
            for field in read.list_fields(token, table_id):
                target = computed.target_table(field)
                if target:
                    host_id, doomed_id, lookup = table_id, target, field
                    break
            if lookup is not None:
                break
        assert lookup is not None, (
            "the copy carries no placeable Lookup column, so this leg would prove nothing "
            "about the loss it exists to measure — the template no longer has one, or the "
            "provenance the preview reads no longer survives the read client's typed door")

        present, before = _await_column(read, token, host_id, lookup.field_name,
                                        holding=True)
        assert before, (
            "the Lookup column holds no values even before the delete — the blanking below "
            "would then be unobservable and this leg would pass on nothing")

        plan = schema_dry_run([destructive.delete_table(token, doomed_id)], read_client=read)
        loss = plan.entries[0].loss_preview
        assert loss is not None, plan.entries[0].refusal
        named = {(row["field_id"], row["table_id"], row["rolls_up_from_table"]): row
                 for row in loss["inbound_lookups"]}
        key = (lookup.field_id, host_id, doomed_id)
        assert key in named, (
            "THE PREVIEW DOES NOT NAME THE INBOUND LOOKUP — the column about to be emptied is "
            f"absent from the blast radius it is in: {sorted(named)}")
        assert named[key]["cells_with_data"] == len(before), (
            "the count the preview reports is how many cells HOLD A VALUE — a present key over "
            f"an empty wrapper is not data (keys present here: {present})")
        assert host_id in loss["other_tables"], (
            "and the table it lives in is named as reached, though the caller never named it")
        print(f"\nPREVIEW names the inbound Lookup {lookup.field_name!r} ({lookup.field_id}) "
              f"in {host_id}, rolling up from {doomed_id}, "
              f"{named[key]['cells_with_data']} cells; effect: {named[key]['effect'][:80]}…")

        log = schema_apply(plan, client=schema, read_client=read,
                           consent=consent_to_destroy(plan))
        assert log.entries[0].outcome == "applied", log.entries[0].refusal

        survivors = {field.field_id: field for field in read.list_fields(token, host_id)}
        assert lookup.field_id in survivors, (
            "the Lookup column SURVIVES the delete — it is emptied, not destroyed")
        assert computed.target_table(survivors[lookup.field_id]) == doomed_id, (
            "and its configuration still names the table that is now gone")
        present_after, after = _await_column(read, token, host_id, lookup.field_name,
                                             holding=False)
        assert after == [], (
            f"THE PREDICTED LOSS IS THE OBSERVED ONE: {len(before)} cells held a value before "
            f"and none does now — instead {len(after)} still do")
        assert read.search_records(token, host_id) is not None, (
            "and the table it lives in still reads with no error at all — the silence")
        print(f"OBSERVED loss: visible values {len(before)} -> {len(after)}; keys present "
              f"{present} -> {present_after}; column survives={lookup.field_id in survivors}")
    finally:
        # `adopt_from_ledger` is the one route into the provisioner's allow-list that is not a
        # create in this process, and it re-checks the disposable title — so the copy is
        # sweepable while the template, which is in no ledger, cannot be addressed at all.
        provisioner = base_write_harness._Provisioner().adopt_from_ledger(ledger)
        deleted, code = provisioner.delete(token)
        ledger.record_delete(token, code, deleted)


def _select_column(read, app_token, table_id, field_name):
    """One select column's ``(field_id, [{id, name, color}, …])``, read from the server."""
    for field in read.list_fields(app_token, table_id):
        if field.field_name == field_name:
            return field.field_id, [{"id": option.id, "name": option.name,
                                     "color": option.color}
                                    for option in (field.property.options or ())]
    raise AssertionError(f"{field_name!r} is not in table {table_id}")


def _select_cells(read, app_token, table_id, field_name):
    """``{record_id: cell}`` for every row that HOLDS a value in one select column."""
    holding = {}
    for record in read.search_records(app_token, table_id):
        value = (getattr(record, "fields", None) or {}).get(field_name)
        if value:
            holding[record.record_id] = value
    return holding


def test_A_POPULATED_OPTION_SHRINK_IS_REFUSED_and_WITH_CONSENT_matches_the_preview_RECORD_FOR_RECORD(
        credentials):
    """LD-462, both sides on one column. ``PUT …/fields/{f}`` replaces the option set, so a body
    that keeps every survivor's ``id`` and omits one destroys the cells that held it — the shape
    LD-339's structural fence passes. The preview must name those records BEFORE anything is
    sent, a default apply must REFUSE, and the destruction that follows consent must be exactly
    what the preview said, record for record."""
    schema, read = _clients()
    write = BaseWriteClient.from_write_credentials()
    with base_write_harness.disposable_base() as (app_token, main_id, _title):
        schema.create_field(app_token, main_id, "Priority", 3, ui_type="SingleSelect",
                            properties={"options": [{"name": "P1", "color": 0},
                                                    {"name": "P2", "color": 1},
                                                    {"name": "P3", "color": 2}]})
        write.batch_create_records(app_token, main_id, [
            {"Priority": "P1"}, {"Priority": "P3"}, {"Priority": "P3"}])
        field_id, options = _select_column(read, app_token, main_id, "Priority")
        before = _select_cells(read, app_token, main_id, "Priority")
        assert sorted(before.values()) == ["P1", "P3", "P3"], before

        keep = [option for option in options if option["name"] != "P3"]
        plan = schema_dry_run([sof.update_field(app_token, main_id, field_id, "Priority", 3,
                                                ui_type="SingleSelect",
                                                properties={"options": keep})],
                             read_client=read)
        loss = plan.entries[0].loss_preview
        assert loss is not None, plan.entries[0].refusal
        assert plan.destructive is True
        predicted = {row["record_id"]: row["values_lost"] for row in loss["records"]}
        assert set(predicted) == {rid for rid, value in before.items() if value == "P3"}, (
            "THE PREVIEW NAMES THE RECORDS THAT LOSE A VALUE, before anything is sent")
        print(f"\npredicted loss: {loss['records_affected']} record(s), "
              f"{loss['values_lost']} value(s): {predicted}")

        # THE REFUSAL: the same plan, applied from a default call, sends nothing.
        with pytest.raises(DestructiveConsentRequired) as excinfo:
            schema_apply(plan, client=schema, read_client=read)
        assert "consent_to_destroy(plan)" in str(excinfo.value)
        assert _select_cells(read, app_token, main_id, "Priority") == before, (
            "a refused apply must leave every cell exactly where it was")

        log = schema_apply(plan, client=schema, read_client=read,
                           consent=consent_to_destroy(plan))
        assert log.entries[0].outcome == "applied", log.entries[0].refusal
        after = _select_cells(read, app_token, main_id, "Priority")
        assert set(before) - set(after) == set(predicted), (
            "THE OBSERVED LOSS IS THE PREDICTED LOSS, record for record")
        assert after == {rid: value for rid, value in before.items() if value != "P3"}
        _field_id, survivors = _select_column(read, app_token, main_id, "Priority")
        assert [option["name"] for option in survivors] == ["P1", "P2"]
        print(f"observed loss: {sorted(set(before) - set(after))} — the preview's own list")


def test_AN_UNPOPULATED_OPTION_SHRINK_APPLIES_UNTOUCHED_and_the_GATE_REMOVED_CONTROL_DESTROYS(
        credentials):
    """The counterweight and the control, on one Base.

    **Arm 1 — nothing to lose, nothing to consent to.** Dropping an option no record holds is a
    schema tidy-up: the preview comes back explicitly EMPTY and measured, the apply needs no
    token, and every cell is byte-identical afterwards.

    **Arm 2 — the gate REMOVED, so the defect reproduces.** The same shrink body, on a
    populated column, sent through ``BaseSchemaClient.update_field`` directly — the unplanned
    route, which is what the library's own planned route did before this gate existed. The cells
    are destroyed, silently, with a success answer: proof the gate is over a real destruction
    rather than a hypothetical one."""
    schema, read = _clients()
    write = BaseWriteClient.from_write_credentials()
    with base_write_harness.disposable_base() as (app_token, main_id, _title):
        for name in ("Quiet", "Control"):
            schema.create_field(app_token, main_id, name, 3, ui_type="SingleSelect",
                                properties={"options": [{"name": "X", "color": 0},
                                                        {"name": "Y", "color": 1},
                                                        {"name": "Z", "color": 2}]})
        write.batch_create_records(app_token, main_id, [
            {"Quiet": "X", "Control": "X"}, {"Quiet": "Y", "Control": "Z"}])

        # ---- arm 1: the shrink that destroys nothing ------------------------- #
        quiet_id, options = _select_column(read, app_token, main_id, "Quiet")
        before = _select_cells(read, app_token, main_id, "Quiet")
        plan = schema_dry_run(
            [sof.update_field(app_token, main_id, quiet_id, "Quiet", 3, ui_type="SingleSelect",
                              properties={"options": [option for option in options
                                                      if option["name"] != "Z"]})],
            read_client=read)
        loss = plan.entries[0].loss_preview
        assert loss is not None and loss["destroys"] is False, plan.entries[0].refusal
        assert loss["records"] == [] and plan.destructive is False
        log = schema_apply(plan, client=schema, read_client=read)
        assert log.entries[0].outcome == "applied", log.entries[0].refusal
        assert _select_cells(read, app_token, main_id, "Quiet") == before, (
            "an UNPOPULATED shrink applies and touches nothing")
        print(f"\nunpopulated shrink: measured-empty preview, applied, cells {before} unchanged")

        # ---- arm 2: the same body with the gate removed ---------------------- #
        control_id, options = _select_column(read, app_token, main_id, "Control")
        held = _select_cells(read, app_token, main_id, "Control")
        assert "Z" in held.values(), "the control column must hold the option being dropped"
        schema.update_field(app_token, main_id, control_id, "Control", 3,
                            ui_type="SingleSelect",
                            properties={"options": [option for option in options
                                                    if option["name"] != "Z"]})
        left = _select_cells(read, app_token, main_id, "Control")
        assert set(held) - set(left) == {rid for rid, value in held.items() if value == "Z"}, (
            "GATE REMOVED: the destruction reproduces — the same body, sent without a plan, "
            "empties the cells that held the dropped option and answers success")
        print(f"gate-removed control: {sorted(set(held) - set(left))} destroyed silently")


# --------------------------------------------------------------------------- #
# THE WHOLE-OBJECT DELETE (LD-466) — the doctrine's own exit, proved on itself.  #
# --------------------------------------------------------------------------- #

def test_THE_WHOLE_BASE_DELETE_lands_PROVES_GONE_and_does_NOT_LIE_on_a_repeat(credentials):
    """The shipped ``delete_base``, end to end on a Base this arm created and nothing else.

    Four assertions, in the only order that means anything:

    1. the Base is **readable** first — otherwise "gone afterwards" proves nothing;
    2. the delete is accepted (its ``code:0`` is acceptance, and that is all it is);
    3. **the re-read is the proof.** ``GET …/apps/{a}`` must now raise carrying a code the
       shipped predicate forgives, and that predicate is asserted against the harness's own
       zero-orphan oracle in the sibling leg below rather than trusted;
    4. a **second** delete raises rather than reporting success — the one outcome a ``finally``
       forgives, and the reason the verb is deliberately not idempotent.

    The token is deleted here rather than by the harness's ``finally``, which is the point: the
    shipped verb does the cleanup and the harness's sweep then finds nothing to do.
    """
    from larkdocio.base.schema_client import base_is_gone
    from larkdocio.errors import LarkAPIError

    schema, read = _clients()
    with base_write_harness.disposable_base() as (app_token, main_id, _title):
        assert read.get_app(app_token) is not None, "a Base that was never readable proves nothing"
        assert list(_table_ids(read, app_token)) == [main_id]

        schema.delete_base(app_token)                       # (2) accepted

        with pytest.raises(LarkAPIError) as gone:           # (3) THE PROOF
            read.get_app(app_token)
        assert base_is_gone(gone.value), (
            f"the re-read raised {gone.value.code!r}, which the shipped predicate does not "
            f"recognise as gone — either the code changed or the predicate is wrong")
        print(f"\nwhole-Base delete → re-read proves gone: code {gone.value.code}")

        with pytest.raises(LarkAPIError) as again:          # (4) no silent success
            schema.delete_base(app_token)
        assert base_is_gone(again.value), again.value.code
        assert again.value.code != gone.value.code, (
            "the two endpoints answer with DIFFERENT codes and that is exactly why one "
            "predicate spans both — if they have converged, say so and simplify deliberately")
        print(f"second delete → {again.value.code}, forgiven rather than faked")


def test_THE_DISPOSABLES_DOCTRINE_IS_FOLLOWABLE_a_try_finally_LEAVES_NO_RESIDUE(credentials):
    """The payoff, and the whole reason the verb was filed: a ``try``/``finally`` disposable-Base
    block that leaves the tenant as it found it, using ONLY shipped calls.

    This is the guide's own recipe run against the real API — create, use, `finally`-delete
    forgiving *already gone* and nothing else, then confirm from the bitable side. The body
    **raises deliberately**, because a teardown that only works on the happy path is not a
    teardown; the exception is caught outside the block and the residue check runs anyway.
    """
    from larkdocio.base.schema_client import base_is_gone
    from larkdocio.errors import LarkAPIError

    schema, read = _clients()
    title = base_write_harness.disposable_title("ld466-doctrine")
    dest_folder = canary_support.require_disposables_folder()
    app = schema.create_app(title, time_zone="Asia/Singapore", folder_token=dest_folder)
    app_token = app.app_token
    # Ledgered the instant the token exists, exactly as the harness does: a create whose token
    # is not recorded is residue nothing can name if the delete below never lands.
    ledger = base_write_harness.Ledger()
    ledger.record_create(app_token, title)
    confirmed_gone = False
    try:
        try:
            assert read.get_app(app_token) is not None
            raise RuntimeError("the body fails on purpose — the teardown must still run")
        finally:
            try:
                schema.delete_base(app_token)
            except LarkAPIError as exc:
                if not base_is_gone(exc):
                    raise
    except RuntimeError:
        pass

    try:
        read.get_app(app_token)
    except LarkAPIError as exc:
        confirmed_gone = base_is_gone(exc)
    ledger.record_delete(app_token, None, confirmed_gone)
    assert confirmed_gone, (
        "the finally-delete did not leave the Base gone — the doctrine is not followable and the "
        "token is on the ledger for the sweep")
    print(f"\ntry/finally disposable Base: created, body raised, deleted, gone — {app_token}")


def test_THE_GONE_PREDICATE_agrees_with_the_HARNESSS_OWN_codes_rather_than_a_second_opinion(
        credentials):
    """``src/larkdocio`` cannot import from ``tests/``, so the two definitions of *gone* for a
    whole Base are held equal here — the same shape the object-gone leg above uses for tables.

    The shipped ``BASE_GONE_CODES`` must be exactly the bitable oracle the harness's zero-orphan
    check uses, plus the Drive endpoint's already-deleted code the harness forgives in its own
    ``finally``. A third number appearing on either side is a second opinion about the same
    question, and this is where it reddens.
    """
    # ``OBJECT_GONE_CODES`` is already imported at module scope and is used as-is: this leg
    # deliberately names no preview module, because the companion's preview-ordering guard keys
    # off that name appearing in a leg body and this leg applies no plan at all.
    from larkdocio.base.schema_client import BASE_GONE_CODES

    assert set(BASE_GONE_CODES) == (
        set(OBJECT_GONE_CODES) | set(base_write_harness.ALREADY_DELETED_CODES))
    assert set(base_write_harness.NOT_YET_ADDRESSABLE_CODES) & set(BASE_GONE_CODES) == set(), (
        "a not-yet-addressable code is a LAG, never a proof of absence — scoring one as gone "
        "would retire a live token from every future sweep")


def test_the_teardown_LEDGER_is_swept_and_every_survivor_is_NAMED(credentials):
    """The last word on cleanup, every Base arm's shape."""
    left = base_write_harness.close_out()
    for entry in left:
        assert entry["app_token"] and entry["title"], entry
        assert base_write_harness.is_disposable_title(entry["title"]), entry
    remaining = base_write_harness.survivors()
    assert {e["app_token"] for e in remaining} == {e["app_token"] for e in left}
    if left:
        print("\nledger survivors (recorded, sweepable):", [e["app_token"] for e in left])
    else:
        assert base_write_harness.orphans() == [], (
            "the orphan oracle must answer zero when the ledger is clean")
