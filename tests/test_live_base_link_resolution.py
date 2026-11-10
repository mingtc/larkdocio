"""THE SINGLE LIVE READ ARM for opt-in link resolution (LD-269 AC13).

``@pytest.mark.live``, deselected by default. Run it with::

    pytest -m live tests/test_live_base_link_resolution.py

**Why a live arm at all, when the offline suite is 50 tests deep.** One thing no offline
fixture can prove: that ``records/batch_get`` *honours* its ``record_ids`` body key. R12 is the
standing hazard on this API family — ``records/search`` treats an unrecognised body key exactly
like the bogus control ``{"zzz": 1}`` — so *"it returned code:0"* is not evidence that a
parameter did anything. **A test that a parameter is sent is not a test that it works.** This
arm sends the parameter and sends the parameter-free control at the same endpoint on the same
table — and the control's answer, **found by this arm's first live run**, is stronger than the
"they differ" the AC asked for: **there is no parameter-free control at this endpoint.** An
empty ``record_ids`` is **refused** ``99992402 field validation failed`` with Lark's own
violation naming *"record_ids (the min len is 1)"*. The endpoint **validates** the key instead
of swallowing it, which is the cleanest possible refutation of the R12 hazard here. The second
thing the arm proves live is the shape the whole *"``1254043`` is a normal case"* policy rests
on: that a well-formed id naming no record comes back **per id**, in ``absent_record_ids``,
inside a **successful** body.

**The link CELL is constructed from this Base's own schema and its own record ids, and that is
said out loud.** The Scratch Base carries no link column at all (``p1-q0-03``), and this arm is
**read-only** — provisioning one would mean writing to the maintainer's Base, which this story does not
do. So the link column it resolves is a :class:`~larkdocio.base.cells.FieldSpec` pointed at a
**real table of this Base** holding **real record ids read from it a moment earlier**.
Everything downstream of that is live: the batched read, the target table's schema, the
primary field derived from it, the per-id outcomes and the cost disclosure. What the arm does
*not* prove — that Lark's own link cell carries ``{"link_record_ids": […]}`` — is pinned
offline against committed captures of a Base that really has link columns (``p0-2-03`` /
``p0-2-05``), which is where that evidence belongs.

**Read-only, and provably so.** Every op in :data:`larkdocio.base.ops.OPS` declares
``mutates: False`` — asserted before the first call — and the arm re-reads ``table.revision``
afterwards and asserts it did not move.

**Gentle.** A handful of calls, all through the client's own limiter, and every id it asks for
came out of the Base itself. Rate limits are not probed.

**Skips loudly, never silently.** Without ``LARKDOCIO_SCRATCH_BASE`` or read credentials the
module skips naming exactly what is missing; if the Base holds **no record at all** it skips
saying that, because an arm that quietly passes on an empty ask is an arm that proves nothing.
"""
import canary_support
import pytest

from larkdocio.base import link_resolution as lr
from larkdocio.base import ops as base_ops
from larkdocio.base.cells import FieldSpec
from larkdocio.base.client import BaseReadClient
from larkdocio.base.table import field_spec

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


@pytest.fixture(scope="module")
def populated(scratch_base):
    """``(client, app_token, table, specs, record_ids)`` for the first table of the Scratch
    Base that actually holds records."""
    domain, app_token = scratch_base
    client = BaseReadClient.from_read_credentials(domain)
    for table in (client.list_tables(app_token) or ()):
        records = client.search_records(app_token, table.table_id)
        ids = [r.record_id for r in records if r.record_id]
        if ids:
            specs = [field_spec(f) for f in client.list_fields(app_token, table.table_id)]
            return client, app_token, table, specs, ids
    pytest.skip(
        "the Scratch Base holds no records, so there is nothing to batch-read — this arm "
        "skips rather than passing on an empty ask")


def test_the_registry_declares_the_whole_arm_read_only_BEFORE_it_calls_anything():
    assert base_ops.read_only(), (
        "a mutating op reached the read registry; this arm runs against the maintainer's real Scratch "
        "Base and must not be the thing that discovers that")


def test_record_ids_IS_HONOURED_and_the_parameter_free_control_is_REFUSED(populated):
    """AC9 against Lark itself, and the finding this arm's first live run produced.

    The ask returns exactly what was asked for; the parameter-free control — the same endpoint,
    the same table, ``record_ids: []`` — is **refused** ``99992402`` with Lark naming the rule
    itself. So the parameter is not merely *sent*: the endpoint will not proceed without it,
    which is a stronger answer than R12 asked for and the opposite of `records/search`'s
    swallow-an-unknown-key behaviour.
    """
    from larkdocio.base.client import BATCH_GET_EMPTY_ASK_REFUSED_CODE
    from larkdocio.errors import LarkAPIError

    client, app_token, table, _specs, ids = populated
    asked = ids[:2]

    answered = client.batch_get_records(app_token, table.table_id, asked)
    returned = [r.record_id for r in (answered.records or ())]
    assert returned, "the ask returned nothing, so nothing below proves anything"
    # Every id that came back is one that was asked for; nothing else rode along.
    assert set(returned) <= set(asked)

    with pytest.raises(LarkAPIError) as refusal:
        client.batch_get_records(app_token, table.table_id, [])
    assert refusal.value.code == BATCH_GET_EMPTY_ASK_REFUSED_CODE, (
        f"the empty ask answered {refusal.value.code}, not the recorded validation refusal — "
        "if it now answers code:0 the key is being swallowed and R12 has reached this endpoint")
    assert "record_ids" in str(refusal.value), (
        "the refusal no longer names the offending field, so a caller cannot act on it")


def test_a_missing_record_id_is_reported_PER_ID_and_does_not_fail_the_call(populated):
    """AC4 against Lark itself: the shape the whole *"1254043 is normal"* policy rests on. A
    well-formed id that names no record must come back in ``absent_record_ids`` inside a
    successful body — or, if the whole call refuses instead, as this library's typed error
    carrying that code and nothing worse. Either way the resolver's policy holds; the arm
    records **which** shape the tenant answered with."""
    from larkdocio.errors import LarkAPIError

    client, app_token, table, _specs, ids = populated
    real = ids[0]
    # A well-formed record id that names no record: the real one's own shape, last char rotated.
    bogus = real[:-1] + ("A" if real[-1] != "A" else "B")
    try:
        body = client.batch_get_records(app_token, table.table_id, [real, bogus])
    except LarkAPIError as error:
        assert error.code == lr.RECORD_ID_NOT_FOUND_CODE, (
            f"a missing record id answered {error.code}, which this library's dangling policy "
            "does not model")
        return
    returned = {r.record_id for r in (body.records or ())}
    absent = set(body.absent_record_ids or ())
    assert real in returned, "the real id did not come back"
    assert bogus not in returned, "a non-existent id came back as a record"
    assert bogus in absent, (
        "a non-existent id was neither returned nor reported absent — the per-id reporting "
        "this library's dangling state is built on has changed shape")


def test_the_shipped_resolver_runs_LIVE_costs_what_it_discloses_and_moves_nothing(populated):
    """The whole rung end to end against real records: resolve, then check the disclosure
    against the observed call count and the read-only claim against the table's own revision.

    The link column is built here rather than read (see the module docstring): the Scratch Base
    has none, and this arm does not write.
    """
    client, app_token, table, specs, ids = populated
    primary = lr.primary_field_name(specs)
    assert primary, "the target table designates no primary field; nothing could be resolved"

    link = FieldSpec(field_name="live-link", type=18, ui_type="SingleLink",
                     property={"multiple": True, "table_id": table.table_id,
                               "table_name": table.name})
    holder = type("LiveRecord", (), {
        "record_id": "recLIVE",
        "fields": {"live-link": {"link_record_ids": list(ids[:3])}},
    })()

    before = client.api_calls
    revision_before = table.revision
    resolution = lr.resolve_links(
        client=client, app_token=app_token,
        sources=[("source-table", [link], [holder])],
        known_schemas={table.table_id: specs})
    observed = client.api_calls - before

    assert resolution.api_calls == observed, (
        f"the disclosure says {resolution.api_calls} extra calls; {observed} were made")
    assert resolution.tables == (table.table_id,)
    # ONE target table, whose schema was already in hand: one batched read and no more, for
    # three ids. A resolver whose count followed the cells would have spent three.
    assert observed == 1, f"{observed} calls for one target table and three ids"
    assert len(resolution.records) == len(ids[:3])
    for entry in resolution.records.values():
        assert entry.state in lr.LINK_RESOLUTION_STATES
        assert isinstance(entry.text, str)
    assert any(entry.state == lr.LINK_RESOLVED for entry in resolution.records.values()), (
        "not one real record resolved, so the primary-field derivation proved nothing")

    after = [t for t in client.list_tables(app_token) if t.table_id == table.table_id][0]
    assert after.revision == revision_before, (
        f"table.revision moved {revision_before} -> {after.revision}; this arm is READ-ONLY")
