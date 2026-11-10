"""THE SINGLE LIVE WRITE ARM for the Base write client.

``@pytest.mark.live_write``, deselected by default. Run it with::

    pytest -m live_write

**Against a self-provisioned disposable, and nothing else.** The Base this arm writes is
created by :func:`base_write_harness.disposable_base` at the start of the run and deleted in a
``finally`` at the end. It never touches a configured Base: the read fixture holds
hand-authored specimens the API cannot recreate, so writing it would destroy evidence rather
than merely be impolite. The harness names no such environment variable at all, which is a
static guarantee rather than a promise (``tests/test_base_write_client.py``).

**The teardown is "deleted, or recorded and sweepable" — and that is measured, not lax.**
Deleting a Base is a drive-file operation, and on this tenant a freshly created Base is not
reliably addressable as one for many minutes (the harness's own docstring carries the
measurement). So the ``finally`` spends a short budget and the ledger keeps whatever it could
not land; the last test in this module runs the sweep and **reports every survivor by token and
title**. A leftover Base is therefore a name in a report, never a silence.

**What it proves that no offline test can.** That the six record families really do reach a
real Base on the write credential pair, and — the R12 half — that the shipped bodies **changed
something**: a created record reads back through the shipped reader with the value that was
sent, an update changes it, a batch changes both rows, and both deletes make the rows
unfetchable. Each of those is an effect assertion against the table's real contents, not a
``code:0``. (The wrong-place body is *not* attempted here: the typed builders cannot express
it, which is the by-construction half of the same discipline, and forging one live would be
writing the defect the client is built to prevent.)

**Gentle.** Around a dozen calls, every one through a limiter at the pace the probe packs
sustained. Rate limits are not probed.

**Skips loudly, never silently.** Without write credentials the module skips with a message
naming exactly what is missing.
"""
import base_write_harness
import pytest

from larkdocio.base.client import BaseReadClient
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


def read_text(cell):
    """The plain text of a Text cell as `search` returns it.

    **The asymmetry this arm exists to meet head-on:** a Text value is WRITTEN as a plain
    string and READ BACK as a segment array — `[{"type": "text", "text": "…"}]`. What was sent
    is not what comes back, which is exactly why an effect assertion has to go through the
    reader's own shape rather than compare the write's argument to the read's value.
    """
    if isinstance(cell, str):
        return cell
    return "".join(segment.get("text", "") for segment in cell or ())


@pytest.fixture(scope="module")
def credentials():
    reason = base_write_harness.missing_reason()
    if reason:
        pytest.skip(reason)
    return True


def test_the_write_registry_declares_the_whole_arm_MUTATING_before_it_calls_anything():
    """The mirror of the read arm's first assertion. This arm exists to mutate, and it does so
    only against a Base it created itself — so the thing to assert up front is that every op it
    is about to run is declared a write, not that none of them is."""
    from larkdocio.base import ops as base_ops
    from larkdocio.base import write_ops

    assert write_ops.all_mutate() is True
    assert base_ops.read_only() is True, (
        "the read registry must still be wholly read-only — the two registries are separate "
        "so that both claims can be true at once")


def test_the_live_write_arm_round_trips_every_record_family(credentials):
    write = BaseWriteClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()

    with base_write_harness.disposable_base() as (app_token, table_id, title):
        assert base_write_harness.is_disposable_title(title)
        assert table_id, "a fresh Base always has a default table"

        # --- create, and read the value back through the shipped reader -------------
        created = write.create_record(app_token, table_id, {"Text": "larkdocio-write-arm"})
        assert created.record_id
        rows = {r.record_id: r for r in read.search_records(app_token, table_id)}
        assert read_text(rows[created.record_id].fields["Text"]) == "larkdocio-write-arm"

        # --- update: the value CHANGED, which is the effect assertion, live ---------
        write.update_record(app_token, table_id, created.record_id, {"Text": "second-value"})
        rows = {r.record_id: r for r in read.search_records(app_token, table_id)}
        assert read_text(rows[created.record_id].fields["Text"]) == "second-value"

        # --- batch create: both rows land, in order ---------------------------------
        batch = write.batch_create_records(
            app_token, table_id, [{"Text": "batch-one"}, {"Text": "batch-two"}])
        assert [read_text(r.fields["Text"]) for r in batch] == ["batch-one", "batch-two"]
        batch_ids = [r.record_id for r in batch]

        # --- batch update: one call, both rows changed ------------------------------
        write.batch_update_records(app_token, table_id, [
            (batch_ids[0], {"Text": "batch-one-edited"}),
            (batch_ids[1], {"Text": "batch-two-edited"}),
        ])
        rows = {r.record_id: r for r in read.search_records(app_token, table_id)}
        assert read_text(rows[batch_ids[0]].fields["Text"]) == "batch-one-edited"
        assert read_text(rows[batch_ids[1]].fields["Text"]) == "batch-two-edited"

        # --- single delete: gone, not emptied ---------------------------------------
        assert write.delete_record(app_token, table_id, created.record_id) is True
        remaining = {r.record_id for r in read.search_records(app_token, table_id)}
        assert created.record_id not in remaining

        # --- batch delete: the shipped `records` key really does delete --------------
        write.batch_delete_records(app_token, table_id, batch_ids)
        remaining = {r.record_id for r in read.search_records(app_token, table_id)}
        assert not (set(batch_ids) & remaining), (
            "the shipped batch-delete body changed the table — the effect assertion, live")


def test_the_arm_stays_within_its_call_budget(credentials):
    """Gentleness is an assertion, not an intention: a leg added without thought would show
    here before it showed on a rate limiter."""
    write = BaseWriteClient.from_write_credentials()
    with base_write_harness.disposable_base() as (app_token, table_id, _title):
        write.create_record(app_token, table_id, {"Text": "budget-probe"})
    assert write.api_calls == 1, write.api_calls
    assert write.limiter is not None


def test_the_teardown_LEDGER_is_swept_and_every_survivor_is_NAMED(credentials):
    """The last word on cleanup. It runs the sweep and prints what is left, so a Base the API
    would not release during the run is a reported token rather than a lost one. This does not
    fail on a survivor — the measured lag makes that a coin flip, and a red that means "the API
    was slow" teaches nobody anything. What it does assert is that the ledger is TELLING THE
    TRUTH: nothing is dropped, and every remaining token carries its name and its last code."""
    left = base_write_harness.close_out()
    for entry in left:
        assert entry["app_token"] and entry["title"], entry
        assert base_write_harness.is_disposable_title(entry["title"]), entry
    remaining = base_write_harness.survivors()
    assert {e["app_token"] for e in remaining} == {e["app_token"] for e in left}, (
        "the ledger and the sweep disagree about what is left — the ledger is the "
        "authoritative sweep list and must not drift from it")
    if left:
        print(f"\nUNSWEPT DISPOSABLE BASES ({len(left)}) — re-run the sweep later:")
        for entry in left:
            print(f"  {entry['app_token']}  {entry['title']}  last code {entry['last_code']}")
