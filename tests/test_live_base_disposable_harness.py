"""THE Base self-provision live cycle (LD-258).

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*`` + network).
Run it explicitly::

    pytest -m live_write tests/test_live_base_disposable_harness.py

The binding **live** proof of the leak-proof Base harness — the ``test_live_sheets_write_harness``
shape, one surface over: a full **create → exercise → verify → DELETE-in-``finally`` →
zero-orphan close-out** cycle against a Base it **provisions and destroys itself**:

1. :func:`base_write_harness.disposable_base` **creates** its own Base, titled
   ``larkdocio-DISPOSABLE-…`` and ledgered on creation;
2. **exercises** it through the shipped LD-255 write client (one record), so the disposable is
   proven a real, usable Base rather than an empty husk;
3. **verifies** the effect through the shipped reader, not through the write's own echo;
4. **DELETES in a ``finally``** (drive v1, ``type=bitable``) — a mid-cycle crash still cleans up;
5. runs the **zero-orphan close-out**, and then asks the **bitable API** about every ledger
   token: ``orphans = 0`` means the API answers ``1002`` / ``91402`` for each, never that Drive
   metadata stopped resolving a title — it never does (``07-orphan-sweep.json``).

**It never writes a configured Base.** The only token it can address is the one it created; the
harness refuses every other by allow-list, which is what makes the Scratch Base's hand-authored
Lookup / Email / Stage specimens untouchable rather than merely unmentioned (O2′).

**Its ledger is per-run** (a ``tmp_path`` file), so ``orphans = 0`` is a statement about *this*
cycle. The session-wide ledger at the repository root stays the sweep list for everything else.

**Gentle.** Five calls, every one through the harness's limiter. Rate limits are not probed.

**Skips loudly, never silently** — :func:`base_write_harness.missing_reason` names exactly what
is absent.
"""
import base_write_harness as H
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
    """A Text cell as the reader returns it: a segment array, not the string that was sent."""
    if isinstance(cell, str):
        return cell
    return "".join(segment.get("text", "") for segment in cell or ())


def test_the_base_harness_round_trips_and_leaves_ZERO_ORPHANS(tmp_path, capsys):
    reason = H.missing_reason()
    if reason:
        pytest.skip(reason)

    ledger = H.Ledger(tmp_path / "run_ledger.json")
    write = BaseWriteClient.from_write_credentials()
    read = BaseReadClient.from_read_credentials()

    evidence = {}
    with H.disposable_base(ledger=ledger) as (app_token, table_id, title):
        evidence["app_token"] = app_token
        evidence["title"] = title
        assert H.is_disposable_title(title), (
            "a disposable that is not greppable is not sweepable")
        assert table_id, "a fresh Base always has a default table"

        # 2) Exercise it — the disposable is a real Base, not an empty husk.
        created = write.create_record(app_token, table_id, {"Text": "larkdocio-harness-cycle"})
        assert created.record_id

        # 3) Verify through the shipped READER, never the write's own echo.
        rows = {r.record_id: r for r in read.search_records(app_token, table_id)}
        assert read_text(rows[created.record_id].fields["Text"]) == "larkdocio-harness-cycle"
        evidence["record_id"] = created.record_id
    # 4) The delete-in-finally has fired here.

    entry = ledger.entries[0]
    assert entry["app_token"] == app_token and entry["title"] == title, (
        "the ledger records every object created, by token AND by name")

    # 5) Close out, then ask the BITABLE API — the oracle, per the Base read spec § D3.
    still_there = H.close_out(ledger=ledger)
    leaked = H.orphans(ledger=ledger)
    evidence["ledger_count"] = len(ledger.entries)
    evidence["orphans"] = len(leaked)
    assert leaked == [], (
        "the bitable API still resolves a Base this cycle created — that is an orphan by the "
        f"only definition that means anything here: {leaked!r} (close-out left {still_there!r})")

    with capsys.disabled():
        print(f"\n[live_write:base-harness] app_token={evidence['app_token']} "
              f"title={evidence['title']} record={evidence.get('record_id')} "
              f"ledger_count={evidence['ledger_count']} orphans={evidence['orphans']}")


def test_the_cycle_stays_within_its_call_budget():
    """Gentleness is an assertion, not an intention — a leg added without thought shows here
    before it shows on a rate limiter."""
    reason = H.missing_reason()
    if reason:
        pytest.skip(reason)
    write = BaseWriteClient.from_write_credentials()
    with H.disposable_base() as (app_token, table_id, _title):
        write.create_record(app_token, table_id, {"Text": "budget-probe"})
    assert write.api_calls == 1, write.api_calls
