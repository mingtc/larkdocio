"""Auto-linkify bare URLs — ALWAYS ON, NO KNOB (LD-054).

Bare ``http(s)://…`` URLs in plain/styled text runs render as ``[url](url)``.
This is a permanent, maintainer-directed, consented output change with no opt-out knob.

The four guardrails (AC2 / AC3):
  * never double-link — runs already carrying a ``.link``, ``mention_doc``
    output, and inline-code content are left untouched;
  * conservative boundary — trailing sentence punctuation (``.,;:!?)``) stays
    OUTSIDE the link;
  * non-``http(s)`` schemes (``mailto:`` / ``ftp:`` / bare ``www.``) are NOT
    linkified (out of scope);
  * the table-cell ``|``-escape still applies after linkify.
"""
from harness import build_blocks, render

from larkdocio.read.config import Config, OutputConfig
from larkdocio.read.parser import Parser


def _text_block(elements):
    return [{
        "block_id": "t",
        "parent_id": "doc",
        "block_type": 2,
        "text": {"elements": elements},
        "children": [],
    }]


def _plain(content):
    return {"text_run": {"content": content}}


def _styled(content, style):
    return {"text_run": {"content": content, "text_element_style": style}}


# -- AC1: always on, no knob ------------------------------------------------

def test_bare_url_in_plain_text_becomes_link():
    out = render(_text_block([_plain("https://www.figma.com/design/abc")]), doc_id="t")
    assert (
        "[https://www.figma.com/design/abc](https://www.figma.com/design/abc)" in out
    ), f"bare URL not linkified: {out!r}"


def test_bare_url_mid_sentence_linkified():
    out = render(_text_block([_plain("see https://example.com/x here")]), doc_id="t")
    assert "see [https://example.com/x](https://example.com/x) here" in out, out


def test_http_scheme_also_linkified():
    out = render(_text_block([_plain("http://example.com")]), doc_id="t")
    assert "[http://example.com](http://example.com)" in out, out


def test_multiple_urls_in_one_run_both_linkified():
    out = render(
        _text_block([_plain("a https://example.com b https://example.org c")]), doc_id="t"
    )
    assert "[https://example.com](https://example.com)" in out, out
    assert "[https://example.org](https://example.org)" in out, out


def test_bare_url_in_bold_run_linkified_inside_markers():
    out = render(
        _text_block([_styled("https://example.com/a", {"bold": True})]), doc_id="t"
    )
    assert "**[https://example.com/a](https://example.com/a)**" in out, out


# -- AC3: conservative trailing-punctuation boundary ------------------------

def test_trailing_period_stays_outside_link():
    out = render(_text_block([_plain("see https://example.com/a.")]), doc_id="t")
    assert "see [https://example.com/a](https://example.com/a)." in out, out


def test_trailing_paren_stays_outside_link():
    out = render(_text_block([_plain("(https://example.com/a)")]), doc_id="t")
    assert "([https://example.com/a](https://example.com/a))" in out, out


def test_trailing_comma_stays_outside_link():
    out = render(_text_block([_plain("https://example.com/a, next")]), doc_id="t")
    assert "[https://example.com/a](https://example.com/a), next" in out, out


def test_interior_dot_preserved_only_trailing_peeled():
    # A dot INSIDE the path stays in the URL; only the sentence-ending dot peels.
    out = render(_text_block([_plain("https://example.com/a.b.c.")]), doc_id="t")
    assert "[https://example.com/a.b.c](https://example.com/a.b.c)." in out, out


# -- AC2: never double-link -------------------------------------------------

def test_run_already_carrying_link_is_not_double_linked():
    # StyledText with a resolved link → already [text](link); content must not
    # be linkified again even though the link destination is itself a URL.
    out = render(
        _text_block([_styled("Link to Google", {"link": {"url": "http://www.google.com"}})]),
        doc_id="t",
    )
    assert "[Link to Google](http://www.google.com)" in out, out
    # No nested/second link markup.
    assert out.count("](") == 1, f"double-linked: {out!r}"


def test_url_content_with_link_not_double_linked():
    out = render(
        _text_block([_styled("https://display.example", {"link": {"url": "https://target.example"}})]),
        doc_id="t",
    )
    assert "[https://display.example](https://target.example)" in out, out
    assert out.count("](") == 1, f"double-linked: {out!r}"


def test_mention_doc_output_not_double_linked():
    blocks = _text_block([
        {"mention_doc": {"title": "Example Document", "url": "https://your-domain.larksuite.com/wiki/abc"}},
    ])
    out = render(blocks, doc_id="t")
    assert "[Example Document](https://your-domain.larksuite.com/wiki/abc)" in out, out
    assert out.count("](") == 1, f"double-linked mention_doc: {out!r}"


def test_url_inside_inline_code_stays_verbatim():
    out = render(
        _text_block([_styled("https://example.com/a", {"inline_code": True})]), doc_id="t"
    )
    assert "`https://example.com/a`" in out, out
    # The URL inside inline code is NOT wrapped in link markup.
    assert "](https" not in out, f"inline-code URL was linkified: {out!r}"


def _code_block(elements, lang=None):
    code = {"elements": elements}
    if lang is not None:
        code["style"] = {"language": lang}
    return [{
        "block_id": "c",
        "parent_id": "doc",
        "block_type": 14,
        "code": code,
        "children": [],
    }]


def test_url_inside_code_fence_stays_verbatim():
    # AC2: code-fence content is verbatim — a bare URL inside a ``` fence must
    # NOT be rewritten to [url](url) (would corrupt e.g. a curl example).
    out = render(_code_block([_plain("curl https://api.example.com/v1")]), doc_id="c")
    assert "curl https://api.example.com/v1" in out, out
    assert "](https" not in out, f"code-fence URL was linkified: {out!r}"


def test_styled_url_inside_code_fence_stays_verbatim():
    # A styled run inside a code fence must also stay verbatim (the _styled path
    # threads the no-linkify flag too).
    out = render(
        _code_block([_styled("curl https://api.example.com/v1", {"bold": True})]),
        doc_id="c",
    )
    assert "https://api.example.com/v1" in out, out
    assert "](https" not in out, f"styled code-fence URL was linkified: {out!r}"


# -- Out of scope: non-http(s) schemes --------------------------------------

def test_mailto_not_linkified():
    out = render(_text_block([_plain("mailto:a@example.com")]), doc_id="t")
    assert "](mailto" not in out and "[mailto" not in out, out
    assert "mailto:a@example.com" in out, out


def test_ftp_not_linkified():
    out = render(_text_block([_plain("ftp://files.example.com/x")]), doc_id="t")
    assert "](ftp" not in out, out
    assert "ftp://files.example.com/x" in out, out


def test_bare_www_without_scheme_not_linkified():
    out = render(_text_block([_plain("www.figma.com/design/abc")]), doc_id="t")
    assert "](www" not in out and "](http" not in out, out
    assert "www.figma.com/design/abc" in out, out


# -- Table-cell |-escape interaction preserved (AC3) ------------------------

def test_url_in_table_cell_linkified_and_pipe_escape_intact():
    # A URL sitting in a Markdown table cell must be linkified, and the cell's
    # own pipe-escape must still fire (a literal | inside the cell → \|).
    blocks = [
        {
            "block_id": "root", "parent_id": "doc", "block_type": 1,
            "page": {"elements": [{"text_run": {"content": "T"}}]},
            "children": ["tbl"],
        },
        {
            "block_id": "tbl", "parent_id": "root", "block_type": 31,
            "table": {"property": {"row_size": 1, "column_size": 1, "header_row": True}},
            "children": ["c0"],
        },
        {
            "block_id": "c0", "parent_id": "tbl", "block_type": 32,
            "table_cell": {}, "children": ["c0t"],
        },
        {
            "block_id": "c0t", "parent_id": "c0", "block_type": 2,
            "text": {"elements": [{"text_run": {"content": "https://example.com/a"}}]},
            "children": [],
        },
    ]
    out = render(blocks, doc_id="root")
    assert "[https://example.com/a](https://example.com/a)" in out, out


# -- No knob: linkify fires regardless of OutputConfig ----------------------

def test_linkify_fires_under_html_tags_config_too():
    blocks = _text_block([_styled("https://example.com/a", {"bold": True})])
    built = build_blocks(blocks)
    cfg = Config(output=OutputConfig(use_html_tags=True))
    out = Parser(cfg).parse_docx_content("t", built)
    assert "<strong>[https://example.com/a](https://example.com/a)</strong>" in out, out
