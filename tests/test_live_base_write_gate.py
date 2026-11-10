"""THE BASE WRITE GATE — the Base record-write ENGINE, proved against the real API.

``@pytest.mark.live_write``, deselected by default. Run it with::

    pytest -m live_write

LD-255's arm proves the six record families reach a real Base. This proves the **engine above
them**: the mandatory previewer, the plan gate, the client-side compare-and-swap, and the
write-effect oracle. Three arms, each proving something no offline test can:

1. **SURGICAL.** Snapshot a table, edit ONE cell, preview, apply, re-read — and assert **cell
   by cell** that only that cell moved: every other cell of that record and every cell of every
   other record is byte-identical, and the record set is unchanged. Then the edit is reversed
   through the same gate and the table is byte-identical to its baseline again, which is what
   the word *surgical* actually claims: the trip leaves no residue.

2. **A REAL ``STALE_BASE``.** A plan is built; a **second write client** then really writes to
   the table out of band; the apply refuses ``stale-base`` with **zero writes measured at the
   client boundary** and the target cell provably unchanged. Then a re-read, re-plan and
   re-apply lands — a recoverable refusal, not a dead end. Only a real Base can prove it: the
   guard compares a ``table.revision`` Lark itself advances.

3. **NOTHING REFUSED IS EVER SENT**, with the oracle's premise as its live control. Two
   refusals are driven, both with the write client wired to a transport that **raises on
   contact**, so zero-calls is structural rather than trusted: a **Stage** cell (the opaque
   type whose write answers success and stores nothing — the reason the oracle exists) over the
   committed schema of a Base that really has one, and a **live** refusal on the disposable's
   own Date column. Then the positive control, live: a known-good write on the same table
   **moves** ``table.revision``. The negative reading of the oracle — *success without an
   anchor advance means the write did not happen* — is only meaningful because the positive
   half is true on this API, which is what this arm measures.

**Why the Stage half runs over a committed schema rather than a live column.** A Stage column
cannot be created here: larkdocio ships **no field authoring at all** (that is the Base schema-write spec), so a
self-provisioned Base has the four fields Lark gives a new table and none of them is opaque.
The alternative — writing to the configured Base that does have one — is forbidden, and rightly
so: its specimens are hand-authored and no API route can recreate them. So the refusal is driven
over that Base's **captured, real** field schema with a transport that raises on contact, which
proves the thing the AC asks for (the write is refused **locally**, at zero transport calls)
without inventing a field or touching a Base this arm did not create.

**Against a self-provisioned disposable, and nothing else.** Every Base written here is created
by :func:`base_write_harness.disposable_base` and deleted in a ``finally``; the harness names no
configured target at all, which is a static guarantee rather than a promise.

**Gentle.** Around three dozen calls across the module, every one through a limiter at the pace
the probe packs sustained. Rate limits are not probed.

**Skips loudly, never silently.** Without write credentials the module skips with a message
naming exactly what is missing.

**The credential rider, restated where it is easy to over-read.** On this tenant the READ and
WRITE credential pairs alias ONE app with a byte-identical secret. So this gate proves the
**write path works**; it proves NOTHING about the read path lacking write scope, and no result
here may be cited as evidence of scope separation. That claim needs a genuinely separate app.
"""
import base_captures
import base_write_harness
import pytest

from log_reading_apply import reading_the_log
from larkdocio.base.apply import apply, dry_run
from larkdocio.base.client import BaseReadClient
from larkdocio.base.model import ReadProof, snapshot_table
from larkdocio.base.plan import Refusal
from larkdocio.base.table import assemble_table
from larkdocio.base.write_client import BaseWriteClient
from larkdocio.errors import LarkConfigError

# This gate's subject is the LOG — which entry landed, which refused, with which typed
# reason — not the return-vs-raise policy (pinned offline in
# tests/test_apply_refusal_policy.py, proved live in
# tests/test_live_write_refusal_policy_gate.py). So it opts into partial application
# once, here, the same way the offline log-reading suites do.
apply = reading_the_log(apply)

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

#: The disposable's default table is created by Lark with these four fields. The Text one is
#: the only column this gate writes; the Date one is what the live local-refusal half aims at.
TEXT_FIELD = "Text"
DATE_FIELD = "Date"

#: Rows the surgical arm seeds. Three, so "every OTHER record is byte-identical" has something
#: to say — a one-row table would make the claim vacuous.
SEEDED = ("gate-row-one", "gate-row-two", "gate-row-three")


class RaisesOnContact:
    """A transport that raises the moment anything touches it.

    The zero-write proof for a plan-time refusal is then **structural**: a refusal that failed
    to fire errors instead of writing, so the assertion cannot pass for the wrong reason. The
    docx ring's reviewer-anchor arm is the precedent.
    """

    class _Boom:
        def __getattr__(self, name):
            raise AssertionError(
                f"the write client touched the transport ({name}) — a plan-time refusal must "
                "cost ZERO transport calls")

    def __getattr__(self, name):
        return RaisesOnContact._Boom()


def inert_write_client():
    """A real :class:`BaseWriteClient` whose SDK raises on contact."""
    return BaseWriteClient("id", "secret", sdk_client=RaisesOnContact())


def one_page(records):
    """A page body standing for the single page a small table's walk really saw."""
    return {"items": list(records), "has_more": False, "page_token": None}


def table_snapshot(read, app_token, table_id):
    """A live :class:`~larkdocio.base.model.BaseTableSnapshot` for one table.

    The record read is asserted to fit in **one** page against the client's own page size, so
    the :class:`~larkdocio.base.model.ReadProof` this hands to ``snapshot_table`` is a reading
    of a walk that really did end, not a claim about one. (This gate's tables are its own and
    hold a handful of rows; a caller with a big table pages it and classifies those pages.)
    """
    from larkdocio.base.client import DEFAULT_PAGE_SIZE

    table = next(t for t in read.list_tables(app_token)
                 if getattr(t, "table_id", None) == table_id)
    fields = read.list_fields(app_token, table_id)
    records = read.search_records(app_token, table_id)
    assert len(records) < DEFAULT_PAGE_SIZE, (
        "this gate's tables are meant to fit in one page; a bigger one would make the "
        "single-page ReadProof below a claim rather than a reading")
    table_read = assemble_table(table_id=table_id, name=getattr(table, "name", "") or "",
                                fields=fields, records=records)
    return snapshot_table(
        table_read, app_token=app_token, revision=getattr(table, "revision", None),
        read_proof=ReadProof.from_pages([one_page(records)]))


def cell_map(snapshot):
    """``{record_id: {field_name: rendered cell}}`` — the comparison unit of "surgical"."""
    return {record.record_id: record.as_dict() for record in snapshot.records}


def revision_of(read, app_token, table_id):
    for table in read.list_tables(app_token) or ():
        if getattr(table, "table_id", None) == table_id:
            return getattr(table, "revision", None)
    return None


def skip_reason():
    """Why this gate cannot run, or ``None``.

    ``base_write_harness.missing_reason()`` asks the shipped write-credential getter, and that
    getter **raises** a typed configuration error rather than answering with empties — which is
    correct for a caller about to write, and would turn a credential-less ``pytest -m
    live_write`` into an ERROR here instead of a skip. So the error is caught and used as the
    reason: it already names both variables, so the skip is LOUD either way and never a silent
    pass. (The harness is LD-258's; this reads it defensively rather than changing it.)
    """
    try:
        return base_write_harness.missing_reason()
    except LarkConfigError as exc:  # pragma: no cover - only on a credential-less machine
        return str(exc)


@pytest.fixture(scope="module")
def credentials():
    reason = skip_reason()
    if reason:
        pytest.skip(reason)
    return True


@pytest.fixture()
def clients(credentials):
    return BaseWriteClient.from_write_credentials(), BaseReadClient.from_read_credentials()


def seed(write, app_token, table_id, values=SEEDED):
    write.batch_create_records(app_token, table_id,
                               [{TEXT_FIELD: value} for value in values])


# --------------------------------------------------------------------------- #
# ARM 1 — SURGICAL, and it leaves no residue.                                   #
# --------------------------------------------------------------------------- #

def test_arm1_a_record_write_is_SURGICAL_and_restores_to_a_byte_identical_baseline(clients):
    write, read = clients
    with base_write_harness.disposable_base() as (app_token, table_id, title):
        assert base_write_harness.is_disposable_title(title)
        seed(write, app_token, table_id)

        before_snapshot = table_snapshot(read, app_token, table_id)
        baseline = cell_map(before_snapshot)
        target = next(rid for rid, cells in baseline.items()
                      if cells.get(TEXT_FIELD) == SEEDED[1])

        # ---- edit exactly one cell, through the mandatory previewer ---------- #
        draft = before_snapshot.edit()
        draft.set(target, TEXT_FIELD, "gate-row-two-EDITED")
        plan = dry_run(draft)
        assert len(plan.entries) == 1, plan.to_dict()
        assert plan.api_call_count == 1, "one edited record is one batch call"

        log = apply(plan, client=write, read_client=read)
        assert len(log.entries) == len(plan.entries)
        assert [entry.outcome for entry in log.entries] == ["applied"], log.to_dict()

        # ---- THE SURGICAL ASSERTION, cell by cell --------------------------- #
        after = cell_map(table_snapshot(read, app_token, table_id))
        assert set(after) == set(baseline), "the record set moved — a write created or removed"
        moved = {(rid, field)
                 for rid, cells in after.items()
                 for field, value in cells.items()
                 if baseline[rid].get(field) != value}
        assert moved == {(target, TEXT_FIELD)}, moved
        assert after[target][TEXT_FIELD] == "gate-row-two-EDITED"

        # ---- reverse it through the same gate: byte-identical baseline ------ #
        back = table_snapshot(read, app_token, table_id).edit()
        back.set(target, TEXT_FIELD, SEEDED[1])
        restore_log = apply(dry_run(back), client=write, read_client=read)
        assert [entry.outcome for entry in restore_log.entries] == ["applied"]
        assert cell_map(table_snapshot(read, app_token, table_id)) == baseline, (
            "the round trip left residue — 'surgical' claims it does not")


# --------------------------------------------------------------------------- #
# ARM 2 — a REAL race, refused, and recoverable.                                #
# --------------------------------------------------------------------------- #

def test_arm2_a_REAL_out_of_band_write_refuses_STALE_BASE_with_zero_writes(clients):
    write, read = clients
    with base_write_harness.disposable_base() as (app_token, table_id, _title):
        seed(write, app_token, table_id)

        snapshot = table_snapshot(read, app_token, table_id)
        planned_at = snapshot.revision
        target = next(rid for rid, cells in cell_map(snapshot).items()
                      if cells.get(TEXT_FIELD) == SEEDED[0])
        draft = snapshot.edit()
        draft.set(target, TEXT_FIELD, "never-lands")
        plan = dry_run(draft)

        # ---- THE RACE: a SECOND client really writes, out of band ----------- #
        interloper = BaseWriteClient.from_write_credentials()
        other = next(rid for rid, cells in cell_map(snapshot).items()
                     if cells.get(TEXT_FIELD) == SEEDED[2])
        interloper.update_record(app_token, table_id, other, {TEXT_FIELD: "moved-underneath"})
        assert revision_of(read, app_token, table_id) != planned_at, (
            "the out-of-band write did not move the anchor — this arm would prove nothing")

        # ---- apply: refused, ZERO writes measured at the client boundary ---- #
        calls_before = write.api_calls
        log = apply(plan, client=write, read_client=read)
        assert write.api_calls == calls_before, (
            "a stale-base refusal must issue ZERO writes; the write client was called")
        assert [entry.outcome for entry in log.entries] == ["stale"], log.to_dict()
        refusal = log.entries[0].refusal
        assert refusal.reason == Refusal.STALE_BASE, refusal
        assert table_id in log.table_halts, log.table_halts

        # …and the target cell really is untouched on the live Base.
        after = cell_map(table_snapshot(read, app_token, table_id))
        assert after[target][TEXT_FIELD] == SEEDED[0]

        # ---- RECOVERABLE: re-read, re-plan, re-apply -> it lands ------------ #
        fresh = table_snapshot(read, app_token, table_id)
        assert fresh.revision != planned_at
        replan = fresh.edit()
        replan.set(target, TEXT_FIELD, "lands-after-replan")
        relog = apply(dry_run(replan), client=write, read_client=read)
        assert [entry.outcome for entry in relog.entries] == ["applied"], relog.to_dict()
        final = cell_map(table_snapshot(read, app_token, table_id))
        assert final[target][TEXT_FIELD] == "lands-after-replan"
        assert final[other][TEXT_FIELD] == "moved-underneath", (
            "the interloper's write must survive — the refusal protected it, not reverted it")


# --------------------------------------------------------------------------- #
# ARM 3 — nothing refused is ever sent, and the oracle's premise is live.        #
# --------------------------------------------------------------------------- #

def test_arm3a_a_STAGE_CELL_is_refused_LOCALLY_at_zero_transport_calls():
    """The silently-dropped write, refused before it can be dropped.

    A Stage write answers success and stores nothing, with the table's revision provably
    unmoved — which is exactly why this engine refuses it rather than reporting a success that
    did not happen. Driven over the committed schema of a Base that really has a Stage column
    (no disposable can be given one — larkdocio ships no field authoring), with a transport that
    raises on contact, so the zero-calls half is structural.
    """
    app, tables, per_table = base_captures.scratch_base()
    stage_table = None
    for table in tables:
        fields, records = per_table[table.table_id]
        if any(getattr(spec, "ui_type", None) == "Stage" for spec in fields):
            stage_table = (table, fields, records)
            break
    assert stage_table is not None, (
        "the committed captures no longer carry a Stage column — this arm's subject is gone")
    table, fields, records = stage_table
    stage_field = next(spec.field_name for spec in fields
                       if getattr(spec, "ui_type", None) == "Stage")

    table_read = assemble_table(table_id=table.table_id, name=table.name,
                                fields=fields, records=records)
    snapshot = snapshot_table(
        table_read, app_token=getattr(app, "app_token", None) or "appCAPTURED",
        revision=getattr(table, "revision", None) or 1,
        read_proof=ReadProof.from_pages([one_page(records)]))

    draft = snapshot.edit()
    draft.set(snapshot.record_ids[0], stage_field, "anything at all")
    plan = dry_run(draft)
    assert [entry.op for entry in plan.entries] == ["refused"], plan.to_dict()
    assert plan.api_call_count == 0, "a plan with nothing to do plans no call"
    detail = plan.entries[0].refusal.detail
    assert "Stage" in detail and "24" in detail, detail

    # …and applying it touches NOTHING: the transport raises if anything reaches it.
    log = apply(plan, client=inert_write_client(), read_client=_InertReadClient())
    assert [entry.outcome for entry in log.entries] == ["refused"], log.to_dict()


class _InertReadClient:
    """A read seam for a plan whose every entry is already refused.

    ``apply`` requires one — the compare-and-swap is client-side — and a plan with no pending
    entry never reaches it. Making it explode on contact is what proves that.
    """

    def list_tables(self, app_token):
        raise AssertionError("a fully-refused plan must not read the anchor either")

    def list_fields(self, app_token, table_id):
        raise AssertionError("a fully-refused plan must not run the precondition read")

    def search_records(self, app_token, table_id):
        raise AssertionError("a fully-refused plan must not run the precondition read")


def test_arm3b_a_live_refusal_costs_zero_calls_and_a_good_write_MOVES_the_anchor(clients):
    """The live half, and the positive control that makes the oracle mean something.

    A value that is not its field's write shape is refused at plan time on the disposable's own
    Date column — zero transport calls, structurally. Then the control: a known-good write to
    the same table really does advance ``table.revision``, so *success without an advance*
    reads as *the write did not happen* rather than as *the anchor does not move here*.
    """
    write, read = clients
    with base_write_harness.disposable_base() as (app_token, table_id, _title):
        seed(write, app_token, table_id, values=(SEEDED[0],))

        snapshot = table_snapshot(read, app_token, table_id)
        names = {spec.field_name for spec in snapshot.fields}
        assert DATE_FIELD in names, sorted(names)
        target = snapshot.record_ids[0]

        # ---- refused locally, and NOTHING is sent --------------------------- #
        refused = snapshot.edit()
        refused.set(target, DATE_FIELD, "the third of never")
        refused_plan = dry_run(refused)
        assert [entry.op for entry in refused_plan.entries] == ["refused"], \
            refused_plan.to_dict()
        assert refused_plan.api_call_count == 0
        log = apply(refused_plan, client=inert_write_client(), read_client=_InertReadClient())
        assert [entry.outcome for entry in log.entries] == ["refused"], log.to_dict()

        # ---- THE POSITIVE CONTROL, live: a good write moves the anchor ------ #
        before = revision_of(read, app_token, table_id)
        good = table_snapshot(read, app_token, table_id).edit()
        good.set(target, TEXT_FIELD, "the-control-write")
        good_log = apply(dry_run(good), client=write, read_client=read)
        assert [entry.outcome for entry in good_log.entries] == ["applied"], good_log.to_dict()
        after = revision_of(read, app_token, table_id)
        assert after is not None and before is not None
        assert after > before, (
            f"table.revision did not advance on a write that landed ({before} -> {after}) — "
            "the write-effect oracle's premise does not hold on this API")
        assert good_log.entries[0].revision == after
        assert not good_log.dropped, "a landed write must never be reported dropped"


# --------------------------------------------------------------------------- #
# The close-out — every disposable accounted for, by name.                      #
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# ARM 4 — a DATE-ONLY value round-trips, and the reverted-fix control shifts.    #
# --------------------------------------------------------------------------- #

#: The zone the round-trip declares. ``Asia/Singapore`` is UTC+8 — the offset the probe measured
#: the server's own day boundary at (16:00 UTC), i.e. the one under which local midnight lands in
#: the window that used to render a day early. A zone that agreed with UTC would prove nothing.
ROUND_TRIP_ZONE = "Asia/Singapore"

#: The three calendar dates, authored as **local midnight in** :data:`ROUND_TRIP_ZONE`: a month
#: boundary, a year boundary, and an ordinary day. Fixed dates, so nothing here reads a clock.
ROUND_TRIP_DATES = ("2026/03/01", "2027/01/01", "2026/08/14")

DATE_ONLY_FIELD = "DateOnly"
DATE_ONLY_FORMATTER = "yyyy/MM/dd"


def local_midnight_ms(calendar_date, zone):
    """``"2026/03/01"`` + a zone → the ms-epoch a caller computing local midnight would send."""
    import datetime as _dt
    from zoneinfo import ZoneInfo

    year, month, day = (int(part) for part in calendar_date.split("/"))
    moment = _dt.datetime(year, month, day, tzinfo=ZoneInfo(zone))
    return int(moment.timestamp() * 1000)


def date_only_round_trip(provisioner, *, declare_zone):
    """Write the three dates into a fresh disposable and read them back through the SHIPPED
    reader. ``declare_zone`` is the whole difference between the fix and its control.

    Returns ``(read, sorted rendered cells)`` — sorted, because ``records/search`` promises no
    order and the claim here is about the *set* of calendar dates, not about row positions.
    """
    from larkdocio.base.read import read_base
    from larkdocio.base.schema_client import BaseSchemaClient

    schema = BaseSchemaClient.from_write_credentials()
    write = BaseWriteClient.from_write_credentials()
    zone = ROUND_TRIP_ZONE if declare_zone else None
    with base_write_harness.disposable_base(provisioner=provisioner,
                                            time_zone=zone) as (app_token, table_id, title):
        assert base_write_harness.is_disposable_title(title)
        schema.create_field(app_token, table_id, DATE_ONLY_FIELD, 5, ui_type="DateTime",
                            properties={"date_formatter": DATE_ONLY_FORMATTER,
                                        "auto_fill": False})
        write.batch_create_records(
            app_token, table_id,
            [{DATE_ONLY_FIELD: local_midnight_ms(date, ROUND_TRIP_ZONE)}
             for date in ROUND_TRIP_DATES])
        read = read_base(app_token)
        table = next(t for t in read.tables if t.table_id == table_id)
        column = [f.field_name for f in table.fields].index(DATE_ONLY_FIELD)
        # The rows Lark gives a brand-new table are EMPTY in this column, and an empty Base cell
        # is an absent key rendered blank — so the dates are the non-blank cells, not "every row".
        rendered = sorted(cell for cell in (row.cells[column] for row in table.rows) if cell)
        assert len(rendered) == len(ROUND_TRIP_DATES), (rendered, len(table.rows))
        return read, rendered


def test_arm4_a_DATE_ONLY_value_round_trips_when_the_zone_is_DECLARED(clients):
    """The fix, live: three dates written as local midnight in a DECLARED zone — across a month
    boundary and a year boundary — read back as the same calendar dates, and the read reports the
    zone as the Base's own rather than an assumption."""
    read, rendered = date_only_round_trip(base_write_harness._Provisioner(), declare_zone=True)

    assert read.time_zone == ROUND_TRIP_ZONE, (
        "the create declared the zone, so every later read must report it")
    assert read.date_zone == ROUND_TRIP_ZONE
    assert read.date_zone_assumed is False
    assert read.date_zone_disclosure is None, "nothing was assumed, so nothing is disclosed"
    assert rendered == sorted(ROUND_TRIP_DATES), (rendered, sorted(ROUND_TRIP_DATES))


def test_arm4_the_REVERTED_FIX_CONTROL_reproduces_the_one_day_shift_but_not_silently(clients):
    """The control the AC asks for, and the only honest form of it: the *identical* run against a
    Base created **without** the zone key — which is exactly what this library minted before the
    fix. The one-day shift comes back, so the gate demonstrably CAN fail on this defect; what it
    can no longer do is stay quiet about it, which the disclosure assertions pin."""
    import datetime as _dt

    read, rendered = date_only_round_trip(base_write_harness._Provisioner(), declare_zone=False)

    assert read.time_zone in (None, ""), (
        "a create with no zone key is the pre-fix behaviour; if Lark started supplying one, this "
        "control is no longer a control and the whole policy is re-opened")
    assert read.date_zone_assumed is True
    assert read.date_zone_disclosure, "the assumption must be disclosed, never silent"
    shifted = sorted((_dt.date.fromisoformat(intended.replace("/", "-"))
                      - _dt.timedelta(days=1)).strftime("%Y/%m/%d")
                     for intended in ROUND_TRIP_DATES)
    assert rendered == shifted, (
        f"the reverted-fix control must reproduce the one-day shift: expected {shifted}, "
        f"got {rendered}")


def test_the_teardown_LEDGER_is_swept_and_every_survivor_is_NAMED(credentials):
    """The last word on cleanup, in the shape LD-255's arm established: the sweep runs and
    prints what is left, so a Base the API would not release during the run is a reported token
    rather than a lost one."""
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
