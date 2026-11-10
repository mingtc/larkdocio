"""LD-506 — images that live INSIDE table cells must reach the Markdown projection.

**Why this module exists.** A consumer measured a real production document
holding **116** image blocks whose larkdocio projection showed **9**, and
reported the other 107 — all inside table cells — as dropped.
The suite could not have caught it either way: maintainer-measured 2026-08-18, of the six
fixtures carrying a ``"block_type": 27`` **none** also carried a
``"block_type": 32``. The corpus was blind to the reader's commonest real-world
image position.

**The expectation is DERIVED, never hand-typed.** Each case counts the
``block_type: 27`` blocks in its own committed input JSON and asserts the
projection carries that many image references — so the number cannot rot when a
fixture is edited.

**Fixture provenance (AC1) — TWO TIERS, and the primary one is a REAL PAYLOAD.**
The inputs are authored in ``tests/_make_fixtures.py`` (see its "in-cell images
(LD-506)" section, which carries the full statement).

* ``table_cell_image`` **IS a live capture, its structure verbatim** — the block list of a real
  docx document exactly as ``GET /open-apis/docx/v1/documents/{id}/blocks``
  returned it, in
  ``dev/ld506-in-cell-image/captures/002-in-cell-image-raw-payload.json``
  (``blocks_flat_route``). The document was created by
  ``dev/ld506-in-cell-image/probes/probe_ld506_live_capture.py`` on 2026-08-19 and
  one image was authored into one cell by the shipped ``put_image_in_document``:
  the ONE permanent media token LD-506 was authorised to mint. Real structure and
  real style sub-objects — do not tidy them; the ids and the token are the
  substitution map's placeholders and the three cell texts are neutral words.
* The other four are **derived by editing that captured JSON** (the route the
  issue's § Media budget requires, so no second upload is ever needed). They
  simplify away one real structural fact the capture taught us: **a real table
  cell always carries an auto-provisioned inner text block, and an authored image
  is appended AFTER it**, so the image cell's children are
  ``[<empty text>, <image>]`` rather than the image alone. Measured
  rendering-inert; stated here so nothing claims a shape the API does not emit.

The live capture **confirmed the offline finding on real bytes**: the projection
carried the in-cell image (``| <label> | ![](…) |``), and the reader's
``with_descendants=True`` route and the flat block-list route returned the **same
11 blocks** on that document. See ``dev/ld506-in-cell-image/findings.md`` § 1.

**What was measured (AC2), in one line each:** on the GFM pipe path an in-cell
image projects correctly in every shape tried (alone, beside text, two in a
cell, nested table, under a list item, inside a callout, ragged final row,
``header_row: False``); on the merged/HTML path it projects correctly from an
ANCHOR cell; and it was DROPPED from a grid position covered by a preceding
anchor's span — the single reproduction found. The full matrix is
``dev/ld506-in-cell-image/captures/001-offline-shape-matrix.json``.

**That drop is FIXED (LD-529).** The strict ``xfail`` LD-506 left as the pin is
gone, and its sibling drop-assertion is inverted; a covered position's content is
absorbed into its covering anchor's cell. See the section below and
``tests/test_merged_cell_absorption.py``. LD-506's referral also carried an
inherited claim that real merged tables *normally* leave covered cells empty —
nothing measured "normally", and it is not repeated here.
"""
import json
import re

import pytest

from harness import FIXTURES_DIR, build_blocks
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser

# Both spellings the projection can legitimately use for an image: the GFM
# `![alt](token)` of the pipe-table path and the `<img src="token">` of the
# merged-table HTML path (LD-144). Counting only the first is exactly the
# artefact this module has to be immune to.
_IMAGE_REF = re.compile(r'!\[[^\]]*\]\([^)]*\)|<img\s')


def _case(name):
    """Load a committed fixture input and return (block dicts, its 27-count)."""
    blocks = json.loads(
        (FIXTURES_DIR / f"{name}.input.json").read_text(encoding="utf-8"))
    return blocks, sum(1 for b in blocks if b["block_type"] == 27)


def _project(blocks):
    """Render through the REAL parser + renderer; return (markdown, parser).

    The document id is the FIRST block's own id — the page/root block — which is
    ``harness.render``'s own convention. It is deliberately not the literal
    ``"root"``: the primary fixture is a verbatim live capture whose root block id
    is the real document id (a docx document's root Page block id **is** its
    document id), so a hard-coded ``"root"`` would render nothing for it.
    """
    parser = Parser(Config())
    markdown = parser.parse_docx_content(blocks[0]["block_id"], build_blocks(blocks))
    return markdown, parser


def _image_refs(markdown):
    return _IMAGE_REF.findall(markdown)


# --- the four in-cell shapes that must project, each its own case -------------

@pytest.mark.parametrize("case", [
    "table_cell_image",                # a cell's auto-provisioned text block + the image, as captured
    "table_cell_image_beside_text",    # an image BESIDE text in one cell
    "table_cell_two_images",           # TWO images in one cell
    "merged_table_cell_image",         # a MERGED table's HTML path (anchor cell)
])
def test_the_projection_carries_every_in_cell_image(case):
    blocks, expected = _case(case)
    assert expected, f"{case} carries no block_type 27 — the fixture is wrong"
    markdown, _ = _project(blocks)
    assert len(_image_refs(markdown)) == expected, (
        f"{case}: the projection shows {len(_image_refs(markdown))} image(s) for "
        f"{expected} image block(s).\n{markdown}")


@pytest.mark.parametrize("case", [
    "table_cell_image",
    "table_cell_image_beside_text",
    "table_cell_two_images",
    "merged_table_cell_image",
])
def test_every_in_cell_image_token_is_queued_for_download(case):
    """The projection is only half the contract: the token must also reach the
    T1 download/substitution queue, or the link points at a file nobody fetched."""
    blocks, expected = _case(case)
    _, parser = _project(blocks)
    assert len(parser.img_tokens) == expected


@pytest.mark.parametrize("case", [
    "table_cell_image",
    "table_cell_image_beside_text",
    "table_cell_two_images",
    "merged_table_cell_image",
])
def test_each_queued_token_appears_in_the_projection(case):
    """Every queued token is actually linked — a token queued with no reference
    is a downloaded file nothing points at (the covered-cell signature below)."""
    blocks, _ = _case(case)
    markdown, parser = _project(blocks)
    for token in parser.img_tokens:
        assert token in markdown, f"{case}: queued token {token} is not in the output"


def test_the_merged_table_path_keeps_the_token_in_the_img_src():
    """The HTML path must preserve the raw token as `src` so the T1 relink still
    rewrites it — a merged table emitting `<img>` rather than `![](…)` is the
    counting artefact a consumer's `!\\[` grep would read as a drop."""
    blocks, _ = _case("merged_table_cell_image")
    markdown, parser = _project(blocks)
    assert "<img " in markdown and "![](" not in markdown
    assert f'<img src="{parser.img_tokens[0]}"' in markdown


# --- the ONE measured drop, FIXED under LD-529 and pinned as the contract ----
#
# LD-506 measured this drop and did not fix it: an image at a grid position
# covered by a preceding anchor's merge span was discarded by _table_html's
# computed-occupancy rule (LD-050) while its token stayed queued on
# parser.img_tokens — a downloaded file linked nowhere. LD-506 left the correct
# expectation as a STRICT xfail (the fix moves the pre-existing
# merged_table_gauntlet golden and supersedes part of LD-050, both maintainer calls) so
# that a future fix would redden the suite. LD-529 took the fix, on the maintainer ruling
# that a covered position's content is absorbed into its covering anchor's cell.
# The xfail is therefore GONE, not weakened: the test below is plain and passing.


def test_a_covered_cells_image_should_reach_the_projection():
    blocks, expected = _case("merged_table_covered_cell_image")
    markdown, _ = _project(blocks)
    assert len(_image_refs(markdown)) == expected


def test_the_covered_cells_image_is_queued_but_never_linked():
    """The queue↔projection contract at the position that used to break it.

    **What this test asserted before LD-529, and why it is inverted.** It was the
    drop's positive pin: the token IS queued (so the download leg fetched the
    bytes) and the projection referenced it NOWHERE — asserted positively so the
    defect could not vanish unnoticed while nobody was looking. LD-529 overtook
    exactly that drop: a covered position's content is now absorbed into the cell
    of the anchor whose span claims it, so the token is queued **and** linked.

    Kept in place, same shape, inverted conclusion — because the failure mode it
    guards is still live in the other direction: a queued token with no reference
    is a downloaded file nothing points at, and this is the one shape in the
    corpus where the renderer has to work for the reference to exist. The name is
    unchanged deliberately: a renamed test is a removed node id.
    """
    blocks, expected = _case("merged_table_covered_cell_image")
    markdown, parser = _project(blocks)
    assert len(parser.img_tokens) == expected == 1
    assert parser.img_tokens[0] in markdown
    assert len(_image_refs(markdown)) == 1


# --- AC4: queue <-> projection, as a CORPUS-WIDE invariant -------------------

_ALL_FIXTURES = sorted(FIXTURES_DIR.glob("*.input.json"))


@pytest.mark.parametrize(
    "input_path", _ALL_FIXTURES,
    ids=[p.name[: -len(".input.json")] for p in _ALL_FIXTURES])
def test_no_fixture_queues_a_token_the_projection_does_not_link(input_path):
    """Every token on ``parser.img_tokens``, over EVERY committed fixture, appears
    in the rendered Markdown.

    The two halves are one contract: the T1 download leg fetches what the parser
    queued, and a queued token with no reference in the output is a file
    downloaded into ``static/`` that nothing points at. LD-506 asserted this for
    the four shapes that worked; LD-529 makes it a sweep over the whole corpus, so
    a NEW orphan path cannot be introduced by a renderer branch nobody thought to
    re-check.

    **Exceptions: none.** Every fixture is in the sweep — measured 2026-08-20, all
    87 pass. The two other position-based content drops the renderer still has
    (both censused under LD-529 AC4) cannot orphan a token here:

    * ``_html_image``'s ``caption is None`` early return renders nothing — but a
      caption-``None`` ``ImageNode`` is only ever constructed when the image
      payload is absent entirely (``blocks/media.py``), and that path queues no
      token. So it is unreachable as an orphan, by construction, not by luck.
    * a **span-0 cell at an UNCOVERED position** is skipped by ``_table_html``
      while no anchor claims it, so its subtree — an image included — is dropped
      and a queued token would orphan. Behaviour deliberately UNCHANGED by LD-529
      (LD-050's belt-and-braces reason is preserved: a synthetic payload may mark
      a covered cell ``0``), never observed in a real payload, and disclosed in
      ``BLOCKS.md`` row 31 and the release notes rather than quietly fixed. No
      committed fixture holds that shape; if one is ever added with an image in
      it, this sweep is where it will redden — and that is the correct place to
      have the conversation, not a silent exclusion here.
    """
    blocks = json.loads(input_path.read_text(encoding="utf-8"))
    markdown, parser = _project(blocks)
    for token in parser.img_tokens:
        assert token in markdown, (
            f"{input_path.name}: queued token {token} is linked nowhere in the "
            f"projection — a downloaded file nothing points at.\n{markdown}")


# --- the corpus blind spot itself, guarded so it cannot re-open ---------------

def test_the_corpus_carries_the_in_cell_image_shape():
    """maintainer-measured at mint: NO committed fixture carried both a 27 and a 32.
    This guard keeps at least one, so the shape can never go unpinned again."""
    both = []
    for path in sorted(FIXTURES_DIR.glob("*.input.json")):
        types = {b["block_type"] for b in json.loads(
            path.read_text(encoding="utf-8"))}
        if {27, 32} <= types:
            both.append(path.name)
    assert both, (
        "No fixture carries an image (27) inside a table cell (32) — the blind "
        "spot LD-506 was filed for has re-opened.")
