"""A test-only reference HTML parse, for asserting emitted markup is well-formed.

LD-144 AC6: the merged-table ``<td>`` path now emits REAL HTML (``<strong>``,
``<ul>``/``<li>``, ``<hr/>``, ``<p>``), so a string-compare is no longer a
sufficient check — an unbalanced or mis-nested tag would still "contain
``<strong>``". This module gives the suite a **structural** assertion instead,
built on the stdlib :mod:`html.parser` (the house rule is git + bash + python
only — no new tooling dependency, and markdown-it-py is a *Markdown* parser that
passes an HTML block through raw, so it cannot validate one).

Two checks, deliberately separate:

* :func:`tag_balance_errors` — every start tag is closed, in order, by its own
  end tag (void elements never being closed). This is the "no unbalanced tags"
  half of AC6.
* :func:`block_content_violations` — the "no stray text nodes where block
  content was expected" half: an element that has a **block-level** direct child
  may not also carry bare non-whitespace text directly, because that text is
  outside every block and renders in an undefined position.

Both return a list of human-readable problems (empty == clean) rather than
asserting, so a test can name what went wrong AND a red-then-green check can
prove the guard actually bites.
"""
from html.parser import HTMLParser

#: HTML void elements — they are never closed, so they never enter the stack.
VOID = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})

#: Elements that are block-level in the sense AC6 cares about: if one of these is
#: a direct child, bare sibling text is "stray text where block content was
#: expected".
BLOCK_LEVEL = frozenset({
    "p", "ul", "ol", "hr", "div", "table", "blockquote", "pre",
    "h1", "h2", "h3", "h4", "h5", "h6",
})

#: Containers that legitimately mix their OWN phrasing text with a block child, so
#: the stray-text rule does not apply to them. A list item is the case that
#: matters here: HTML nests a sub-list INSIDE the parent ``<li>``, right beside
#: that item's own text (``<li>outer<ul><li>inner</li></ul></li>``).
MIXED_CONTENT_OK = frozenset({"li"})


class _Checker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []
        # Per open element: (tag, [direct child tags], [direct text chunks]).
        self.frames = [("<root>", [], [])]

    # -- balance ----------------------------------------------------------- #

    def handle_starttag(self, tag, attrs):
        self.frames[-1][1].append(tag)
        if tag in VOID:
            return
        self.stack.append(tag)
        self.frames.append((tag, [], []))

    def handle_startendtag(self, tag, attrs):
        # `<hr/>` / `<br/>` — self-closing, so only a child record.
        self.frames[-1][1].append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            self.errors.append(f"void element </{tag}> was explicitly closed")
            return
        if not self.stack:
            self.errors.append(f"</{tag}> with no open tag")
            return
        if self.stack[-1] != tag:
            self.errors.append(
                f"</{tag}> closes <{self.stack[-1]}> (mis-nested; stack {self.stack})"
            )
            return
        self.stack.pop()
        self.frames.pop()

    def handle_data(self, data):
        self.frames[-1][2].append(data)

    def close(self):
        super().close()
        if self.stack:
            self.errors.append(f"unclosed tags at end of input: {self.stack}")


def _walk_frames(markup):
    """Re-parse ``markup`` collecting, per element, its direct children + text.

    A second, simpler pass than :class:`_Checker`'s balance bookkeeping so a
    mis-nesting error is reported once (by the balance check) rather than twice.
    """
    frames = []          # completed (tag, child_tags, text_chunks)
    open_frames = [["<root>", [], []]]

    class _Collector(HTMLParser):
        def handle_starttag(self, tag, attrs):
            open_frames[-1][1].append(tag)
            if tag not in VOID:
                open_frames.append([tag, [], []])

        def handle_startendtag(self, tag, attrs):
            open_frames[-1][1].append(tag)

        def handle_endtag(self, tag):
            if tag in VOID or len(open_frames) == 1:
                return
            if open_frames[-1][0] != tag:
                return
            frames.append(tuple(open_frames.pop()))

        def handle_data(self, data):
            open_frames[-1][2].append(data)

    p = _Collector(convert_charrefs=True)
    p.feed(markup)
    p.close()
    frames.extend(tuple(f) for f in open_frames)
    return frames


def tag_balance_errors(markup: str) -> list:
    """Every balance/nesting problem in ``markup`` (empty list == well-formed)."""
    c = _Checker()
    c.feed(markup)
    c.close()
    return c.errors


def block_content_violations(markup: str) -> list:
    """Elements carrying a block-level child AND bare non-whitespace text."""
    out = []
    for tag, children, texts in _walk_frames(markup):
        if tag in MIXED_CONTENT_OK:
            continue
        if not any(ch in BLOCK_LEVEL for ch in children):
            continue
        stray = [t for t in texts if t.strip()]
        if stray:
            out.append(
                f"<{tag}> mixes block children {sorted(set(children) & BLOCK_LEVEL)} "
                f"with stray text {stray!r}"
            )
    return out


def assert_wellformed(markup: str):
    """Raise ``AssertionError`` unless ``markup`` is balanced AND block-clean."""
    balance = tag_balance_errors(markup)
    assert not balance, f"markup is not well-formed: {balance}\n---\n{markup}"
    stray = block_content_violations(markup)
    assert not stray, f"stray text where block content expected: {stray}\n---\n{markup}"
