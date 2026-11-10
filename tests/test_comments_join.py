"""The join: from a parsed document's own review anchors to the reviewers' words.

The document reader already records, on every block and on every styled run, the review
anchors the API reported there. Those are ids — on their own they say only *something was
commented here*. This file is about turning them into the comments themselves, and about the
four ways that could go wrong: asking for nothing and paying for it anyway, asking twice for
the same id, losing an id that resolves to nothing, and losing the block-versus-run
distinction.

It also pins the two things the surface must NOT do: consult the identity service, and claim
a comment-to-block mapping the API cannot support.
"""
import comments_harness as harness
import comments_payloads as payloads
import pytest

from larkdocio.comments import (
    REVERSE_JOIN_NOTE,
    Comment,
    CommentsRead,
    anchor_ids,
    comments,
)
from larkdocio.comments.read import MISSING_IDS_NOTE, node_anchor_ids
from larkdocio.model import (
    GridNode,
    HeadingNode,
    PageNode,
    StyledText,
    TableCellNode,
    TableNode,
    Text,
    TextNode,
)

_ITEM = payloads.LIST_ONE_PAGE["data"]["items"][0]


def _batch(*ids):
    """A batch-fetch response body carrying one comment per id, on the captured shape."""
    return {"code": 0, "msg": "Success",
            "data": {"items": [dict(_ITEM, comment_id=cid) for cid in ids]}}


def _para(text, *, block_ids=None, runs=()):
    content = [Text(text)] if not runs else list(runs)
    return TextNode(content=content, block_id="b1", comment_ids=block_ids)


# --------------------------------------------------------------------------- #
# Anchor collection — both granularities, every container shape.                 #
# --------------------------------------------------------------------------- #

def test_a_block_level_anchor_is_collected():
    root = PageNode(title=[Text("Doc")], children=[_para("hi", block_ids=["c-block"])])
    assert anchor_ids(root) == ("c-block",)


def test_a_word_level_anchor_on_a_styled_run_is_collected():
    run = StyledText("twelve point four", bold=True, comment_ids=["c-run"])
    root = PageNode(title=[Text("Doc")], children=[_para("x", runs=[Text("a "), run])])
    assert anchor_ids(root) == ("c-run",)


def test_a_block_and_a_run_anchor_on_the_SAME_block_are_both_collected():
    run = StyledText("figure", comment_ids=["c-run"])
    node = TextNode(content=[Text("the "), run], block_id="b1", comment_ids=["c-block"])
    root = PageNode(title=[Text("Doc")], children=[node])

    assert anchor_ids(root) == ("c-block", "c-run")
    # And each level still reports its own, un-merged — the two are independent facts.
    assert node_anchor_ids(node) == ("c-block",)
    assert node_anchor_ids(run) == ("c-run",)


def test_two_runs_in_one_block_carrying_DIFFERENT_anchors_are_both_collected():
    first = StyledText("first", comment_ids=["c-1"])
    second = StyledText("second", comment_ids=["c-2"])
    node = TextNode(content=[first, Text(" and "), second], block_id="b1")
    root = PageNode(title=[Text("Doc")], children=[node])

    assert anchor_ids(root) == ("c-1", "c-2")
    assert node_anchor_ids(first) == ("c-1",)
    assert node_anchor_ids(second) == ("c-2",)


def test_the_SAME_anchor_on_a_block_and_on_a_run_is_de_duplicated_for_the_QUERY_only():
    """De-duplication belongs to the request, not to the model: both nodes keep the id."""
    run = StyledText("figure", comment_ids=["c-same"])
    node = TextNode(content=[run], block_id="b1", comment_ids=["c-same"])
    root = PageNode(title=[Text("Doc")], children=[node])

    assert anchor_ids(root) == ("c-same",), "the query must ask once"
    assert node_anchor_ids(node) == ("c-same",)
    assert node_anchor_ids(run) == ("c-same",)


def test_anchors_are_collected_through_every_container_shape():
    """Children, table cells and grid columns — a comment inside a table must not vanish."""
    cell = TableCellNode(
        children=[TextNode(content=[Text("cell")], block_id="t1__t",
                           comment_ids=["c-in-cell"])],
        block_id="t1")
    table = TableNode(cells=[cell], col_size=1, block_id="tbl")
    # A grid holds ONE LIST of child nodes per column — there is no wrapper node in the
    # tree, which is exactly why the walk reads ``columns`` as a list of lists.
    in_grid = TextNode(content=[Text("col")], block_id="g1", comment_ids=["c-in-grid"])
    grid = GridNode(columns=[[in_grid]], block_id="grid")
    deep = HeadingNode(level=1, content=[Text("H")], block_id="h",
                       children=[TextNode(content=[Text("deep")], block_id="d",
                                          comment_ids=["c-deep"])])
    root = PageNode(title=[Text("Doc")], children=[table, grid, deep])

    assert set(anchor_ids(root)) == {"c-in-cell", "c-in-grid", "c-deep"}


def test_an_absent_anchor_list_and_an_empty_one_both_collect_nothing():
    """The absent-versus-empty distinction lives on the node; neither is an anchor to ask
    about, and neither may be turned into the other here."""
    absent = TextNode(content=[Text("a")], block_id="b1")
    empty = TextNode(content=[Text("b")], block_id="b2", comment_ids=[])
    assert absent.comment_ids is None and empty.comment_ids == []
    assert anchor_ids(PageNode(title=[Text("D")], children=[absent, empty])) == ()


# --------------------------------------------------------------------------- #
# AC2 — the read, joined.                                                       #
# --------------------------------------------------------------------------- #

def test_a_document_with_NO_anchors_makes_NO_call_at_all():
    """Asserted with a call spy, not by reading the code."""
    client = harness.client({"batch_query": _batch("anything")})
    root = PageNode(title=[Text("Doc")], children=[_para("nothing anchored here")])

    result = comments("doc-token", root=root, client=client)

    assert client._sdk.calls == [], "a document with no anchors must cost nothing"
    assert result.api_calls == 0
    assert result.available is True and result.comments == ()
    assert result.requested_ids == () and result.missing_ids == ()


def test_the_anchors_are_resolved_in_one_batch_and_reachable_per_block_and_per_run():
    run = StyledText("twelve point four", comment_ids=["c-run"])
    node = TextNode(content=[Text("the "), run], block_id="b1", comment_ids=["c-block"])
    root = PageNode(title=[Text("Doc")], children=[node])
    client = harness.client({"batch_query": _batch("c-block", "c-run")})

    result = comments("doc-token", root=root, client=client)

    assert client._sdk.ops == ["batch_query"], "one batch, not one call per id"
    assert client._sdk.requests_for("batch_query")[0].request_body.comment_ids == [
        "c-block", "c-run"]
    assert [c.comment_id for c in result.for_node(node)] == ["c-block"]
    assert [c.comment_id for c in result.for_node(run)] == ["c-run"]
    assert result.missing_ids == ()


def test_a_hundred_anchors_go_out_as_ONE_batch():
    ids = [f"c-{i:03d}" for i in range(100)]
    nodes = [TextNode(content=[Text(str(i))], block_id=f"b{i}", comment_ids=[cid])
             for i, cid in enumerate(ids)]
    root = PageNode(title=[Text("Doc")], children=nodes)
    client = harness.client({"batch_query": _batch(*ids)})

    result = comments("doc-token", root=root, client=client)

    assert len(client._sdk.calls) == 1
    assert client._sdk.requests_for("batch_query")[0].request_body.comment_ids == ids
    assert len(result.comments) == 100
    assert result.api_calls == 1


def test_an_id_that_resolves_to_nothing_is_REPORTED_never_silently_dropped():
    """The pinned decision: report-as-missing. A comment removed between the document read
    and the comments read is a race, not a caller error — refusing the whole read for it
    would hide every other reviewer's words."""
    node = TextNode(content=[Text("x")], block_id="b1",
                    comment_ids=["c-alive", "c-removed"])
    root = PageNode(title=[Text("Doc")], children=[node])
    client = harness.client({"batch_query": _batch("c-alive")})

    result = comments("doc-token", root=root, client=client)

    assert result.available is True, "one stale anchor must not fail the whole read"
    assert result.missing_ids == ("c-removed",)
    assert result.requested_ids == ("c-alive", "c-removed")
    assert [c.comment_id for c in result.for_node(node)] == ["c-alive"]
    assert MISSING_IDS_NOTE in result.notes
    assert "resolved to no comment" in result.disclosure


def test_without_a_tree_the_whole_list_is_read_instead():
    client = harness.client({"list": payloads.LIST_ONE_PAGE})
    result = comments("doc-token", client=client)

    assert client._sdk.ops == ["list"]
    assert [c.comment_id for c in result.comments] == ["7667710952829095653"]
    assert result.requested_ids == () and result.missing_ids == ()


def test_a_truncated_thread_is_COMPLETED_rather_than_reported_as_its_first_page():
    body = {"code": 0, "msg": "Success",
            "data": {"items": [payloads.COMMENT_WITH_TRUNCATED_THREAD]}}
    client = harness.client({
        "batch_query": body,
        "reply_list": payloads.REPLY_LIST_PAGE_TWO,
    })
    node = TextNode(content=[Text("x")], block_id="b1",
                    comment_ids=["7667710952829095653"])
    root = PageNode(title=[Text("Doc")], children=[node])

    result = comments("doc-token", root=root, client=client)

    assert client._sdk.ops == ["batch_query", "reply_list"]
    assert client._sdk.requests_for("reply_list")[0].page_token == "reply-page-2"
    assert [r.reply_id for r in result.comments[0].replies] == ["reply-1", "reply-2"]
    assert result.comments[0].text == "first page reply\nsecond page reply"


# --------------------------------------------------------------------------- #
# AC5 — authorship stays raw, and the identity service is NEVER called.          #
# --------------------------------------------------------------------------- #

def test_the_author_is_exposed_as_the_RAW_id():
    client = harness.client({"list": payloads.LIST_ONE_PAGE})
    result = comments("doc-token", client=client)
    assert result.comments[0].user_id == "ou_examplebot0000000000000000000001"


def test_NO_identity_lookup_is_ATTEMPTED_for_any_author_or_mention():
    """A call-count spy over the endpoint paths actually requested. The mentioned id in this
    payload is one the identity endpoint refuses on this library's scopes; the surface does
    not go and find that out."""
    body = {"code": 0, "msg": "Success",
            "data": {"items": [dict(_ITEM, comment_id="c1", reply_list=(
                payloads.CREATE_WITH_PERSON_MENTION["data"]["reply_list"]))]}}
    node = TextNode(content=[Text("x")], block_id="b1", comment_ids=["c1"])
    root = PageNode(title=[Text("Doc")], children=[node])
    client = harness.client({"batch_query": body})

    result = comments("doc-token", root=root, client=client)

    assert result.comments[0].mentioned_user_ids == (
        "ou_examplebot0000000000000000000001",)
    assert len(client._sdk.paths) == 1
    assert all("/comments" in p for p in client._sdk.paths), client._sdk.paths
    assert not any("contact" in p for p in client._sdk.paths), (
        "the identity service was consulted — no name may be guessed for an author")


def test_the_surface_never_imports_the_identity_endpoint_at_all():
    """Structural companion to the call spy: the module cannot regress into a lookup,
    because the request class for one is not even reachable from here."""
    import ast
    import inspect

    from larkdocio.comments import client as client_mod
    from larkdocio.comments import models, read

    for module in (client_mod, models, read):
        source = inspect.getsource(module)
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                text = ast.unparse(node)
                assert "contact" not in text, f"{module.__name__} imports {text!r}"


def test_no_human_versus_application_flag_is_INVENTED():
    """The payload carries no such discriminator, so the model must not offer one."""
    fields = set(Comment.__dataclass_fields__)
    for invented in ("is_bot", "is_app", "user_type", "author_name", "display_name",
                     "is_human"):
        assert invented not in fields, f"{invented!r} is not in any payload — do not infer it"
    assert not any(hasattr(Comment, name) for name in ("is_bot", "user_type"))


# --------------------------------------------------------------------------- #
# AC10 — the reverse join is absent, and says why.                              #
# --------------------------------------------------------------------------- #

def test_the_comment_to_block_mapping_is_NOT_shipped():
    """No relation field on the model, no need-relation on the wire, no method offering it."""
    fields = set(Comment.__dataclass_fields__) | set(CommentsRead.__dataclass_fields__)
    for absent in ("relation", "position_info", "block_id", "position"):
        assert absent not in fields, (
            f"{absent!r} would be a comment-to-block claim this API cannot support")
    for absent in ("for_comment", "block_of", "relation", "position_of"):
        assert not hasattr(CommentsRead, absent)

    import inspect

    from larkdocio.comments import client as client_mod
    source = inspect.getsource(client_mod)
    assert "need_relation" not in source, (
        "the relation flag is not requested — the field it populates cannot be verified")


def test_the_absence_is_DOCUMENTED_with_its_reason():
    note = REVERSE_JOIN_NOTE
    assert "NOT implemented" in note and "NOT claimed to work" in note
    assert "cannot be created through the" in note, "the reason must be stated, not implied"
    for surface in (__import__("larkdocio.comments", fromlist=["x"]).__doc__,):
        assert "not implemented" in surface.lower()


def test_the_captured_relation_request_really_came_back_without_the_field():
    """The evidence behind the decision, kept executable: the probe asked for the relation
    and the response carried no such key."""
    item = payloads.BATCH_QUERY_ONE["data"]["items"][0]
    assert "relation" not in item
    assert "position_info" not in item


# --------------------------------------------------------------------------- #
# The walk agrees with the writer's own container-shape enumeration.             #
# --------------------------------------------------------------------------- #

def test_the_anchor_walk_sees_every_container_shape_the_writer_walk_does():
    """A drift guard instead of a cross-surface import: each surface enumerates container
    shapes for itself, so the enumerations are joined here. A fourth container added to
    the model reddens this until every walk knows about it.

    Three surfaces enumerate them now — the anchor collection here, the writer's anchor
    resolver, and the public ``model.walk`` a consumer is handed. Silently reaching only part
    of a document is precisely the defect the public walk exists to prevent, so it is joined
    to the same guard rather than trusted to stay in step.
    """
    from larkdocio.comments.read import _child_sequences as read_walk
    from larkdocio.model.tree import _child_sequences as model_walk
    from larkdocio.write.resolve import _child_sequences as write_walk

    cell = TableCellNode(children=[TextNode(content=[Text("c")], block_id="t1__t")],
                         block_id="t1")
    in_grid = TextNode(content=[Text("g")], block_id="g1")
    for node in (
        PageNode(title=[Text("D")], children=[cell]),
        TableNode(cells=[cell], col_size=1, block_id="tbl"),
        GridNode(columns=[[in_grid]], block_id="grid"),
        HeadingNode(level=1, content=[Text("H")], block_id="h", children=[cell]),
        TextNode(content=[Text("x")], block_id="b1"),
    ):
        mine = [id(child) for seq in read_walk(node) for child in seq]
        theirs = [id(child) for seq in write_walk(node) for child in seq]
        public = [id(child) for seq in model_walk(node) for child in seq]
        assert mine == theirs, f"the two container walks disagree on {type(node).__name__}"
        assert public == mine, (
            f"the PUBLIC model.walk container shapes disagree with the anchor walk's on "
            f"{type(node).__name__} — one of them reaches less of a document than the other"
        )


# --------------------------------------------------------------------------- #
# The result object.                                                            #
# --------------------------------------------------------------------------- #

def test_the_result_round_trips_through_json():
    import json

    client = harness.client({"list": payloads.LIST_ONE_PAGE})
    result = comments("doc-token", client=client)
    assert CommentsRead.from_dict(json.loads(json.dumps(result.to_dict()))) == result


def test_the_result_is_frozen():
    assert CommentsRead.__dataclass_params__.frozen is True


def test_lookups_skip_ids_that_are_not_present_without_raising():
    client = harness.client({"list": payloads.LIST_ONE_PAGE})
    result = comments("doc-token", client=client)
    assert result.for_ids(["nope"]) == ()
    assert result.for_node(TextNode(content=[Text("x")], block_id="b")) == ()


@pytest.mark.parametrize("root", [None])
def test_a_none_tree_reads_the_list_rather_than_asking_for_nothing(root):
    client = harness.client({"list": payloads.LIST_ONE_PAGE})
    result = comments("doc-token", root=root, client=client)
    assert client._sdk.ops == ["list"] and len(result.comments) == 1
