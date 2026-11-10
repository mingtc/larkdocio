"""Offline unit tests for the anchor resolution engine (LD-066).

W1-S2 resolves an :class:`EditRequest` (LD-065: anchor = verbatim quote + breadcrumb
heading-path) against the reader's parsed node tree — W0's ``block_id`` provenance on
each block node is the addressing key — to **exactly one target block or a typed
refusal, never a guess**. The spike (``dev/write-spike/07-report.md``) proved the one
hard problem is anchor resolution, not the API: a verbatim quote is *not* a unique
locator (one sentence matched 5 blocks; ``97.2%`` matched 6), so those become fixtures
that must **refuse** (``ambiguous-N-candidates``). Quote match is verbatim substring on
a block's own plain text; breadcrumb narrows; write-hostile targets (image/board/embed/
synced — the spike's list) refuse. Fully offline; goldens ZERO-DRIFT is a gate.
"""

from harness import build_blocks

from larkdocio.model import (
    BitableNode,
    BoardNode,
    CalloutNode,
    DocumentNode,
    HeadingNode,
    IframeNode,
    ImageNode,
    PageNode,
    ReferenceBaseNode,
    ReferenceSyncedNode,
    SheetNode,
    SourceSyncedNode,
    Text,
    TextNode,
)
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.write.model import (
    Anchor,
    DeleteRequest,
    EditRequest,
    InsertPosition,
    InsertRequest,
    NewParagraph,
    RefusalReason,
)
from larkdocio.write.resolve import (
    WRITE_HOSTILE_NODE_TYPES,
    ResolvedInsertion,
    ResolvedTarget,
    block_plain_text,
    resolve,
)


# --------------------------------------------------------------------------- #
# tiny helpers to build offline node trees                                     #
# --------------------------------------------------------------------------- #

def _para(bid, text):
    return TextNode(content=[Text(text)], block_id=bid)


def _heading(bid, text, level=1):
    return HeadingNode(level=level, content=[Text(text)], block_id=bid)


def _page(*children):
    return PageNode(title=[Text("Doc")], children=list(children), block_id="root")


def _req(quote, breadcrumb=()):
    return EditRequest(anchor=Anchor(quote=quote, breadcrumb=breadcrumb), replacement="X")


# --------------------------------------------------------------------------- #
# AC1 — exactly-one-or-refuse (never >1, never auto-pick)                       #
# --------------------------------------------------------------------------- #

def test_resolve_returns_resolved_target_for_a_unique_match():
    tree = _page(_para("p1", "The sky is blue."), _para("p2", "Grass is green."))
    result = resolve(_req("The sky is blue."), tree)
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "p1"


def test_resolve_returns_a_typed_refusal_or_a_resolved_target_only():
    tree = _page(_para("p1", "unique line"))
    ok = resolve(_req("unique line"), tree)
    miss = resolve(_req("nowhere"), tree)
    assert isinstance(ok, ResolvedTarget)
    # a refusal is NOT a ResolvedTarget and carries a typed reason
    assert not isinstance(miss, ResolvedTarget)
    assert miss.reason in set(RefusalReason)


def test_resolver_never_auto_picks_among_candidates():
    # Two blocks contain the quote and there is no breadcrumb to narrow → the
    # resolver refuses rather than returning one (or both).
    tree = _page(_para("p1", "same sentence"), _para("p2", "same sentence"))
    result = resolve(_req("same sentence"), tree)
    assert not isinstance(result, ResolvedTarget)
    assert result.reason is RefusalReason.AMBIGUOUS


# --------------------------------------------------------------------------- #
# AC2 — quote match: verbatim substring on a block's own plain text             #
# --------------------------------------------------------------------------- #

def test_unique_quote_resolves_to_the_one_block():
    tree = _page(
        _para("a", "Intro paragraph."),
        _para("b", "Revenue grew 12.4% in Q3."),
        _para("c", "Closing remarks."),
    )
    assert resolve(_req("Revenue grew 12.4% in Q3."), tree).block_id == "b"


def test_quote_matches_a_substring_within_a_larger_paragraph():
    tree = _page(_para("a", "The quarterly figure was 12.4% overall this year."))
    assert resolve(_req("12.4%"), tree).block_id == "a"


def test_quote_match_is_verbatim_not_normalized():
    # Different casing / trailing whitespace is NOT a verbatim substring → not-found.
    tree = _page(_para("a", "Total revenue"))
    assert resolve(_req("total revenue"), tree).reason is RefusalReason.NOT_FOUND
    assert resolve(_req("Total  revenue"), tree).reason is RefusalReason.NOT_FOUND


def test_block_plain_text_is_the_blocks_own_text_not_its_children():
    # A heading's plain text is only its own line, not the section beneath it.
    heading = _heading("h", "Results")
    para = _para("p", "Revenue grew.")
    page = PageNode(title=[Text("Doc")], children=[heading, para], block_id="root")
    assert block_plain_text(heading) == "Results"
    assert block_plain_text(para) == "Revenue grew."
    assert block_plain_text(page) == "Doc"  # page title is its own text


# --------------------------------------------------------------------------- #
# AC3 — breadcrumb narrows when the quote alone is ambiguous                    #
# --------------------------------------------------------------------------- #

def test_same_quote_under_two_headings_resolves_via_breadcrumb():
    # The identical sentence sits under two different headings (flat siblings, the
    # common Feishu shape). The breadcrumb picks the right one.
    tree = _page(
        _heading("hA", "Alpha"),
        _para("pA", "shared sentence"),
        _heading("hB", "Beta"),
        _para("pB", "shared sentence"),
    )
    assert resolve(_req("shared sentence", ("Alpha",)), tree).block_id == "pA"
    assert resolve(_req("shared sentence", ("Beta",)), tree).block_id == "pB"


def test_breadcrumb_narrows_nested_heading_path():
    tree = _page(
        _heading("h1", "Results", level=1),
        _heading("h2", "Q3", level=2),
        _para("p1", "the metric"),
        _heading("h1b", "Outlook", level=1),
        _para("p2", "the metric"),
    )
    # Full path, nearest heading, and outer heading all narrow to p1 (contiguous sub-path).
    assert resolve(_req("the metric", ("Results", "Q3")), tree).block_id == "p1"
    assert resolve(_req("the metric", ("Q3",)), tree).block_id == "p1"
    assert resolve(_req("the metric", ("Outlook",)), tree).block_id == "p2"


def test_breadcrumb_that_narrows_to_zero_is_not_found():
    # Quote matches two blocks but the breadcrumb points at no matching heading path.
    tree = _page(
        _heading("hA", "Alpha"),
        _para("pA", "dup"),
        _heading("hB", "Beta"),
        _para("pB", "dup"),
    )
    assert resolve(_req("dup", ("Gamma",)), tree).reason is RefusalReason.NOT_FOUND


# --------------------------------------------------------------------------- #
# AC4 — the spike's 5-way / 6-way ambiguity become fixtures that REFUSE         #
# --------------------------------------------------------------------------- #

def test_five_way_same_sentence_refuses_ambiguous():
    # Spike Test 2: one verbatim sentence matched 5 blocks.
    ids = [f"blk{i}" for i in range(5)]
    tree = _page(*[_para(b, "On-time delivery improved.") for b in ids])
    result = resolve(_req("On-time delivery improved."), tree)
    assert result.reason is RefusalReason.AMBIGUOUS
    assert result.candidate_count == 5
    assert list(result.candidate_ids) == ids  # document order, all five carried


def test_six_way_value_refuses_ambiguous():
    # Spike Test 5: the value 97.2% appeared in 6 blocks (as a substring).
    ids = [f"cell{i}" for i in range(6)]
    tree = _page(*[_para(b, f"Metric {b} value 97.2% recorded.") for b in ids])
    result = resolve(_req("97.2%"), tree)
    assert result.reason is RefusalReason.AMBIGUOUS
    assert result.candidate_count == 6
    assert set(result.candidate_ids) == set(ids)


def test_ambiguous_is_a_refusal_never_a_target():
    tree = _page(_para("p1", "same"), _para("p2", "same"), _para("p3", "same"))
    assert not isinstance(resolve(_req("same"), tree), ResolvedTarget)


# --------------------------------------------------------------------------- #
# AC5 — a quote matching no block refuses not-found                             #
# --------------------------------------------------------------------------- #

def test_quote_matching_no_block_refuses_not_found():
    tree = _page(_para("p1", "hello"), _para("p2", "world"))
    assert resolve(_req("absent quote"), tree).reason is RefusalReason.NOT_FOUND


def test_empty_quote_is_a_degenerate_anchor_not_found():
    tree = _page(_para("p1", "anything"))
    assert resolve(_req(""), tree).reason is RefusalReason.NOT_FOUND


# --------------------------------------------------------------------------- #
# AC6 — write-hostile targets refuse, even if otherwise unique                  #
# --------------------------------------------------------------------------- #

def test_write_hostile_image_refuses_even_if_unique():
    # The quote resolves to exactly one block, but it is an image → refuse.
    tree = _page(
        _para("p", "ordinary paragraph"),
        ImageNode(caption="quarterly revenue chart", block_id="img"),
    )
    result = resolve(_req("quarterly revenue chart"), tree)
    assert result.reason is RefusalReason.WRITE_HOSTILE


def test_write_hostile_synced_block_refuses():
    tree = _page(
        SourceSyncedNode(content=[Text("synced content line")], block_id="sync"),
    )
    result = resolve(_req("synced content line"), tree)
    assert result.reason is RefusalReason.WRITE_HOSTILE


def test_write_hostile_embed_iframe_refuses():
    tree = _page(
        IframeNode(url="https://embed.example/dashboard", block_id="frame"),
    )
    result = resolve(_req("embed.example/dashboard"), tree)
    assert result.reason is RefusalReason.WRITE_HOSTILE


def test_write_hostile_set_covers_the_spikes_image_board_embed_synced_list():
    # Detected BY BLOCK TYPE. Board carries no quotable text, so its category is
    # covered at the type level (a board can only ever be not-found or type-caught).
    for cls in (
        ImageNode, BoardNode, IframeNode,
        BitableNode, SheetNode, ReferenceBaseNode,
        SourceSyncedNode, ReferenceSyncedNode,
    ):
        assert cls in WRITE_HOSTILE_NODE_TYPES


def test_write_hostile_is_checked_after_uniqueness_not_before():
    # A hostile block among an ambiguous set does not get singled out — the result
    # is still ambiguous (we never pick one), proving the type check is post-unique.
    tree = _page(
        SourceSyncedNode(content=[Text("dup text")], block_id="s1"),
        _para("p1", "dup text"),
    )
    result = resolve(_req("dup text"), tree)
    assert result.reason is RefusalReason.AMBIGUOUS
    assert set(result.candidate_ids) == {"s1", "p1"}


# --------------------------------------------------------------------------- #
# AC7 — offline; works on the real parsed tree; reader output byte-identical    #
# --------------------------------------------------------------------------- #

def test_resolve_over_a_headless_document_root():
    # The entry-block-missing fallback (DocumentNode) is walked too.
    tree = DocumentNode(children=[_para("p1", "headless line")], block_id=None)
    assert resolve(_req("headless line"), tree).block_id == "p1"


def test_parse_docx_tree_accessor_matches_reader_output_byte_for_byte():
    # The non-rendering tree accessor returns the SAME tree the reader renders, so
    # exposing it changes NO reader Markdown output (goldens zero-drift, structurally).
    block_dicts = [
        {"block_id": "root", "parent_id": "", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Title"}}]},
         "children": ["h", "p"]},
        {"block_id": "h", "parent_id": "root", "block_type": 3,
         "heading1": {"elements": [{"text_run": {"content": "Section"}}]}},
        {"block_id": "p", "parent_id": "root", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "Body text here."}}]}},
    ]
    blocks = build_blocks(block_dicts)

    p1 = Parser(Config())
    tree = p1.parse_docx_tree("root", blocks)
    md_from_tree = p1.renderer.render(tree)

    p2 = Parser(Config())
    md_direct = p2.parse_docx_content("root", build_blocks(block_dicts))

    assert md_from_tree == md_direct
    assert isinstance(tree, PageNode)


def test_resolve_over_a_parser_built_tree_from_real_sdk_blocks():
    # End-to-end on real SDK Block objects: parse → tree → resolve to the block_id.
    block_dicts = [
        {"block_id": "root", "parent_id": "", "block_type": 1,
         "page": {"elements": [{"text_run": {"content": "Doc"}}]},
         "children": ["h", "p"]},
        {"block_id": "h", "parent_id": "root", "block_type": 3,
         "heading1": {"elements": [{"text_run": {"content": "Findings"}}]}},
        {"block_id": "p", "parent_id": "root", "block_type": 2,
         "text": {"elements": [{"text_run": {"content": "The uptime was 99.9 percent."}}]}},
    ]
    parser = Parser(Config())
    tree = parser.parse_docx_tree("root", build_blocks(block_dicts))
    result = resolve(_req("uptime was 99.9 percent", ("Findings",)), tree)
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "p"


# =========================================================================== #
# LD-075 — insert/delete resolution (W3-S2)                                    #
#                                                                             #
# An InsertRequest's reference anchor and a DeleteRequest's target anchor      #
# resolve through the SAME exactly-one-or-refuse narrative path (reused, not   #
# forked): unique → ResolvedTarget, ambiguous → AMBIGUOUS, not-found →         #
# NOT_FOUND, write-hostile reference/target → WRITE_HOSTILE. For an insert the #
# resolver additionally computes WHERE the new block(s) would land — the       #
# parent block_id + index derived from the resolved reference and the position #
# (before → the reference's index; after → index+1; append-into → last child   #
# of the reference) — and refuses `cannot-hold-children` when an append-into    #
# reference is a leaf that cannot parent children. Fully offline.              #
# =========================================================================== #


def _insert(quote, position, texts=("new para",), breadcrumb=()):
    return InsertRequest(
        reference=Anchor(quote=quote, breadcrumb=breadcrumb),
        position=position,
        content=[NewParagraph(text=t) for t in texts],
    )


def _delete(quote, breadcrumb=()):
    return DeleteRequest(target=Anchor(quote=quote, breadcrumb=breadcrumb))


# --------------------------------------------------------------------------- #
# AC1 — reference/target resolution reuses exactly-one-or-refuse                #
# --------------------------------------------------------------------------- #

def test_insert_reference_resolves_to_exactly_one_block():
    tree = _page(_para("p1", "The sky is blue."), _para("p2", "Grass is green."))
    result = resolve(_insert("The sky is blue.", InsertPosition.AFTER), tree)
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "p1"  # the resolved REFERENCE block


def test_delete_target_resolves_to_exactly_one_block():
    tree = _page(_para("p1", "keep me"), _para("p2", "remove me"))
    result = resolve(_delete("remove me"), tree)
    assert isinstance(result, ResolvedTarget)
    assert result.block_id == "p2"


def test_insert_reference_ambiguous_refuses_never_auto_picks():
    # Two blocks contain the reference quote, no breadcrumb to narrow → refuse.
    tree = _page(_para("p1", "same sentence"), _para("p2", "same sentence"))
    result = resolve(_insert("same sentence", InsertPosition.BEFORE), tree)
    assert not isinstance(result, ResolvedTarget)
    assert result.reason is RefusalReason.AMBIGUOUS
    assert set(result.candidate_ids) == {"p1", "p2"}


def test_delete_target_ambiguous_refuses():
    tree = _page(_para("p1", "dup"), _para("p2", "dup"), _para("p3", "dup"))
    result = resolve(_delete("dup"), tree)
    assert result.reason is RefusalReason.AMBIGUOUS
    assert result.candidate_count == 3


def test_insert_reference_not_found_refuses():
    tree = _page(_para("p1", "hello"))
    assert resolve(_insert("absent", InsertPosition.AFTER), tree).reason is RefusalReason.NOT_FOUND


def test_delete_target_not_found_refuses():
    tree = _page(_para("p1", "hello"))
    assert resolve(_delete("absent"), tree).reason is RefusalReason.NOT_FOUND


def test_insert_reference_breadcrumb_narrows_like_the_narrative_path():
    tree = _page(
        _heading("hA", "Alpha"),
        _para("pA", "shared"),
        _heading("hB", "Beta"),
        _para("pB", "shared"),
    )
    assert resolve(_insert("shared", InsertPosition.AFTER, breadcrumb=("Beta",)), tree).block_id == "pB"
    assert resolve(_delete("shared", breadcrumb=("Alpha",)), tree).block_id == "pA"


# --------------------------------------------------------------------------- #
# AC2 — write-hostile reference/target refuses (reuses _is_write_hostile)       #
# --------------------------------------------------------------------------- #

def test_insert_reference_write_hostile_synced_refuses():
    tree = _page(SourceSyncedNode(content=[Text("synced line")], block_id="sync"))
    result = resolve(_insert("synced line", InsertPosition.AFTER), tree)
    assert result.reason is RefusalReason.WRITE_HOSTILE


def test_insert_reference_write_hostile_image_refuses():
    tree = _page(ImageNode(caption="revenue chart", block_id="img"))
    result = resolve(_insert("revenue chart", InsertPosition.BEFORE), tree)
    assert result.reason is RefusalReason.WRITE_HOSTILE


def test_delete_target_write_hostile_synced_refuses():
    # You cannot delete a synced block through the gated pipeline.
    tree = _page(SourceSyncedNode(content=[Text("synced line")], block_id="sync"))
    result = resolve(_delete("synced line"), tree)
    assert result.reason is RefusalReason.WRITE_HOSTILE


def test_delete_target_write_hostile_embed_refuses():
    tree = _page(IframeNode(url="https://embed.example/x", block_id="frame"))
    result = resolve(_delete("embed.example/x"), tree)
    assert result.reason is RefusalReason.WRITE_HOSTILE


# --------------------------------------------------------------------------- #
# Insert insertion-point computation — parent block_id + index by position      #
# (feeds AC3's preview; verified at the resolver level here)                     #
# --------------------------------------------------------------------------- #

def test_insert_after_computes_parent_and_index_plus_one():
    tree = _page(_para("p0", "zero"), _para("p1", "one"), _para("p2", "two"))
    result = resolve(_insert("one", InsertPosition.AFTER), tree)
    assert isinstance(result.insertion, ResolvedInsertion)
    assert result.insertion.position == "after"
    assert result.insertion.parent_block_id == "root"   # the page owns p1
    assert result.insertion.index == 2                   # p1 is index 1 → after = 2


def test_insert_before_computes_parent_and_index():
    tree = _page(_para("p0", "zero"), _para("p1", "one"), _para("p2", "two"))
    result = resolve(_insert("one", InsertPosition.BEFORE), tree)
    assert result.insertion.position == "before"
    assert result.insertion.parent_block_id == "root"
    assert result.insertion.index == 1                   # p1's own index


def test_insert_after_a_reference_nested_inside_a_container():
    # The reference is a child OF a container (a callout). before/after resolve the
    # parent + index within that container's own child list — not the page root.
    callout = CalloutNode(
        children=[_para("c0", "first child"), _para("c1", "second child")],
        block_id="cal",
    )
    tree = _page(callout)
    result = resolve(_insert("first child", InsertPosition.AFTER), tree)
    assert result.insertion.parent_block_id == "cal"     # c0's parent is the callout
    assert result.insertion.index == 1                    # c0 index 0 → after = 1


def test_insert_append_into_a_true_container_reference():
    # A heading resolves as the reference and can hold children; append-into → its
    # last-child index (0 when it owns none — the common flat Feishu shape).
    tree = _page(_heading("h", "Section"), _para("p", "body"))
    result = resolve(_insert("Section", InsertPosition.APPEND_INTO), tree)
    assert isinstance(result, ResolvedTarget)
    assert result.insertion.position == "append-into"
    assert result.insertion.parent_block_id == "h"       # the heading itself is the parent
    assert result.insertion.index == 0                    # heading owns no flat children


def test_insert_append_into_leaf_refuses_cannot_hold_children():
    # A plain paragraph cannot parent children — append-into it refuses (the LD-074
    # cannot-hold-children reason, produced by S2 as the model prescribes).
    tree = _page(_para("p", "leaf paragraph"))
    result = resolve(_insert("leaf paragraph", InsertPosition.APPEND_INTO), tree)
    assert not isinstance(result, ResolvedTarget)
    assert result.reason is RefusalReason.CANNOT_HOLD_CHILDREN


def test_insert_write_hostile_beats_cannot_hold_children():
    # A write-hostile reference is refused for hostility FIRST, even under
    # append-into (the narrative resolution's hostile check precedes the leaf check).
    tree = _page(ImageNode(caption="a chart", block_id="img"))
    result = resolve(_insert("a chart", InsertPosition.APPEND_INTO), tree)
    assert result.reason is RefusalReason.WRITE_HOSTILE


def test_insert_before_the_document_root_reference_refuses():
    # The reference resolves to the page root itself (its title), which has no parent to
    # place a sibling beside → no valid insertion location → refuse.
    #
    # MIGRATION-ERA PIN UPDATED BY LD-131 (was `RefusalReason.NOT_FOUND`). Justification,
    # quoted from the dogfood report § F5: "`BEFORE` and `AFTER` return
    # `{"reason": "not-found"}` — with no `detail` field at all — while `APPEND_INTO` with
    # the *identical anchor* resolves to `block_id=DocComme…`. The anchor was found; the
    # truth is that the target is the document root, which has no siblings. A consumer
    # reads `not-found` and goes hunting for a better quote: the wrong repair." The old
    # assertion pinned that lie; the reason is now the position-capability mirror of
    # `cannot-hold-children`. Consumer-visible error-text change, consented in LD-131 AC5.
    tree = _page(_para("p", "body"))          # PageNode title is "Doc"
    result = resolve(_insert("Doc", InsertPosition.BEFORE), tree)
    assert not isinstance(result, ResolvedTarget)
    assert result.reason is RefusalReason.CANNOT_HOLD_SIBLINGS
    assert "root" in result.detail                 # names the resolved block
    assert "append-into" in result.detail          # names the repair that works
