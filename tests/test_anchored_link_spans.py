"""LD-434 — the ANCHORED INLINE LINK rung: a created run may carry a link URL.

*"For the full details, **open the attached file**"* — a sentence whose anchor text is **not**
the URL. Lark stores a created ``text_run``'s ``text_element_style.link.url`` and reads it
back verbatim (``dev/media-spike/captures/541-``, ``542-``, in the dev repo); this library
refused to author one. These tests pin the typed shape that opens it.

Conformance-tier: the encoding, the URL-spelling pin and the reader round trip are **measured
external truth / product contract**, not this module's internal choices
(``process/doctrine/conformance-tier.md`` § A.4).
"""
import pytest

from larkdocio.blocks.text import _text_run_node
from larkdocio.model.renderer import MarkdownRenderer
from larkdocio.write.encode import encode_block
from larkdocio.write.model import NewBlock, NewBlockKind, TextSpan

pytestmark = pytest.mark.conformance


ANCHOR = "open the attached file"
URL = "https://your-domain.larksuite.com/file/Example168cd88b654f181f3582"


def sentence() -> NewBlock:
    """The maintainer's own sentence, as the typed shape authors it."""
    return NewBlock.rich_paragraph((
        TextSpan("For the full details, "),
        TextSpan(ANCHOR, link_url=URL),
    ))


# --------------------------------------------------------------------------- #
# The typed shape.                                                             #
# --------------------------------------------------------------------------- #

def test_a_span_carries_anchor_text_and_an_optional_link():
    span = TextSpan(ANCHOR, link_url=URL)
    assert span.text == ANCHOR
    assert span.link_url == URL
    assert TextSpan("plain").link_url is None


def test_a_rich_block_derives_its_plain_text_from_its_spans():
    block = sentence()
    assert block.kind is NewBlockKind.PARAGRAPH
    assert block.text == "For the full details, open the attached file"


def test_an_empty_span_is_refused_at_construction():
    with pytest.raises(ValueError, match="empty"):
        TextSpan("", link_url=URL)


def test_a_rich_block_with_no_spans_is_refused():
    with pytest.raises(ValueError, match="at least one span"):
        NewBlock.rich_paragraph(())


def test_spans_and_a_disagreeing_text_are_refused_rather_than_reconciled():
    with pytest.raises(ValueError, match="disagree"):
        NewBlock(kind=NewBlockKind.PARAGRAPH, text="something else",
                 spans=(TextSpan("a"), TextSpan("b")))


@pytest.mark.parametrize("kind,extra", [
    (NewBlockKind.CODE, {}),
    (NewBlockKind.MERMAID, {}),
])
def test_spans_are_refused_on_the_kinds_whose_projection_cannot_carry_a_link(kind, extra):
    with pytest.raises(ValueError, match="spans"):
        NewBlock(kind=kind, spans=(TextSpan("x", link_url=URL),), **extra)


def test_a_table_BLOCK_refuses_spans_and_names_the_CELL_as_where_the_anchor_goes():
    """TRANSFORMED, never deleted (LD-619 / D-110), and this is what it now pins.

    **The REASON is the original and is unchanged:** a table's content lives in ``rows``, so
    a span sequence hung on the table **block** addresses no cell — and what the refusal
    protects is what it always protected, that this library does not silently emit content
    which lands nowhere.

    **Only the CONCLUSION moved.** This test used to be named *"a table still refuses spans
    because its content lives in rows"* and it was read as the whole answer to *can a table
    carry an anchored link* — an answer that rested on a **data-shape description offered
    where a measurement was missing**. The measurement now exists: Lark accepts and **stores**
    a link-carrying run inside a docx table cell, on both write routes, read back fresh
    (LD-517, ``dev/ld517-in-cell-link/findings.md``). So the block-level refusal survives with
    its reason, and it now has to **name the route that works** — the cell itself — because a
    refusal that hides a shipped capability is the same defect as one that invents a limit.
    """
    with pytest.raises(ValueError) as exc:
        NewBlock(kind=NewBlockKind.TABLE, rows=(("a",),),
                 spans=(TextSpan("x", link_url=URL),))
    message = str(exc.value)
    assert "spans" in message
    assert "content lives in rows" in message          # the reason, verbatim
    assert "rows=" in message and "TextSpan" in message  # the conclusion that moved


def test_a_table_CELL_may_carry_the_anchor_which_is_where_the_capability_landed():
    """The other half of the same boundary — the new truth, beside the preserved reason."""
    table = NewBlock.table([["Example Item", (TextSpan(ANCHOR, link_url=URL),)]])
    assert table.rows[0][1] == (TextSpan(ANCHOR, link_url=URL),)
    assert table.text == ""      # a table's plain text still lives nowhere but its rows


def test_a_heading_and_a_list_item_may_carry_an_anchor():
    heading = NewBlock(kind=NewBlockKind.HEADING, level=2,
                       spans=(TextSpan("See ", ), TextSpan("the file", link_url=URL)))
    assert heading.text == "See the file"
    bullet = NewBlock(kind=NewBlockKind.BULLET,
                      spans=(TextSpan("the file", link_url=URL),))
    assert bullet.text == "the file"


# --------------------------------------------------------------------------- #
# The URL SPELLING PIN (AC7) — verbatim, and it is not a guess.                #
# --------------------------------------------------------------------------- #

def test_the_url_is_encoded_VERBATIM_the_shape_lark_stored(capsys):
    payload = encode_block(sentence())
    elements = payload["text"]["elements"]
    assert elements == [
        {"text_run": {"content": "For the full details, "}},
        {"text_run": {"content": ANCHOR,
                      "text_element_style": {"link": {"url": URL}}}},
    ]


def test_a_percent_encoded_spelling_is_REFUSED_because_it_does_not_round_trip():
    encoded = "https%3A%2F%2Fexample.com%2Ffile%2Fx"
    with pytest.raises(ValueError) as exc:
        TextSpan(ANCHOR, link_url=encoded)
    message = str(exc.value)
    assert "percent" in message.lower()
    # the REASON survives: Lark accepted both spellings; it is the reader that decodes.
    assert "unescape_url" in message or "decode" in message.lower()


def test_a_url_carrying_whitespace_is_refused():
    with pytest.raises(ValueError, match="whitespace"):
        TextSpan(ANCHOR, link_url="https://example.com/a b")


def test_an_empty_link_url_is_refused_rather_than_authored_as_a_dead_anchor():
    with pytest.raises(ValueError, match="empty"):
        TextSpan(ANCHOR, link_url="")


# --------------------------------------------------------------------------- #
# The ROUND TRIP against the reader's OWN dialect.                             #
# --------------------------------------------------------------------------- #

class _Style:
    """The shape the pinned SDK deserializes a read ``text_element_style`` into."""

    def __init__(self, url):
        self.bold = self.italic = self.strikethrough = False
        self.underline = self.inline_code = False
        self.link = type("_Link", (), {"url": url})()
        self.text_color = self.background_color = self.comment_ids = None


class _Run:
    def __init__(self, content, url=None):
        self.content = content
        self.text_element_style = _Style(url) if url else None


def test_the_reader_renders_an_authored_anchor_back_as_the_anchor_and_its_url():
    """encode → (what Lark stores, per capture 541-/542-) → the reader's own Markdown."""
    payload = encode_block(sentence())
    nodes = []
    for element in payload["text"]["elements"]:
        run = element["text_run"]
        url = ((run.get("text_element_style") or {}).get("link") or {}).get("url")
        nodes.append(_text_run_node(None, _Run(run["content"], url)))
    rendered = MarkdownRenderer().render_inline(nodes, block_context=True)
    assert rendered == f"For the full details, [{ANCHOR}]({URL})"
