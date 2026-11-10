"""LD-257 — the in-memory Base table model: the SNAPSHOT half.

Every test here is offline. The fixtures are the **committed probe captures**
(`tests/captures/base-study/captures/`) loaded through the landed loader `tests/base_captures.py` and,
where a walk is being pinned, the pinned SDK's own deserializer — so an API drift reddens at
deserialization instead of travelling on as a plausible-looking `None` (PROJECT.md § Quality
bar).

The properties this file exists to hold:

* **AC1** — a snapshot is complete or it is not a snapshot. The paging proof is read off the
  page bodies the walk actually saw, and a walk that stopped with a live cursor still in hand
  **refuses to become a model**. The named regression is the **ten phantom rows**.
* **AC2** — the diff leg makes no network call: an import guard over both modules, a
  call-count spy over the transport, and a socket that raises if anything reaches for one.
* **AC6** — the model is not a cache: the recorded anchor is the one the plan is built
  against, and no re-read happens implicitly.
* **AC7** — multi-table snapshots are per-table by construction; `table.revision` is
  per-table isolated (`05-08`).

The diff half is `tests/test_base_model_diff.py`.
"""
import ast
import json
import socket
from pathlib import Path

import pytest
from lark_oapi.api.bitable.v1 import SearchAppTableRecordResponse
from lark_oapi.core.json import JSON

from base_captures import capture, scratch_base
from larkdocio.base import diff as base_diff
from larkdocio.base import model as base_model
from larkdocio.base.model import (
    BaseSnapshot,
    BaseTableSnapshot,
    IncompleteSnapshot,
    ReadProof,
    snapshot_base,
    snapshot_table,
)
from larkdocio.base.table import assemble_base, assemble_table
from larkdocio.errors import LarkDocIOError

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src" / "larkdocio" / "base"


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #

def pagination_steps():
    """The six live steps of `p1-q1-01`, keyed by the probe's own note."""
    return {step["_note"]: step
            for step in capture("p1-q1-01-pagination-anomaly.json")["steps"]}


def search_page_bodies():
    """The real three-page walk of the 6-row Scratch Base table at `?page_size=2`.

    Deserialized through the SDK, so these are the same `SearchAppTableRecordResponseBody`
    objects the client's own walk consumes.
    """
    steps = pagination_steps()
    return [
        JSON.unmarshal(json.dumps(steps[note]["response"]),
                       SearchAppTableRecordResponse).data
        for note in ("page_size in the QUERY STRING", "walk step 1", "walk step 2")
    ]


def ten_phantom_rows_body():
    """The first (and only) page of `05-07`'s `plain` read: **10 rows, `has_more: true`,
    `total: 12`** — the shape that fooled the opener's own probe 05."""
    modes = capture("05-07-record-read-option-matrix.json")["response"]["data"]["modes"]
    return JSON.unmarshal(json.dumps(modes["plain"]), SearchAppTableRecordResponse).data


def scratch_table_read(table_index=0):
    """One captured Scratch-Base table through the landed structured intermediate."""
    app, tables, per_table = scratch_base()
    table = tables[table_index]
    fields, records = per_table[table.table_id]
    return assemble_table(table_id=table.table_id, name=table.name,
                          fields=fields, records=records)


def walked_table_read():
    """The same table, assembled from the records of the real **three-page walk**."""
    app, tables, per_table = scratch_base()
    table = tables[0]
    fields, _ = per_table[table.table_id]
    records = [item for body in search_page_bodies() for item in (body.items or ())]
    return assemble_table(table_id=table.table_id, name=table.name,
                          fields=fields, records=records)


def table_revisions_05_08():
    """`05-08`'s measured per-table revisions, before and after one record write."""
    data = capture("05-08-staleness.json")["response"]["data"]
    return data["table_revisions_before_write"], data["table_revisions_after_write"]


# --------------------------------------------------------------------------- #
# AC1 — a snapshot is complete or it is not a snapshot                         #
# --------------------------------------------------------------------------- #

def test_ac1_a_two_page_walk_that_reached_the_end_builds_a_complete_model():
    """The real three-page walk of the 6-row table: exhausted, and all six records land."""
    proof = ReadProof.from_pages(search_page_bodies())
    assert proof.exhausted is True
    assert proof.pages == 3
    assert proof.records == 6

    snapshot = snapshot_table(walked_table_read(), app_token="appXXX", revision=18,
                              read_proof=proof)
    assert isinstance(snapshot, BaseTableSnapshot)
    assert len(snapshot.records) == 6
    assert snapshot.read_proof.exhausted is True


def test_ac1_a_walk_that_stopped_with_a_live_cursor_refuses_to_become_a_model():
    """Truncate the same walk after page 2 — `has_more: true` with a fresh cursor still in
    hand. The records that came back are real; the *table* was not read, so this is not a
    snapshot and may not become a model."""
    truncated = search_page_bodies()[:2]
    proof = ReadProof.from_pages(truncated)
    assert proof.exhausted is False
    assert proof.records == 4

    with pytest.raises(IncompleteSnapshot) as excinfo:
        snapshot_table(walked_table_read(), app_token="appXXX", revision=18,
                       read_proof=proof)
    message = str(excinfo.value)
    assert "exhaust" in message.lower()
    # It must say WHY, because "incomplete" alone is not actionable.
    assert proof.stopped_because in message


def test_ac1_the_ten_phantom_rows_shape_is_a_named_regression():
    """**The ten phantom rows.** A freshly created Base's default table ships with **10
    auto-provisioned empty rows** (`dev/base-study-2026-08-03.md` § probe 05). So a
    first-page-only read of a populated table hands back ten rows, `code:0`, and looks for all
    the world like the table — the opener's own probe 05 was fooled by exactly that before
    probe 06 corrected it, and `05-07`'s `plain` mode still carries the shape: **10 items,
    `has_more: true`, `total: 12`**.

    A diff over that snapshot would read the two unseen rows as **DELETIONS**. That is why
    the refusal is AC1 and not a footnote.
    """
    body = ten_phantom_rows_body()
    assert len(body.items) == 10
    assert body.has_more is True
    assert body.total == 12

    proof = ReadProof.from_pages([body])
    assert proof.exhausted is False
    assert proof.records == 10

    with pytest.raises(IncompleteSnapshot):
        snapshot_table(scratch_table_read(), app_token="appXXX", revision=1,
                       read_proof=proof)


def test_ac1_the_proof_classifies_every_way_a_walk_can_end():
    """Each termination shape the client's own walk recognises, and whether it is exhaustion.

    The client believes the **cursor**, not the flag, and stops; what it cannot do is *report*
    that it stopped early. That is the gap this proof closes.
    """
    def body(items, has_more, token=None):
        return {"items": items, "has_more": has_more, "page_token": token}

    assert ReadProof.from_pages([body([1], False)]).exhausted is True
    # "There is more" with nothing to ask for next.
    assert ReadProof.from_pages([body([1], True, None)]).exhausted is False
    # "There is more", with the cursor we just used — a replay, not a page.
    repeated = ReadProof.from_pages([body([1], True, "t1"), body([1], True, "t1")])
    assert repeated.exhausted is False
    assert "cursor" in repeated.stopped_because
    # A live cursor still in hand.
    assert ReadProof.from_pages([body([1], True, "t2")]).exhausted is False
    # Nothing was read at all.
    nothing = ReadProof.from_pages([])
    assert nothing.exhausted is False
    assert nothing.pages == 0


def test_ac1_the_proof_agrees_with_the_shipped_client_walk_about_what_came_back():
    """The proof is a **reading of the walk**, not a second walk. Over the same page bodies
    its record count is exactly what `BaseReadClient._walk_pages` would have returned — so it
    cannot drift into a different opinion about what the walk saw."""
    from larkdocio.base.client import BaseReadClient

    bodies = search_page_bodies()
    by_cursor = {None: bodies[0]}
    for index, body in enumerate(bodies[:-1]):
        by_cursor[body.page_token] = bodies[index + 1]

    client = BaseReadClient("id", "secret", sdk_client=object())
    walked = client._walk_pages(lambda token: by_cursor[token])
    assert len(walked) == ReadProof.from_pages(bodies).records == 6


def test_ac1_the_snapshot_is_built_from_the_landed_structured_intermediate():
    """`snapshot_table` takes a `BaseTableRead` — the landed L1 type — and nothing else. A
    raw payload is refused rather than parsed, because a second parse of the wire is a second
    definition of what a Base cell is."""
    proof = ReadProof.from_pages(search_page_bodies())
    with pytest.raises(LarkDocIOError):
        snapshot_table({"table_id": "tbl1", "fields": [], "rows": []},
                       app_token="appXXX", revision=1, read_proof=proof)


def test_ac1_the_cells_are_l1s_own_render_never_a_second_opinion():
    """Every cell in the model is byte-identical to the landed intermediate's — the model
    arranges L1's rendered cells, it never re-renders one."""
    table_read = scratch_table_read()
    proof = ReadProof.from_pages(search_page_bodies())
    snapshot = snapshot_table(table_read, app_token="appXXX", revision=18, read_proof=proof)
    for row, record in zip(table_read.rows, snapshot.records):
        assert record.record_id == row.record_id
        assert tuple(value for _, value in record.cells) == row.cells


# --------------------------------------------------------------------------- #
# AC6 — the model is not a cache, and its age is visible                       #
# --------------------------------------------------------------------------- #

def test_ac6_the_snapshot_carries_the_revision_it_was_taken_at():
    before, _ = table_revisions_05_08()
    revision = before["tblIwcDAKXzn8xXB"]
    snapshot = snapshot_table(scratch_table_read(), app_token="appXXX", revision=revision,
                              read_proof=ReadProof.from_pages(search_page_bodies()))
    assert snapshot.revision == revision == 18


def test_ac6_a_model_with_no_anchor_is_not_a_model():
    """`table.revision` is the only compare-and-swap anchor bitable exposes (`05-08`: the
    body keys `revision` / `last_modified_time` are **silently ignored**). A snapshot with no
    anchor could never be safely applied, so it refuses at construction rather than at
    `apply`."""
    with pytest.raises(IncompleteSnapshot) as excinfo:
        snapshot_table(scratch_table_read(), app_token="appXXX", revision=None,
                       read_proof=ReadProof.from_pages(search_page_bodies()))
    assert "revision" in str(excinfo.value)


def test_ac6_the_plan_is_built_against_the_recorded_anchor_not_a_fresh_read():
    """The anchor that reaches the diff is the snapshot's own. Mutating the source the
    snapshot was taken from changes nothing — there is no implicit refresh."""
    snapshot = snapshot_table(scratch_table_read(), app_token="appXXX", revision=18,
                              read_proof=ReadProof.from_pages(search_page_bodies()))
    draft = snapshot.edit()
    draft.set(snapshot.records[0].record_id, "Text", "moved")
    assert draft.diff().revision == 18
    # A second, *newer* read of the same table does not reach back into the snapshot.
    fresher = snapshot_table(scratch_table_read(), app_token="appXXX", revision=19,
                             read_proof=ReadProof.from_pages(search_page_bodies()))
    assert snapshot.revision == 18
    assert fresher.revision == 19
    assert draft.diff().revision == 18


# --------------------------------------------------------------------------- #
# AC7 — multi-table plans are per-table by construction                        #
# --------------------------------------------------------------------------- #

def scratch_base_read():
    """The whole captured Scratch Base through the landed intermediate."""
    app, tables, per_table = scratch_base()
    assembled = [
        assemble_table(table_id=table.table_id, name=table.name,
                       fields=per_table[table.table_id][0],
                       records=per_table[table.table_id][1])
        for table in tables
    ]
    return assemble_base(app_token=app.app_token, name=app.name,
                         time_zone=app.time_zone, tables=assembled)


def base_snapshot_at(revisions):
    base_read = scratch_base_read()
    proofs = {table.table_id: ReadProof.from_pages(search_page_bodies())
              for table in base_read.tables}
    return snapshot_base(base_read, revisions=revisions, read_proofs=proofs)


def test_ac7_each_table_carries_its_own_anchor():
    base_read = scratch_base_read()
    first, second = (table.table_id for table in base_read.tables)
    snapshot = base_snapshot_at({first: 18, second: 0})
    assert isinstance(snapshot, BaseSnapshot)
    assert snapshot.table(first).revision == 18
    assert snapshot.table(second).revision == 0


def test_ac7_a_bump_in_one_table_does_not_implicate_the_other():
    """`table.revision` is **per-table isolated** — `05-08` measured the untouched second
    table sitting at `0` while the edited one advanced `18 → 19`, and the *app* revision did
    not move at all. So a plan spanning two tables carries two anchors, and D4′'s per-table
    halt scope is coherent."""
    before, after = table_revisions_05_08()
    edited, untouched = "tblIwcDAKXzn8xXB", "tblDghjoOXsg03o9"
    assert (before[edited], after[edited]) == (18, 19)
    assert before[untouched] == after[untouched] == 0

    base_read = scratch_base_read()
    first, second = (table.table_id for table in base_read.tables)
    snapshot = base_snapshot_at({first: before[edited], second: before[untouched]})
    draft = snapshot.edit()
    draft.table(first).set(snapshot.table(first).records[0].record_id, "Text", "moved")
    diff = draft.diff()

    assert [entry.table_id for entry in diff.tables] == [first, second]
    assert diff.table(first).revision == 18
    assert diff.table(second).revision == 0

    # The same two tables read after the write: only the edited one moved.
    bumped = base_snapshot_at({first: after[edited], second: after[untouched]})
    assert bumped.table(first).revision == 19
    assert bumped.table(second).revision == 0


def test_ac7_a_base_snapshot_refuses_a_table_with_no_proof_or_no_anchor():
    base_read = scratch_base_read()
    first, second = (table.table_id for table in base_read.tables)
    proofs = {first: ReadProof.from_pages(search_page_bodies())}
    with pytest.raises(IncompleteSnapshot):
        snapshot_base(base_read, revisions={first: 1, second: 1}, read_proofs=proofs)
    with pytest.raises(IncompleteSnapshot):
        snapshot_base(base_read, revisions={first: 1},
                      read_proofs={first: ReadProof.from_pages(search_page_bodies()),
                                   second: ReadProof.from_pages(search_page_bodies())})


# --------------------------------------------------------------------------- #
# AC2 — the diff leg makes NO network call                                     #
# --------------------------------------------------------------------------- #

_FORBIDDEN_IMPORTS = (
    "larkdocio.base.client",
    "larkdocio.base.write_client",
    "larkdocio.base.read",
    "lark_oapi.api",
    "http",
    "urllib",
    "requests",
    "socket",
    "ssl",
)


def imported_modules(path):
    """Every module name imported **directly** by one source file, via its AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("module_file", ["model.py", "diff.py"])
def test_ac2_neither_module_imports_a_client_or_a_transport(module_file):
    """Structural, not incidental. `reconcile.py` states the same property for docx; this is
    the Base parity, and an AST guard is what keeps it true after the next edit."""
    for name in imported_modules(_SRC / module_file):
        for forbidden in _FORBIDDEN_IMPORTS:
            assert not (name == forbidden or name.startswith(forbidden + ".")), (
                f"{module_file} imports {name!r} — the diff leg makes no network call")


def test_ac2_the_diff_module_names_no_endpoint_and_no_http_verb():
    source = (_SRC / "diff.py").read_text(encoding="utf-8")
    for token in ("open.larksuite.com", "open.feishu.cn", "/open-apis/"):
        assert token not in source


class _Leg:
    """A bare attribute holder standing in for one SDK resource namespace."""


class _Recorder:
    """One SDK resource method: records every request, hands back the next canned response."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, *args, **kwargs):
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.responses) - 1)
        return self.responses[index]


def offline_read_client():
    """A `BaseReadClient` over the captured Scratch Base, plus the recorder it calls."""
    from lark_oapi.api.bitable.v1 import (
        GetAppResponse,
        ListAppTableFieldResponse,
        ListAppTableResponse,
    )

    from larkdocio.base.client import BaseReadClient

    app = JSON.unmarshal(json.dumps(capture("p1-q0-01-app-meta.json")["response"]),
                         GetAppResponse)
    tables = JSON.unmarshal(json.dumps(capture("p1-q0-02-tables.json")["response"]),
                            ListAppTableResponse)
    per_table = capture("p1-q0-03-per-table.json")["per_table"]
    fields = [JSON.unmarshal(json.dumps(entry["fields"]["response"]),
                             ListAppTableFieldResponse) for entry in per_table]
    records = [JSON.unmarshal(json.dumps(entry["records_search"]["response"]),
                              SearchAppTableRecordResponse) for entry in per_table]

    recorders = {
        "app": _Recorder([app]),
        "field": _Recorder(fields),
        "record": _Recorder(records),
        "table": _Recorder([tables]),
    }
    sdk = _Leg()
    sdk.bitable = _Leg()
    sdk.bitable.v1 = _Leg()
    sdk.bitable.v1.app = _Leg()
    sdk.bitable.v1.app.get = recorders["app"]
    sdk.bitable.v1.app_table = _Leg()
    sdk.bitable.v1.app_table.list = recorders["table"]
    sdk.bitable.v1.app_table_field = _Leg()
    sdk.bitable.v1.app_table_field.list = recorders["field"]
    sdk.bitable.v1.app_table_record = _Leg()
    sdk.bitable.v1.app_table_record.search = recorders["record"]

    class _NoWait:
        def acquire(self):
            return None

    return BaseReadClient("id", "secret", sdk_client=sdk, rate_limiter=_NoWait()), recorders


def test_ac2_a_call_count_spy_records_zero_calls_during_diff():
    """The whole spine — read, snapshot, edit, diff — with a recording transport underneath.
    The read costs its five calls; the diff leg costs **zero**, and the spy is what says so
    rather than a docstring."""
    from larkdocio.base.read import read_base

    client, recorders = offline_read_client()
    base_read = read_base("vuidhExample9cdd21c93b126bb", client=client)
    calls_after_read = client.api_calls
    requests_after_read = {name: len(rec.requests) for name, rec in recorders.items()}
    assert calls_after_read > 0

    proofs = {table.table_id: ReadProof.from_pages(search_page_bodies())
              for table in base_read.tables}
    snapshot = snapshot_base(
        base_read,
        revisions={table.table_id: 1 for table in base_read.tables},
        read_proofs=proofs,
    )
    draft = snapshot.edit()
    table_id = base_read.tables[0].table_id
    draft.table(table_id).set(snapshot.table(table_id).records[0].record_id, "Text", "moved")
    draft.table(table_id).add(Text="a brand new row")
    draft.table(table_id).delete(snapshot.table(table_id).records[1].record_id)
    diff = draft.diff()

    assert diff is not None
    assert client.api_calls == calls_after_read
    assert {name: len(rec.requests) for name, rec in recorders.items()} == requests_after_read


def test_ac2_the_diff_leg_survives_a_world_with_no_sockets(monkeypatch):
    """Belt to the AST guard's braces: if anything under `diff()` reached for a socket, this
    would raise instead of quietly succeeding."""
    snapshot = snapshot_table(scratch_table_read(), app_token="appXXX", revision=18,
                              read_proof=ReadProof.from_pages(search_page_bodies()))
    draft = snapshot.edit()
    draft.set(snapshot.records[0].record_id, "Text", "moved")

    def _no_sockets(*args, **kwargs):
        raise AssertionError("the diff leg opened a socket")

    monkeypatch.setattr(socket, "socket", _no_sockets)
    monkeypatch.setattr(socket, "create_connection", _no_sockets)
    diff = draft.diff()
    assert diff.of(base_diff.EDITED)


def test_ac2_the_model_does_not_relist_the_non_writable_pairs():
    """AC4's eight pairs are **imported** from LD-255's `write_vocabulary`, which is what makes
    this story and LD-256 parallel-safe. A second list here would drift the first time Lark
    added a computed type."""
    from larkdocio.base.write_vocabulary import NON_WRITABLE_PAIRS

    for module_file in ("model.py", "diff.py"):
        source = (_SRC / module_file).read_text(encoding="utf-8")
        for _, ui_type in NON_WRITABLE_PAIRS:
            if ui_type in ("Formula", "Lookup", "Stage"):
                continue  # named in prose, never as a table row
            assert ui_type not in source, f"{module_file} re-lists {ui_type}"
    assert "write_vocabulary" in " ".join(imported_modules(_SRC / "diff.py"))


def test_the_public_names_are_reachable_without_the_package_front_door():
    """LD-257 ships nothing consumer-observable: the trio is importable from its own modules
    and is **deliberately not** re-exported from `larkdocio.base` yet — that is LD-260's."""
    import larkdocio.base as base_package

    assert base_model.snapshot_table is snapshot_table
    assert not hasattr(base_package, "snapshot_table")
