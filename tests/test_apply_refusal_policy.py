"""LD-458 — a plan-gated ``apply()`` RAISES on a refused entry unless the caller opts in.

The maintainer ruling (2026-08-14, recorded verbatim in the issue and in ``requirements/DECISIONS.md``):
**"go with a"** — ``apply()`` raises on refused entries unless the caller explicitly opts into
partial application. The evidence is two independent dogfood-round-4 incidents whose one line is
*"``apply()`` does not raise on refused entries, so a log-ignoring caller gets silent partial
application"* (``dev/dogfood4/verdict-grid.md`` § 5 thread 1 + § 2 D2).

**Nothing about the writes changes.** The same entries apply and the same entries refuse, in the
same order, issuing the same calls — only *return-vs-raise* moves. The opt-in is **one spelling
on every plan-gated apply this library ships** (``allow_partial=True``): docx, sheets, Base
records and Base schema. A per-surface vocabulary is exactly the inconsistency round 4 punished
elsewhere, so the spelling is asserted from ``inspect.signature`` rather than trusted.

The log's consumability is pinned here too (AC4): every ``ApplyLog`` iterates and answers
``len()``. The defect that earned it was a ``TypeError`` raised **after** a live write had
already landed, because the log a consumer was told to read was not iterable.
"""
import inspect

import pytest

from base_schema_fakes import FakeBaseWorld, NoSleep, ScriptedSchemaClient
from larkdocio.errors import LarkApplyRefusedError, LarkDocIOError, LarkRateLimitError

from larkdocio.write.apply import apply as docx_apply
from larkdocio.write.preview import dry_run as docx_dry_run
from larkdocio.write.model import ApplyLog as DocxApplyLog

from larkdocio.sheets.write_apply import ApplyLog as SheetsApplyLog
from larkdocio.sheets.write_apply import (
    ValueWriteRequest,
    apply as sheets_apply,
    dry_run as sheets_dry_run,
)

from larkdocio.base.apply import apply as base_apply, dry_run as base_dry_run
from larkdocio.base.plan import ApplyLog as BaseApplyLog
from larkdocio.base.schema_apply import schema_apply, schema_dry_run
from larkdocio.base.schema_plan import create_table

from test_base_apply import FakeBase, MAIN, R1
from test_sheets_write_apply import FakeSheetGateway, TOKEN
from write_harness import (
    RoutingOpener,
    _block_payload,
    _client,
    _insert,
    _page,
    _para,
    _req,
    _run,
)


# --------------------------------------------------------------------------- #
# Per-surface fixtures: a batch with ONE refusable entry beside a good one.      #
# --------------------------------------------------------------------------- #

def _docx(quotes=("present", "absent")):
    """A docx plan over a one-paragraph tree: ``present`` resolves, ``absent`` refuses."""
    tree = _page(_para("p1", "present"))
    plan = docx_dry_run([_req(q, replacement=f"{q}!") for q in quotes], tree)
    opener = RoutingOpener(blocks={
        "p1": _block_payload("p1", [_run("present")], parent_id="root"),
        "root": _block_payload("root", [], block_type=1),
    })
    return plan, _client(opener), opener


def _sheets():
    gw = FakeSheetGateway(revision=4, values={
        "s1!A1:A1": [["a0"]],
        # a rich cell is refused at dry-run: this engine writes plain values.
        "s1!B1:B1": [[{"type": "url", "link": "x", "text": "y"}]],
    })
    plan = sheets_dry_run([
        ValueWriteRequest.for_a1("s1!A1:A1", [["a1"]]),
        ValueWriteRequest.for_a1("s1!B1:B1", [["b1"]]),
    ], gw, TOKEN)
    return plan, gw


def _base_records():
    """One writable edit + one computed cell (refused at plan time, zero calls)."""
    base = FakeBase()
    draft = base.snapshot(table_id=MAIN).edit()
    draft.set("rec88HpEvHGLV4", "lookup", "computed cells cannot be written")
    plan = base_dry_run(draft)
    return plan, base


def _base_schema():
    """A schema plan whose only call answers ``code:0`` and changes nothing → ``dropped``."""
    world = FakeBaseWorld(apps={"appOLD": "Scratch Base"},
                          tables={"appOLD": {"tbl1": "Table"}})
    client = ScriptedSchemaClient(world, deaf={"create_table"})
    plan = schema_dry_run([create_table("appOLD", "ghost", primary_field_name="Title")])
    return plan, client, world


def _schema_run(plan, client, world, **kwargs):
    return schema_apply(plan, client=client, read_client=world,
                        settle_attempts=10, sleep=NoSleep(), **kwargs)


# =========================================================================== #
# AC1 — the default is a RAISE, and the raise is typed and carries the record  #
# =========================================================================== #

def test_docx_apply_raises_when_any_entry_is_refused():
    plan, client, _opener = _docx()
    with pytest.raises(LarkApplyRefusedError):
        docx_apply(plan, client, "doc123")


def test_the_refusal_error_is_typed_and_part_of_the_toolkit_family():
    plan, client, _opener = _docx()
    with pytest.raises(LarkApplyRefusedError) as caught:
        docx_apply(plan, client, "doc123")
    assert isinstance(caught.value, LarkDocIOError), "except LarkDocIOError must catch it"
    assert type(caught.value) is not RuntimeError


def test_the_raise_carries_the_whole_log_the_applied_entries_and_each_refusal():
    plan, client, _opener = _docx()
    with pytest.raises(LarkApplyRefusedError) as caught:
        docx_apply(plan, client, "doc123")
    err = caught.value

    assert isinstance(err.log, DocxApplyLog), "the FULL log object travels on the error"
    assert len(err.log) == len(plan.entries)
    assert len(err.applied) == 1 and err.applied[0].outcome == "applied"
    assert len(err.refused) == 1 and err.refused[0].outcome == "refused"
    # the reason AND the detail, per refused entry, programmatically
    assert err.refusals == ({"reason": "not-found",
                             "detail": err.refused[0].refusal.detail},)
    assert err.refusals[0]["detail"], "a detail-less refusal is not actionable"


def test_the_message_names_the_counts_both_ways_and_how_to_opt_in():
    plan, client, _opener = _docx()
    with pytest.raises(LarkApplyRefusedError) as caught:
        docx_apply(plan, client, "doc123")
    message = str(caught.value)
    assert "1 of 2 entries applied; 1 refused" in message
    assert "allow_partial=True" in message
    assert "not-found" in message, "the message names the reason, not only the count"


def test_the_opt_in_returns_the_log_exactly_as_before():
    plan, client, _opener = _docx()
    log = docx_apply(plan, client, "doc123", allow_partial=True)
    assert [e.outcome for e in log.entries] == ["applied", "refused"]


def test_nothing_about_which_entries_apply_or_refuse_changes():
    """The same writes are issued whether the call raises or returns."""
    plan_a, client_a, opener_a = _docx()
    with pytest.raises(LarkApplyRefusedError) as caught:
        docx_apply(plan_a, client_a, "doc123")
    raised_log = caught.value.log

    plan_b, client_b, opener_b = _docx()
    returned_log = docx_apply(plan_b, client_b, "doc123", allow_partial=True)

    assert raised_log.to_dict() == returned_log.to_dict()
    assert [c["method"] for c in opener_a.calls] == [c["method"] for c in opener_b.calls]
    assert len(opener_a.writes) == len(opener_b.writes) == 1


def test_a_clean_docx_run_returns_normally_and_does_not_raise():
    plan, client, _opener = _docx(quotes=("present",))
    log = docx_apply(plan, client, "doc123")
    assert [e.outcome for e in log.entries] == ["applied"]


# =========================================================================== #
# AC2 / AC3 — ONE spelling, on EVERY plan-gated apply surface                  #
# =========================================================================== #

_GATED_APPLIES = {
    "docx-write": docx_apply,
    "sheets-write": sheets_apply,
    "base-write": base_apply,
    "base-schema-write": schema_apply,
}


@pytest.mark.parametrize("surface,fn", sorted(_GATED_APPLIES.items()))
def test_every_plan_gated_apply_carries_the_same_opt_in_spelling(surface, fn):
    parameter = inspect.signature(fn).parameters.get("allow_partial")
    assert parameter is not None, f"{surface} has no partial-application opt-in"
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, "opt-in is explicit, never positional"
    assert parameter.default is False, "partial application is opt-IN, never the default"


def test_sheets_apply_raises_and_the_opt_in_returns():
    plan, gw = _sheets()
    with pytest.raises(LarkApplyRefusedError) as caught:
        sheets_apply(plan, gw)
    assert isinstance(caught.value.log, SheetsApplyLog)
    assert len(caught.value.refused) == 1 and len(caught.value.applied) == 1

    plan, gw = _sheets()
    log = sheets_apply(plan, gw, allow_partial=True)
    assert [e.outcome for e in log.entries] == ["applied", "refused"]


def test_base_record_apply_raises_and_the_opt_in_returns():
    plan, base = _base_records()
    with pytest.raises(LarkApplyRefusedError) as caught:
        base_apply(plan, client=base, read_client=base)
    assert isinstance(caught.value.log, BaseApplyLog)
    assert caught.value.refusals[0]["reason"] == "non-writable-field"

    plan, base = _base_records()
    log = base_apply(plan, client=base, read_client=base, allow_partial=True)
    assert [e.outcome for e in log.entries] == ["refused"]


def test_base_schema_apply_raises_and_the_opt_in_returns():
    plan, client, world = _base_schema()
    with pytest.raises(LarkApplyRefusedError) as caught:
        _schema_run(plan, client, world)
    assert caught.value.refused[0].outcome == "dropped", (
        "a call that answered code:0 and changed nothing did NOT land")

    plan, client, world = _base_schema()
    log = _schema_run(plan, client, world, allow_partial=True)
    assert [e.outcome for e in log.entries] == ["dropped"]


def test_a_clean_run_on_every_surface_returns_without_the_opt_in():
    """The gate fires on refusals only — a clean batch is untouched by this policy."""
    gw = FakeSheetGateway(revision=4, values={"s1!A1:A1": [["a0"]]})
    plan = sheets_dry_run([ValueWriteRequest.for_a1("s1!A1:A1", [["a1"]])], gw, TOKEN)
    assert [e.outcome for e in sheets_apply(plan, gw).entries] == ["applied"]

    base = FakeBase()
    draft = base.snapshot().edit()
    draft.set(R1, "Text", "moved by the plan")
    log = base_apply(base_dry_run(draft), client=base, read_client=base)
    assert [e.outcome for e in log.entries] == ["applied"]

    world = FakeBaseWorld(apps={"appOLD": "Scratch Base"},
                          tables={"appOLD": {"tbl1": "Table"}})
    client = ScriptedSchemaClient(world)
    plan = schema_dry_run([create_table("appOLD", "fresh", primary_field_name="Title")])
    assert _schema_run(plan, client, world).entries[0].is_applied


# =========================================================================== #
# AC4 — the log is CONSUMABLE: it iterates and it measures, on every surface    #
# =========================================================================== #

def test_every_apply_log_iterates_and_answers_len():
    plan, client, _opener = _docx()
    docx_log = docx_apply(plan, client, "doc123", allow_partial=True)
    plan, gw = _sheets()
    sheets_log = sheets_apply(plan, gw, allow_partial=True)
    plan, base = _base_records()
    base_log = base_apply(plan, client=base, read_client=base, allow_partial=True)

    for log in (docx_log, sheets_log, base_log):
        assert list(log) == list(log.entries), f"{type(log).__module__} does not iterate"
        assert len(log) == len(log.entries), f"{type(log).__module__} has no len()"
        assert [e for e in log], "a for-loop over the log must yield its entries"


def test_the_docx_log_names_what_applied_and_what_refused():
    plan, client, _opener = _docx()
    log = docx_apply(plan, client, "doc123", allow_partial=True)
    assert len(log.applied) == 1 and log.applied[0].outcome == "applied"
    assert len(log.refusals) == 1 and log.refusals[0].outcome == "refused"
    assert log.applied + log.refusals == log.entries or (
        set(log.applied) | set(log.refusals)) == set(log.entries)


def test_an_empty_log_iterates_to_nothing_rather_than_raising_TypeError():
    """The defect this AC exists for: a TypeError discovered AFTER a live write landed."""
    assert list(DocxApplyLog()) == [] and len(DocxApplyLog()) == 0
    assert list(SheetsApplyLog()) == [] and len(SheetsApplyLog()) == 0
    assert list(BaseApplyLog()) == [] and len(BaseApplyLog()) == 0


# =========================================================================== #
# The LD-453 follow-up (recorded by that issue's QA): `_live_insertion_point`   #
# shipped THREE refusal arms with no offline test. They are pinned here.        #
# =========================================================================== #

def _insert_plan(reference_text="Alpha"):
    from larkdocio.write.model import InsertPosition

    tree = _page(_para("p1", reference_text))
    return docx_dry_run(
        [_insert(reference_text, InsertPosition.AFTER, ["new line"])], tree)


def test_ld453_arm_a_parent_that_cannot_be_read_refuses_stale_anchor_with_no_write():
    """Arm (a): the live parent read fails (Lark's own ``1770002``) → no index can be
    derived, so the plan's position cannot be confirmed. NO write."""
    plan = _insert_plan()
    opener = RoutingOpener(blocks={
        # the reference reads fine and names a parent the opener does not know → 1770002
        "p1": _block_payload("p1", [_run("Alpha")], parent_id="ghostparent"),
    })
    log = docx_apply(plan, _client(opener), "doc123", allow_partial=True)
    entry = log.entries[0]
    assert entry.outcome == "refused"
    assert entry.refusal.reason.value == "stale-anchor"
    assert "1770002" in entry.refusal.detail and "ghostparent" in entry.refusal.detail
    assert opener.writes == [], "a position that cannot be confirmed issues NO write"


def test_ld453_arm_b_a_reference_that_is_no_longer_a_child_refuses_with_no_write():
    """Arm (b): the parent reads, but no longer lists the reference — it moved."""
    plan = _insert_plan()
    opener = RoutingOpener(blocks={
        "p1": _block_payload("p1", [_run("Alpha")], parent_id="root"),
        "root": {"code": 0, "data": {"block": {
            "block_id": "root", "block_type": 1, "children": ["someone", "else"]}}},
    })
    log = docx_apply(plan, _client(opener), "doc123", allow_partial=True)
    entry = log.entries[0]
    assert entry.outcome == "refused"
    assert entry.refusal.reason.value == "stale-anchor"
    assert "no longer a child" in entry.refusal.detail
    assert opener.writes == [], "no guessed index, and no write"


def test_ld453_arm_c_a_rate_limit_on_the_parent_read_is_RE_RAISED_not_called_staleness():
    """Arm (c): throttling is not drift — telling a consumer to re-plan an unchanged
    document would be a lie.

    **TRANSFORMED, NOT STRUCK (LD-643).** The reason above is unchanged and still binds in
    full: a rate limit may never be reported as staleness, and the two assertions that say so
    — the reason is not ``stale-anchor``, and **no write is issued** — are both still here and
    both still checked. What LD-643 supersedes is the CONCLUSION this test used to draw from
    that reason: *"so the rate-limit error travels out of apply() intact"*. Travelling out of
    ``apply()`` intact is exactly what cost the caller the apply-log for the entries that had
    already landed, which is the defect the docx disposition boundary closes. So the error is
    still not called staleness — it is now called ``rate-limited``, in a log that is 1:1 with
    the plan, and the batch halts. The engine's own re-raise inside ``_live_or_stale`` is
    untouched; what changed is that ``apply()`` now catches it one level out and types it.
    """
    plan = _insert_plan()

    class ThrottledParentClient:
        def __init__(self):
            self.writes = []

        def read_document_revision(self, document_id):   # pragma: no cover - guard unavailable
            return None

        def get_block(self, document_id, block_id):
            if block_id == "root":
                raise LarkRateLimitError("throttled", code="99991400", msg="too many request")
            return _block_payload("p1", [_run("Alpha")], parent_id="root")["data"]["block"]

        def create_children(self, document_id, block_id, children, index):
            self.writes.append((document_id, block_id, children, index))
            raise AssertionError("no write may be issued after a rate-limit re-raise")

    client = ThrottledParentClient()
    log = docx_apply(plan, client, "doc123", allow_partial=True)

    entry = log.entries[0]
    assert entry.refusal.reason.value != "stale-anchor", "throttling is still not staleness"
    assert entry.refusal.reason.value == "rate-limited"
    assert entry.outcome == "refused"
    assert "NOTHING landed" in entry.refusal.detail
    assert log.halt["reason"] == "rate-limited"
    # The other half of the original assertion, unchanged: no write is issued.
    assert client.writes == []
