"""Characterization tests for the shared write-test harness (LD-088).

LD-088 consolidates the fake-transport doubles, the model node/request/table
builders, and the request-introspection helpers that the four write-apply test
files (`test_whole_paragraph_apply`, `test_subspan_edits`, `test_insert_delete_apply`,
`test_table_cell_apply`) and the two table anchor-resolution test files had each
re-authored near-byte-identically (the LD-039 `builders.py` doctrine, which the
write tranche re-violated).

This module PINS the canonical shape each shared helper produces, so the
consolidation is behaviour-preserving: the four apply suites import these helpers
instead of defining their own, and their assertions are unchanged. If a helper's
output shape ever drifts, this file reddens in one place.
"""
import json

from larkdocio.model import HeadingNode, PageNode, TableCellNode, TableNode, Text, TextNode
from larkdocio.write.client import WriteClient
from larkdocio.write.model import (
    DeleteRequest,
    EditRequest,
    InsertPosition,
    InsertRequest,
    TableLocator,
)

from write_harness import (
    FakeClock,
    StubOpener,
    _block_payload,
    _by_method,
    _cell,
    _client,
    _delete,
    _heading,
    _insert,
    _methods,
    _page,
    _para,
    _patch_ok,
    _req,
    _run,
    _table,
    _treq,
)


# --------------------------------------------------------------------------- #
# raw-payload doubles                                                          #
# --------------------------------------------------------------------------- #

def test_run_plain_and_styled():
    assert _run("hi") == {"text_run": {"content": "hi"}}
    assert _run("hi", bold=True) == {
        "text_run": {"content": "hi", "text_element_style": {"bold": True}}
    }


def test_block_payload_base_shape():
    assert _block_payload("p1", [_run("x")]) == {
        "code": 0,
        "data": {"block": {"block_id": "p1", "block_type": 2, "text": {"elements": [_run("x")]}}},
    }


def test_block_payload_key_and_type_override():
    payload = _block_payload("h1", [_run("x")], block_type=3, key="heading1")
    block = payload["data"]["block"]
    assert block["block_type"] == 3 and "heading1" in block


def test_block_payload_superset_style_and_parent():
    payload = _block_payload("d1", [_run("x")], parent_id="root", style={"folded": True})
    block = payload["data"]["block"]
    assert block["parent_id"] == "root"
    assert block["text"]["style"] == {"folded": True}


def test_patch_ok_shape():
    assert _patch_ok() == {"code": 0, "data": {"block": {"block_id": "x"}}}


# --------------------------------------------------------------------------- #
# transport doubles                                                           #
# --------------------------------------------------------------------------- #

def test_fake_clock_sleep_advances_now_and_records():
    clock = FakeClock()
    assert clock.time() == 0.0
    clock.sleep(1.0)
    assert clock.time() == 1.0 and clock.sleeps == [1.0]


def test_stub_opener_records_requests_and_returns_queued_payloads_in_order():
    opener = StubOpener([{"a": 1}, {"b": 2}])

    class _Req:
        full_url = "http://x"
        data = None

        def get_method(self):
            return "GET"

    assert json.loads(opener(_Req()).read()) == {"a": 1}
    assert json.loads(opener(_Req()).read()) == {"b": 2}
    assert _methods(opener) == ["GET", "GET"]
    assert _by_method(opener, "GET") == opener.requests


def test_client_builds_a_write_client_with_injected_opener():
    opener = StubOpener([])
    client = _client(opener)
    assert isinstance(client, WriteClient)


# --------------------------------------------------------------------------- #
# model node / request builders                                               #
# --------------------------------------------------------------------------- #

def test_para_default_and_inlines_superset():
    plain = _para("p1", "hello")
    assert isinstance(plain, TextNode) and plain.block_id == "p1"
    assert plain.content == [Text("hello")]
    custom = _para("p2", "ignored", inlines=[Text("A"), Text("B")])
    assert custom.content == [Text("A"), Text("B")]


def test_heading_default_and_children_superset():
    h = _heading("h1", "Title", level=2)
    assert isinstance(h, HeadingNode) and h.level == 2 and h.children == []
    child = _para("c1", "kid")
    hc = _heading("h2", "Title", children=[child])
    assert hc.children == [child]


def test_page_root():
    page = _page(_para("p1", "x"))
    assert isinstance(page, PageNode) and page.block_id == "root"
    assert page.title == [Text("Doc")]


def test_req_edit_request():
    r = _req("quote", replacement="NEW")
    assert isinstance(r, EditRequest)
    assert r.anchor.quote == "quote" and r.replacement == "NEW"


def test_insert_request_builder():
    ins = _insert("ref", InsertPosition.AFTER, ["a", "b"])
    assert isinstance(ins, InsertRequest)
    assert ins.reference.quote == "ref" and ins.position is InsertPosition.AFTER
    assert [p.text for p in ins.content] == ["a", "b"]


def test_delete_request_builder():
    d = _delete("gone")
    assert isinstance(d, DeleteRequest) and d.target.quote == "gone"


# --------------------------------------------------------------------------- #
# table structural builders                                                   #
# --------------------------------------------------------------------------- #

def test_cell_wraps_inner_text_block():
    cell = _cell("c0", "hi")
    assert isinstance(cell, TableCellNode) and cell.block_id == "c0"
    (inner,) = cell.children
    assert isinstance(inner, TextNode) and inner.block_id == "c0__t"


def test_table_flattens_rows_and_sets_col_size():
    table = _table("t", [[("a", "A"), ("b", "B")], [("c", "C"), ("d", "D")]])
    assert isinstance(table, TableNode) and table.col_size == 2
    assert [c.block_id for c in table.cells] == ["a", "b", "c", "d"]


def test_treq_table_locator_request():
    r = _treq("row-key", column_index=2)
    assert isinstance(r, EditRequest) and isinstance(r.anchor, TableLocator)
    assert r.anchor.row_key == "row-key" and r.anchor.column_index == 2
