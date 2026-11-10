"""THE LIVE RAW-VALUE ARM for the Base read surface (LD-293 AC9).

``@pytest.mark.live``, deselected by default. Run it with::

    pytest -m live

**Why a live arm at all, when every shape is already pinned offline.** Because the whole claim
of this surface is *"what the transport received on that call"*, and an offline fixture can
only prove *"what the transport received in 2026"*. The unit suite compares the accessor
against committed captures; this compares it against **the records the client just fetched**,
on the same call, so a shape Lark changed since the captures were taken shows up as a
difference between the two rather than as a plausible-looking value.

**Read-only, and provably so.** Retention adds no op — it decides whether an already-received
payload is kept — so this arm rides the same read-only registry the other two Base read arms
do, asserts that before its first call, and re-reads ``table.revision`` at the end as the
no-write proof. **No writes, no disposable provisioning, no file bytes.**

**What this Base can and cannot prove, said here rather than implied.** The compound specimens
the configured Scratch Base actually holds are **Email** and **Lookup** — the two whose
rendered form differs most from their wire form, and the Email column is the exact shape that
made a consumer's dedupe report identical addresses as different. **Person, link, attachment
and date columns are not populated on it**, and populating them would be a *write* this arm may
not make, so those shapes are proved offline against the committed captures instead. The arm
reports which types it covered rather than asserting a coverage it cannot control, and fails
outright if it covers none.

**Gentle.** One read of the configured Scratch Base through the shipped entry point, plus the
client reads this arm makes itself to have something to compare against, plus one revision
re-read. Rate limits are not probed.

**Skips loudly, never silently.** Without ``LARKDOCIO_SCRATCH_BASE`` or read credentials the
whole module skips with a message naming exactly what is missing.
"""
import canary_support
import pytest

from larkdocio.base import ops as base_ops
from larkdocio.base.client import BaseReadClient
from larkdocio.base.read import read_base
from larkdocio.base.table import render_base

pytestmark = pytest.mark.live
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

canary_support.load_env()


@pytest.fixture(scope="module")
def scratch_base():
    reason = canary_support.base_missing_reason()
    if reason:
        pytest.skip(reason)
    return canary_support.parse_base_url(canary_support.scratch_base_url())


def test_the_registry_declares_the_whole_arm_read_only_BEFORE_it_calls_anything():
    assert base_ops.read_only(), (
        "a mutating op reached the registry; this arm runs against the maintainer's real Scratch "
        "Base and must not be the thing that discovers that")


def test_raw_is_what_the_transport_received_on_that_very_call(scratch_base):
    """The arm's core assertion: the retained value **is** the record body the client just
    fetched — same value, same Python type — for every key of every record, and the compound
    types are present rather than assumed."""
    domain, app_token = scratch_base
    client = BaseReadClient.from_read_credentials(domain)

    document = read_base(app_token, client=client, domain=domain, retain_raw=True)
    assert document.tables, "the Base reported no tables"

    # What the transport itself received, read separately so the comparison has two sides.
    compound_seen = set()
    for table in document.tables:
        fetched = {record.record_id: (record.fields or {})
                   for record in client.search_records(app_token, table.table_id)}
        assert fetched, f"table {table.name!r} came back with no records to compare"
        by_pair = {spec.field_name: spec.pair for spec in table.fields}
        for row in table.rows:
            assert row.raw_fields is not None, "retention was on and nothing was retained"
            wire = fetched[row.record_id]
            assert list(row.raw_fields.keys()) == list(wire.keys()), (
                f"{row.record_id}: raw re-ordered or renamed the body's keys")
            for key, value in wire.items():
                held = row.raw_fields[key]
                assert type(held) is type(value), (
                    f"{row.record_id}.{key}: raw carried {type(held).__name__} where the "
                    f"wire carried {type(value).__name__}")
                assert held == value, f"{row.record_id}.{key}: the value moved"
                compound_seen.add(by_pair.get(key))

    # The compound types AC9 names, as far as this Base carries them. The Scratch Base holds
    # hand-authored specimens, so what it does NOT hold is reported rather than asserted away.
    wanted = {(11, "User"), (18, "SingleLink"), (21, "DuplexLink"), (17, "Attachment"),
              (5, "DateTime"), (1001, "CreatedTime"), (1002, "ModifiedTime"), (1, "Email"),
              (19, "Lookup")}
    covered = wanted & compound_seen
    assert covered, (
        "this Base carries none of the compound types the arm exists to check; the raw view "
        f"was proven only over scalars. Present: {sorted(p for p in compound_seen if p)}")
    print(f"raw view proven live over compound types: {sorted(covered)}")


def test_the_flag_being_on_changes_NOTHING_a_reader_sees(scratch_base):
    """Off is byte-identical, asserted against the live Base rather than a fixture: two reads
    of the same Base, one with retention and one without, render the same Markdown."""
    domain, app_token = scratch_base
    client = BaseReadClient.from_read_credentials(domain)

    with_raw = read_base(app_token, client=client, domain=domain, retain_raw=True)
    without = read_base(app_token, client=client, domain=domain)
    assert render_base(with_raw) == render_base(without), (
        "retention changed the rendered output — it must add an artefact, never an opinion")
    assert all(row.raw_fields is None for table in without.tables for row in table.rows)


def test_the_arm_moved_nothing(scratch_base):
    """The no-write proof this ring's other arms make too: ``table.revision`` is the reliable
    write detector, and it must be where it was."""
    domain, app_token = scratch_base
    client = BaseReadClient.from_read_credentials(domain)

    before = {table.table_id: table.revision for table in client.list_tables(app_token)}
    read_base(app_token, client=client, domain=domain, retain_raw=True)
    after = {table.table_id: table.revision for table in client.list_tables(app_token)}
    assert after == before, f"table.revision moved {before} -> {after}; this arm is READ-ONLY"
