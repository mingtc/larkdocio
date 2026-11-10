"""LD-172 — the comments read tells the truth about what it read.

The defect this file pins is not "a wrong number came back". It is that **the read claimed
completeness it had not achieved**: the shipped recipe called ``comments(token, root=root)``,
which returned **5 of the 7** comments on a real document, and ``review.disclosure`` said
flatly *"5 comment(s) read"* with ``missing_ids: ()``. A consumer building a reviewer report
off that shipped a report missing the whole-document objections and had no way to know.

**Everything here runs on real payloads.** The seven comments are the round-2 harvest's six
verbatim listing items (``tests/captures/comments-probe-round2-captures/10-harvest-docx.json``) plus the
whole-document comment the same run created and read back
(``14-demo.json`` → ``demo_list_item_verbatim``) — the exact seven the report counted, on the
exact document it counted them on. The tree is built by the **real parser** from the same
harvest's verbatim anchored blocks, so the anchors the scoped read asks about are the anchors
Lark really reported.

Three properties make the fix defensible rather than cosmetic:

* the **plain** call returns all seven and the **scoped** call returns five, from the SAME one
  API call — so the scoping buys nothing;
* ``for_node`` is **identical** across the two results — so the reason the recipe used
  ``root=`` (per-block lookup) never needed it;
* the two results' ``disclosure`` strings now **differ**, and only the complete one claims the
  file's whole list. Under the old wording they were indistinguishable — that is the bug, and
  the red-then-green pair below is that comparison, mechanized.
"""
import json
import pathlib

import comments_harness as harness
import guide_recipes as gr
from harness import build_blocks

from larkdocio.comments import (
    Comment,
    CommentReply,
    CommentsRead,
    ReplyElement,
    comments,
)
from larkdocio.comments.models import KIND_UNKNOWN_PREFIX, SCOPE_WHOLE_DOCUMENT
from larkdocio.comments.read import (
    ANCHOR_SCOPED_NOTE,
    COMPLETENESS_ANCHOR_SCOPED,
    COMPLETENESS_COMPLETE,
    COMPLETENESS_UNAVAILABLE,
    IMAGE_REPLIES_NOTE,
    REACTIONS_NOT_MODELLED_NOTE,
    UNANCHORED_IDS_NOTE,
)
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CAPTURES = REPO_ROOT / "tests" / "captures" / "comments-probe-round2-captures"
_HARVEST = _CAPTURES / "10-harvest-docx.json"
_DEMO = _CAPTURES / "14-demo.json"

#: The document the report counted on — its real token, so the disclosure strings under test
#: are the strings the report quoted.
DOC_TOKEN = "DocCommentZooExample0000001"

#: The anchored comment the scoped read lost, by the example name the harvest labels it with.
LOST_ANCHORED_EXAMPLE = "Simple"
#: The reply that carries an IMAGE (F14) and the one that was "liked" (reactions, F14).
IMAGE_EXAMPLE = "Image"
LIKE_EXAMPLE = "Like"


def _harvest() -> dict:
    return json.loads(_HARVEST.read_text(encoding="utf-8"))


def _demo_whole_document_item() -> dict:
    """The whole-document comment, verbatim off its own capture.

    It is the class the report cared most about — *"this document is not ready to ship"* — and it
    is **structurally unreachable** from a ``root=`` read: a whole-file comment has no anchor,
    so no set of tree anchors can name it.
    """
    return json.loads(_DEMO.read_text(encoding="utf-8"))["demo_list_item_verbatim"]


def _example_ids() -> dict:
    """``{example name: comment_id}`` off the harvest's own forward join."""
    return {name: rec["comment_id"]
            for name, rec in _harvest()["forward_join_blocks_to_comments"].items()}


def _anchored_items() -> list:
    """The six anchored listing items, verbatim, in the harvest's own order."""
    return list(_harvest()["list_items_verbatim"])


def _all_seven_items() -> list:
    """The file's whole comment list: six anchored + one whole-document."""
    return _anchored_items() + [_demo_whole_document_item()]


def _items_for(ids) -> list:
    wanted = list(ids)
    by_id = {item["comment_id"]: item for item in _all_seven_items()}
    return [by_id[i] for i in wanted if i in by_id]


def _list_body(items) -> dict:
    return {"code": 0, "msg": "Success", "data": {"items": items, "has_more": False}}


def _batch_body(items) -> dict:
    return {"code": 0, "msg": "Success", "data": {"items": items}}


# --------------------------------------------------------------------------- #
# The tree — the real parser over the harvest's own verbatim anchored blocks.    #
# --------------------------------------------------------------------------- #

def _tree_without(example: str):
    """A parsed tree carrying every harvested anchored block **except** ``example``'s.

    That is the report's shape: five of the six anchors reachable from the tree, so the scoped
    read asks for five ids and comes back with five comments while the file holds seven.
    """
    lost = _example_ids()[example]
    records = {
        bid: rec for bid, rec in _harvest()["anchored_blocks"].items()
        if lost not in json.dumps(rec["block_verbatim"])
    }
    assert records and len(records) < len(_harvest()["anchored_blocks"])
    blocks = []
    for record in records.values():
        verbatim = json.loads(json.dumps(record["block_verbatim"]))
        verbatim.pop("children", None)      # their real children are outside this capture
        blocks.append(verbatim)
    root = {
        "block_id": DOC_TOKEN,
        "block_type": 1,
        "page": {"elements": [{"text_run": {"content": "Comment zoo"}}]},
        "children": [b["block_id"] for b in blocks],
    }
    return Parser(Config()).parse_docx_tree(DOC_TOKEN, build_blocks([root] + blocks))


def _plain_read():
    """``comments(token)`` — the whole list, on the double."""
    client = harness.client({"list": _list_body(_all_seven_items())})
    return comments(DOC_TOKEN, client=client), client


def _scoped_read():
    """``comments(token, root=root)`` — the report's call, on the same double."""
    tree = _tree_without(LOST_ANCHORED_EXAMPLE)
    from larkdocio.comments import anchor_ids

    reachable = anchor_ids(tree)
    client = harness.client({"batch_query": _batch_body(_items_for(reachable))})
    return comments(DOC_TOKEN, root=tree, client=client), client


# --------------------------------------------------------------------------- #
# The report's counts, reproduced.                                              #
# --------------------------------------------------------------------------- #

def test_the_plain_call_returns_every_comment_the_file_holds():
    review, _client = _plain_read()
    assert len(review.comments) == 7, [c.comment_id for c in review.comments]
    assert review.api_calls == 1


def test_the_anchor_scoped_call_returns_five_of_the_seven():
    review, _client = _scoped_read()
    assert len(review.comments) == 5, [c.comment_id for c in review.comments]
    # The SAME one API call — the scoping is not a cost trade, which is what makes the
    # recipe's use of it indefensible rather than merely suboptimal.
    assert review.api_calls == 1
    assert review.missing_ids == (), "every anchor the tree carried did resolve"


def test_the_two_comments_the_scoped_call_loses_are_the_anchored_one_and_the_whole_document_one():
    plain, _ = _plain_read()
    scoped, _ = _scoped_read()
    lost = {c.comment_id for c in plain.comments} - {c.comment_id for c in scoped.comments}
    by_id = {c.comment_id: c for c in plain.comments}

    assert lost == {_example_ids()[LOST_ANCHORED_EXAMPLE],
                    _demo_whole_document_item()["comment_id"]}
    scopes = sorted(by_id[i].scope for i in lost)
    assert scopes == ["anchored", SCOPE_WHOLE_DOCUMENT], scopes


def test_for_node_is_IDENTICAL_across_the_two_reads():
    """The finding that makes the demotion defensible: ``root=`` bought nothing at all.

    The reason the recipe passed a tree was per-block lookup — and ``for_node`` reads the
    node's own anchors against ``by_id``, so it resolves just as well on the complete result.
    """
    plain, _ = _plain_read()
    scoped, _ = _scoped_read()
    tree = _tree_without(LOST_ANCHORED_EXAMPLE)
    from larkdocio.model import walk

    def hits(review):
        out = {}
        for node in walk(tree):
            found = [c.comment_id for c in review.for_node(node)]
            for run in getattr(node, "content", None) or ():
                found.extend(c.comment_id for c in review.for_node(run))
            if found:
                out[node.block_id] = found
        return out

    assert hits(plain) == hits(scoped)
    assert hits(plain), "the parity claim is vacuous unless the join actually resolved"


# --------------------------------------------------------------------------- #
# AC2 — the disclosure field for the comment → NO ANCHOR direction.              #
# --------------------------------------------------------------------------- #

def test_the_scoped_read_is_marked_anchor_scoped_and_the_plain_read_complete():
    plain, _ = _plain_read()
    scoped, _ = _scoped_read()
    assert plain.completeness == COMPLETENESS_COMPLETE
    assert scoped.completeness == COMPLETENESS_ANCHOR_SCOPED


def test_unanchored_ids_names_the_comment_no_anchor_can_reach():
    """The direction ``missing_ids`` never covered: a comment with no anchor at all.

    ``missing_ids`` is anchor → no comment. This is comment → no anchor, and on the complete
    read it is nameable exactly: a whole-document comment carries no anchor, so no scoped read
    can ever return it.
    """
    plain, _ = _plain_read()
    assert plain.unanchored_ids == (_demo_whole_document_item()["comment_id"],)
    assert UNANCHORED_IDS_NOTE in plain.notes


def test_an_all_anchored_file_reports_no_unanchored_ids_and_no_such_note():
    client = harness.client({"list": _list_body(_anchored_items())})
    review = comments(DOC_TOKEN, client=client)
    assert review.unanchored_ids == ()
    assert UNANCHORED_IDS_NOTE not in review.notes


def test_the_scoped_read_carries_the_anchor_scoped_note():
    scoped, _ = _scoped_read()
    assert ANCHOR_SCOPED_NOTE in scoped.notes
    assert ANCHOR_SCOPED_NOTE in scoped.disclosure


def test_the_plain_read_carries_no_anchor_scoped_note():
    plain, _ = _plain_read()
    assert ANCHOR_SCOPED_NOTE not in plain.notes


def test_completeness_and_unanchored_ids_survive_a_json_round_trip():
    for review in (_plain_read()[0], _scoped_read()[0]):
        wire = json.loads(json.dumps(review.to_dict()))
        assert wire["completeness"] == review.completeness
        assert wire["unanchored_ids"] == list(review.unanchored_ids)
        back = CommentsRead.from_dict(wire)
        assert back == review
        assert back.completeness == review.completeness
        assert back.unanchored_ids == review.unanchored_ids
        assert back.disclosure == review.disclosure


def test_an_unavailable_read_is_marked_unavailable_however_it_was_built():
    """The never-silent normalization: a read that failed cannot be labelled complete."""
    hand = CommentsRead(file_token=DOC_TOKEN, available=False,
                        unavailable_reason="the file is gone")
    assert hand.completeness == COMPLETENESS_UNAVAILABLE


# --------------------------------------------------------------------------- #
# AC3 — `disclosure` cannot claim completeness it did not achieve.               #
# --------------------------------------------------------------------------- #

def _legacy_head(review) -> str:
    """The wording that shipped, reproduced here so the bite is the real comparison.

    This is ``CommentsRead.disclosure``'s head as of the tested wheel, verbatim. It is a
    function of the COUNT alone — which is precisely why it read identically for a complete
    read and for a scoped one that had silently dropped two comments.
    """
    if review.comments:
        return (f"{len(review.comments)} comment(s) read for {review.file_token}"
                f" ({review.file_type}).")
    return (f"No comments on {review.file_token} ({review.file_type}) — the read "
            f"succeeded and found none.")


def test_the_old_wording_claimed_completeness_for_BOTH_reads_red():
    """RED: the shipped head is indistinguishable between the two reads except for a digit.

    Neither string contains a word about scoping, so the 5-of-7 read reported the same kind of
    fact as the 7-of-7 one. That is the defect, stated as an assertion.
    """
    plain, _ = _plain_read()
    scoped, _ = _scoped_read()
    old_plain, old_scoped = _legacy_head(plain), _legacy_head(scoped)
    assert old_plain.replace("7 ", "N ") == old_scoped.replace("5 ", "N ")
    for old in (old_plain, old_scoped):
        assert "scope" not in old.lower() and "anchor" not in old.lower()


def test_the_new_wording_names_the_gap_and_the_two_disclosures_differ_green():
    """GREEN: only the complete read claims the file's whole list; the scoped one says it is
    scoped, and names both counts rather than hedging."""
    plain, _ = _plain_read()
    scoped, _ = _scoped_read()

    assert "whole comment list" in plain.disclosure
    assert "7 comment(s) read" in plain.disclosure

    assert "whole comment list" in scoped.disclosure, (
        "the scoped line must name the whole list it is NOT")
    assert "NOT the file's whole comment list" in scoped.disclosure
    assert "5 comment(s) read" in scoped.disclosure
    assert "5 review anchor(s)" in scoped.disclosure

    assert plain.disclosure != scoped.disclosure


def test_a_tree_with_no_anchors_no_longer_reports_that_the_file_has_NO_comments():
    """The worst instance of the same lie, and the cheapest to hit.

    A document whose tree carries no anchor costs no API call — a real optimization — but the
    old wording turned it into *"the read succeeded and found none"* on a file that holds
    seven comments.
    """
    from larkdocio.model import PageNode, Text

    bare = PageNode(title=[Text("Comment zoo")], children=[])
    client = harness.client({})
    review = comments(DOC_TOKEN, root=bare, client=client)

    assert review.api_calls == 0 and review.comments == ()
    assert review.completeness == COMPLETENESS_ANCHOR_SCOPED
    assert "found none" not in review.disclosure
    assert "NOT the file's whole comment list" in review.disclosure
    assert "found none" in _legacy_head(review), "the red half of this pair"


def test_a_read_that_genuinely_found_nothing_still_says_so_plainly():
    """The distinction must not collapse the other way: an empty COMPLETE read is a real,
    ordinary answer and still reads as one."""
    client = harness.client({"list": _list_body([])})
    review = comments(DOC_TOKEN, client=client)
    assert review.completeness == COMPLETENESS_COMPLETE
    assert "found none" in review.disclosure


# --------------------------------------------------------------------------- #
# AC4 (F14) — an image-bearing reply, an unmodelled element, and reactions.      #
# --------------------------------------------------------------------------- #

def _reply_of(example: str) -> CommentReply:
    item = _items_for([_example_ids()[example]])[0]
    return Comment.from_wire(item).replies[0]


def test_an_image_bearing_reply_reports_the_image_it_carries():
    """F14: the zoo's *Comment with Image Embedded* came back as plain text and the image
    vanished. The image is NOT an element — it is ``reply.extra.image_list`` — so the model
    has to read it there, and the reply now says an image is part of what the reviewer said.
    """
    reply = _reply_of(IMAGE_EXAMPLE)
    assert reply.image_tokens == ("Example275b62835dfea3441291",)
    # The text projection is unchanged — a token is not text, and inventing a placeholder
    # inside the reviewer's sentence would be worse than reporting it beside it.
    assert reply.text == "Comment with Image Embedded"


def test_a_reply_with_no_image_reports_no_image_tokens():
    assert _reply_of(LIKE_EXAMPLE).image_tokens == ()


def test_the_comment_flattens_its_replies_image_tokens():
    item = _items_for([_example_ids()[IMAGE_EXAMPLE]])[0]
    assert Comment.from_wire(item).image_tokens == ("Example275b62835dfea3441291",)


def test_image_tokens_survive_a_json_round_trip():
    reply = _reply_of(IMAGE_EXAMPLE)
    assert CommentReply.from_dict(json.loads(json.dumps(reply.to_dict()))) == reply


def test_the_read_discloses_that_a_reply_carries_an_image():
    client = harness.client({"list": _list_body(_all_seven_items())})
    review = comments(DOC_TOKEN, client=client)
    assert IMAGE_REPLIES_NOTE in review.notes
    assert IMAGE_REPLIES_NOTE in review.disclosure


def test_a_read_with_no_image_bearing_reply_carries_no_image_note():
    client = harness.client(
        {"list": _list_body(_items_for([_example_ids()[LIKE_EXAMPLE]]))})
    review = comments(DOC_TOKEN, client=client)
    assert IMAGE_REPLIES_NOTE not in review.notes


def test_the_liked_comment_carries_no_reaction_field_in_the_payload_at_all():
    """The evidence behind the DISCLOSE call: reactions are not in the response.

    The zoo's *Comment with a Like* is liked in the Lark UI, and its verbatim listing item
    carries no reaction key anywhere. So modelling reactions would mean inventing a field the
    API never sends; disclosing that they are unread is the only honest option.
    """
    item = _items_for([_example_ids()[LIKE_EXAMPLE]])[0]
    assert "react" not in json.dumps(item).lower()
    assert "like" not in [k.lower() for k in item]


def test_a_read_that_found_comments_discloses_that_reactions_are_unread():
    client = harness.client({"list": _list_body(_all_seven_items())})
    review = comments(DOC_TOKEN, client=client)
    assert REACTIONS_NOT_MODELLED_NOTE in review.notes
    assert REACTIONS_NOT_MODELLED_NOTE in review.disclosure


def test_an_empty_read_does_not_bother_disclosing_reactions():
    client = harness.client({"list": _list_body([])})
    assert REACTIONS_NOT_MODELLED_NOTE not in comments(DOC_TOKEN, client=client).notes


def test_the_read_surface_descriptor_states_that_reactions_are_unread():
    """The DISCLOSE call, made discoverable from the registry as well as from a read."""
    from larkdocio.capabilities import capabilities

    summary = capabilities(full=True)["surfaces"]["docx-comments-read"]["levels"]["summary"].lower()
    assert "reaction" in summary


def test_an_unmodelled_reply_element_is_EMITTED_tagged_not_elided():
    """The convention the projection already owns, pinned: an element whose type this model
    does not know keeps the server's own label behind ``unknown:`` and stays in ``elements``.

    Built by taking a real reply and replacing its element with one of a type the SDK does not
    model — the shape a future element kind arrives in.
    """
    item = json.loads(json.dumps(_items_for([_example_ids()[IMAGE_EXAMPLE]])[0]))
    item["reply_list"]["replies"][0]["content"]["elements"] = [
        {"type": "reaction", "text_run": None, "person": None, "docs_link": None},
    ]
    (element,) = Comment.from_wire(item).replies[0].elements
    assert element.kind == KIND_UNKNOWN_PREFIX + "reaction"
    assert element.text == ""
    assert ReplyElement.from_dict(json.loads(json.dumps(element.to_dict()))) == element


def test_an_unknown_element_beside_a_known_one_neither_displaces_it_nor_vanishes():
    item = json.loads(json.dumps(_items_for([_example_ids()[IMAGE_EXAMPLE]])[0]))
    elements = item["reply_list"]["replies"][0]["content"]["elements"]
    elements.append({"type": "sticker", "text_run": None, "person": None, "docs_link": None})
    reply = Comment.from_wire(item).replies[0]
    assert [e.kind for e in reply.elements] == ["text", KIND_UNKNOWN_PREFIX + "sticker"]
    assert reply.text == "Comment with Image Embedded"


# --------------------------------------------------------------------------- #
# AC1 — the recipe reads the comments on the document.                          #
# --------------------------------------------------------------------------- #

_RECIPE = "read-the-comments-on-a-document"


def _recipe_source() -> str:
    return gr.recipe_source(_RECIPE)


def _comments_calls(src: str):
    """Every live ``comments(...)`` call in the recipe, as AST nodes.

    Read off the parse tree rather than by substring, because the recipe's **prose** names the
    scoped call in order to document it — the fact under test is which call the recipe *makes*.
    """
    import ast

    return [n for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "comments"]


def test_the_recipe_calls_comments_with_the_token_ALONE():
    """The headline fix: a recipe titled *read the comments on a document* reads them all."""
    calls = _comments_calls(_recipe_source())
    assert len(calls) == 1, f"expected exactly one comments() call, got {len(calls)}"
    (call,) = calls
    assert [k.arg for k in call.keywords] == [], (
        "the recipe must not recommend the anchor-scoped call: it cannot return a "
        "whole-document comment at all, and costs the same one API call")
    assert len(call.args) == 1 and getattr(call.args[0], "id", None) == "doc_token"


def test_no_commented_out_line_in_the_recipe_promotes_back_to_the_scoped_call():
    """The uncomment trap: a consumer pastes the recipe and uncomments what looks helpful.

    A commented-out **statement** re-introducing ``root=`` would put the defect back one
    keystroke away, so the harness's own commented-statement detector is asserted over it.
    """
    for commented in gr.commented_code_lines(_recipe_source()):
        assert "root=" not in commented.code, commented


def test_the_recipe_still_teaches_the_per_block_join_from_the_plain_result():
    """The demotion must not cost the recipe its most useful half — the block → comments
    lookup, which never needed the scoping argument."""
    src = _recipe_source()
    assert "review.for_node(node)" in src
    assert "review.for_node(run)" in src


def test_the_recipe_preamble_documents_the_scoping_argument_as_an_optimization_with_its_cost():
    """``root=`` stays documented — as what it is. Both halves must be in the same breath:
    the benefit (no anchors ⇒ no call) and the cost (it cannot return a whole-document
    comment, and may return fewer than the file holds)."""
    import doc_prose

    preamble = doc_prose.prose(gr.recipe_preamble(_RECIPE))
    for phrase in (
        "no API call",
        "cannot return",
        "whole-document comment",
        "fewer comments than the file holds",
        "same single API call",
    ):
        assert doc_prose.prose(phrase) in preamble, (
            f"the recipe's preamble does not state: {phrase!r}")


def test_the_recipe_preamble_teaches_the_completeness_marker():
    import doc_prose

    preamble = doc_prose.prose(gr.recipe_preamble(_RECIPE))
    assert doc_prose.prose("completeness") in preamble
    assert doc_prose.prose("anchor-scoped") in preamble
