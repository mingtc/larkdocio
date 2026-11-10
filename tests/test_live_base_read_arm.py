"""THE SINGLE LIVE READ ARM for the Base client (LD-247 AC10).

``@pytest.mark.live``, deselected by default. Run it with::

    pytest -m live

**What it is, and what it is deliberately not.** This is *one* arm proving the shipped client
reaches a real Base and comes back with sane, typed data. It is **not** the determinism canary
— two downloads compared byte-for-byte, the whole surface exercised — which is **LD-252**, the
tranche's live gate. Keeping this small is the point: the tranche's live budget belongs to
LD-252, and a story that spends it early leaves nothing for the gate that matters.

**Read-only, and provably so.** Every op in :data:`larkdocio.base.ops.OPS` declares
``mutates: False`` — asserted here before the first call, so a future write op cannot be
smuggled onto this path. The arm also records ``table.revision`` before and after and asserts
it did not move: a read that changed the Base would show up as a moved revision, which is the
one thing the packs proved is a reliable write detector (a Stage write returns ``code:0`` and
leaves the revision alone; a real Text write moves it).

**Gentle.** Six calls, all through the client's own limiter: app meta, tables, then views,
fields, records for the first table, then one revision re-read. Rate limits are not probed.

**Skips loudly, never silently.** Without ``LARKDOCIO_SCRATCH_BASE`` or read credentials the
whole module skips with a message naming exactly what is missing.
"""
import canary_support
import pytest

from larkdocio.base import ops as base_ops
from larkdocio.base.client import BaseReadClient

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


def test_the_live_read_arm_reaches_a_real_base_and_moves_nothing(scratch_base):
    domain, app_token = scratch_base
    client = BaseReadClient.from_read_credentials(domain)

    app = client.get_app(app_token)
    assert app.name, "the Base reported no name"
    assert app.is_advanced in (True, False)

    tables = client.list_tables(app_token)
    assert tables, "the Base reported no tables — a Base always has at least one"
    table = tables[0]
    revision_before = table.revision

    views = client.list_views(app_token, table.table_id)
    assert views, "a table always has at least one view (the last one cannot be deleted)"

    fields = client.list_fields(app_token, table.table_id)
    assert fields, "a table always has at least one field"
    assert all(field.field_name for field in fields)

    records = client.search_records(app_token, table.table_id)
    # A table may legitimately be empty; what must hold is that every record came back typed
    # and carries the id `search` reports (never the legacy list's duplicated `id`).
    for record in records:
        assert record.record_id

    after = [t for t in client.list_tables(app_token) if t.table_id == table.table_id][0]
    assert after.revision == revision_before, (
        f"table.revision moved {revision_before} -> {after.revision}; this arm is READ-ONLY")

    # Six calls if every list fits one page, which it does on the Scratch Base. The bound is
    # the assertion (a table that grew past a page is not a failure); the budget is.
    assert 6 <= client.api_calls <= 10, (
        f"the arm's live budget is ~6 calls; it spent {client.api_calls}")
