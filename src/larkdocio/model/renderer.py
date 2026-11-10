"""The Markdown renderer over the typed model (LD-024).

ONE renderer serializes a node per its type — the inverse of the registry
division: handlers construct nodes, this renderer emits Markdown. It imports the
node types (one-way dependency); the nodes never import the renderer.

**Two escaping layers, and they are NOT the same thing.**

1. **Structural-ambiguity escaping — ALWAYS ON (LD-130, maintainer-consented output
   change).** Literal text may never masquerade as *structure*. A plain paragraph
   whose text is ``# Fake H1`` used to emit output byte-indistinguishable from a
   real heading, so a consumer re-parsing our Markdown computed a heading path —
   ``Anchor.breadcrumb`` is a heading path — from phantom headings that are not in
   the real tree (dogfood F1). This layer escapes exactly the ambiguity: the
   **line-leading block markers** at a block-content line start, and the
   **inline emphasis/code delimiter runs** that could pair up inside one literal
   run. An unambiguous metachar (``Issue #5``, ``2 * 3``, ``snake_case``) is left
   alone; every marker the renderer itself emits is STRUCTURE and is never
   escaped. See :func:`_escape_structural`.
2. **Escape-literals policy (Decision Log #3) — DEFAULT OFF.** The wider,
   opt-in sledgehammer: every CommonMark punctuation character in a literal span
   is backslash-escaped (``_ESCAPABLE``). The default read pipeline never flips it
   on; when it IS on it supersedes layer 1 (it already escapes a superset). Because
   it is total it is also **exactly invertible**, and its inverse
   (:func:`unescape_literals`) is defined right beside it — anything comparing
   escaped output against source text has to compare in the decoded domain, or an
   editor who merely normalized ``99\\.9`` back to ``99.9`` reads as having rewritten
   a paragraph nobody touched.

**The block-identity marker projection — DEFAULT OFF.** A third rendering policy
(``emit_block_ids``) prefixes each block-level node's serialization with a single-line
``<!-- lark:block:<id> -->`` marker, keyed on the identifier the model already carries,
and records the identifiers it emitted in document order. It is strictly ADDITIVE:
removing the marker lines returns the renderer's own output for the same escaping
policy, byte for byte. It pairs with the escape-literals policy above for a reason —
with literals escaped, a document whose own prose is marker-shaped cannot emit
something indistinguishable from a real marker.

Verbatim content — code fences, inline-code spans, ``RawInline``/``RawBlock``
markup, and merged-table HTML cells — is NEVER touched by layer 1: escaping
there would surface a literal backslash to the reader (an HTML ``<td>`` is not
markdown-parsed at all).

**A merged table's cells are serialized to HTML, not Markdown (LD-144).** Because
an HTML ``<td>`` is not markdown-parsed, Markdown *structure* is as inert there as
a backslash escape: emphasis markers, list markers and a ``---`` divider all
arrived at the reader as literal characters, and the underline wrapper the
renderer emits was escaped into a visible ``&lt;u&gt;``. So the HTML-table branch
has its **own** cell serializer (:meth:`MarkdownRenderer._html_cell_content`,
joined per merged span by :meth:`MarkdownRenderer._html_merged_cell`) that walks
the cell's child NODES and emits real tags. Escaping there is HTML-entity
escaping of TEXT only — never a backslash (LD-130's pin still holds), and colour
stays dropped (LD-042's settled capture-only doctrine).
"""
import re
from typing import List, NamedTuple, Optional, Tuple

from larkdocio.errors import LarkEscapeError

from .conservation import opaque_kind as _opaque_kind

from .nodes import (
    AddOnsNode,
    AgendaItemContentNode,
    AgendaItemNode,
    AgendaItemTitleNode,
    AgendaNode,
    BitableNode,
    BoardNode,
    BulletListItemNode,
    CalloutNode,
    CodeNode,
    DividerNode,
    DocumentNode,
    EquationBlockNode,
    FileNode,
    GridColumnNode,
    GridNode,
    HeadingNode,
    IframeNode,
    ImageNode,
    Inline,
    InlineEquation,
    MentionDoc,
    MentionUser,
    Node,
    OrderedListItemNode,
    PageNode,
    QuoteContainerNode,
    QuoteNode,
    RawBlock,
    RawInline,
    ReferenceBaseNode,
    ReferenceSyncedNode,
    SheetNode,
    SourceSyncedNode,
    StyledText,
    TableCellNode,
    TableNode,
    Text,
    TextNode,
    TodoListItemNode,
    UnknownBlockNode,
    UnsupportedInline,
    ViewNode,
)
from .table_occupancy import fold_rows, merge_span, occupancy

# --------------------------------------------------------------------------- #
# LD-145 — the heading-level ceiling shared by BOTH serializers                #
# --------------------------------------------------------------------------- #
#
# Lark stores heading levels 1-9; every dialect this renderer emits stops at 6
# (CommonMark's ATX marker is 1-6; HTML has <h1>..<h6> and no <h7>). The tree is
# the only place the TRUE level lives -- ``HeadingNode.level`` is never clamped,
# so a tree consumer still sees 7/8/9.
#
# Both serializers key off this one constant, and neither ever invents a marker
# outside its dialect (no ``#######``, no ``<h7>``). What they DO above the
# ceiling differs on purpose:
#
#   * MARKDOWN (:meth:`MarkdownRenderer._heading`) CAPS to ``######``. Markdown's
#     whole heading vocabulary is the ``#`` marker, so the only alternatives are
#     "a heading at the wrong level" or "not a heading at all" -- and 7 ``#`` was
#     the latter (CommonMark reads it as a paragraph of literal ``#``, which is
#     how the emission also broke the ``compose()`` round-trip: dogfood round-2
#     T17). A heading's structural role -- outline entry, TOC, anchor -- survives
#     a capped level and is destroyed by a paragraph, so the LEVEL gives way and
#     the loss is recorded in the dialect lossiness table (H7-9 read back as H6).
#   * MERGED-CELL HTML (:meth:`_HtmlCellRenderer._html_heading`, LD-144) degrades
#     to ``<p><strong>...</strong></p>`` instead. That heading sits inside a
#     ``<td>``, where it is no consumer's outline entry -- there is no structural
#     role left to save, so emitting ``<h6>`` would buy nothing and assert a level
#     the tree does not have. With only visual weight to preserve, it refuses to
#     misstate the level.
#
# The divergence is deliberate and tested as a PAIR (tests/test_heading_level_cap.py
# § "The cross-seam pair"), so a future change to either seam has to face the other.
MAX_HEADING_LEVEL = 6

# CommonMark ASCII punctuation that carries markdown meaning. Backslash is first
# so a literal backslash is escaped before the backslashes this routine inserts
# (never double-escaping an inserted one).
_ESCAPABLE = "\\`*_{}[]()#+-.!|>~<"

# --------------------------------------------------------------------------- #
# LD-130 — structural-ambiguity escaping of PLAIN text (ALWAYS ON)             #
# --------------------------------------------------------------------------- #
#
# The rule, stated once: a literal run of text must never PARSE as structure,
# and nothing else may change. Two disjoint classes:
#
#   (a) LINE-LEADING BLOCK MARKERS — only live at a block-content line start,
#       so they are escaped only there (:data:`_LINE_LEADING_RE`). A metachar
#       mid-line (``Issue #5``, ``costs 5 - 10``) cannot start a block and is
#       left alone.
#   (b) INLINE DELIMITER RUNS (``*`` ``_`` `` ` `` ``~``) — live anywhere, but
#       only in PAIRS: one lone ``*`` cannot emphasize anything. So a run is
#       escaped only when the same literal run carries a second candidate run
#       it could pair with (:func:`_emphasis_chars_to_escape`), which is what
#       keeps ``2 * 3 = 6`` and ``snake_case`` byte-unchanged.
#
# Escaping is by backslash, which CommonMark honors only before ASCII
# punctuation — that is why an ordered-list marker escapes its DELIMITER
# (``1\.``) and never the digit (``\1`` would emit a literal backslash).

#: Inline delimiter characters that can open/close emphasis, a code span or a
#: GFM strikethrough. ``~`` is included because the renderer emits ``~~`` for a
#: real strikethrough run, so literal ``~~`` in text is the same phantom class.
_EMPHASIS_CHARS = ("*", "_", "`", "~")

#: Everything that can START a block-level construct on a line of its own.
#: Anchored at the line start with CommonMark's 0-3 spaces of allowed indent (a
#: 4-space indent is an indented code block — out of LD-130's scope, see the
#: module's Known-limitations note in the issue).
#:
#: * ``atx``    — ``#``..``######`` + space/tab/EOL  → a heading
#: * ``bullet`` — ``-``/``*``/``+`` + space/tab/EOL  → a list item
#: * ``tbreak`` — 3+ of the SAME ``-``/``*``/``_``   → a thematic break
#: * ``quote``  — ``>`` (no space needed)            → a blockquote
#: * ``odelim`` — ``N.``/``N)`` + space/tab/EOL      → an ordered list item
#: * ``pipe``   — a leading ``|``                    → a GFM table row
#: * ``delim``  — a GFM delimiter-row shape (``--|--``) → makes the PREVIOUS
#:                line a table header; also a setext ``---`` underline
#: * ``setext`` — a run of ``=``                     → a setext h1 underline
_LINE_LEADING_RE = re.compile(
    r"""
    ^[ ]{0,3}(?:
        (?P<atx>\#{1,6})(?=[ \t]|$)
      | (?P<bullet>[-*+])(?=[ \t]|$)
      | (?P<tbreak>(?P<tbc>[-*_])(?:[ \t]*(?P=tbc)){2,})[ \t]*$
      | (?P<quote>>)
      | \d{1,9}(?P<odelim>[.)])(?=[ \t]|$)
      | (?P<pipe>\|)
      | (?P<delim>:?-+:?(?:[ \t]*\|[ \t]*:?-+:?)*[ \t]*\|?)[ \t]*$
      | (?P<setext>=+)[ \t]*$
    )
    """,
    re.VERBOSE,
)


def _delimiter_runs(s: str, ch: str) -> List[tuple]:
    """Every maximal run of ``ch`` in ``s`` as ``(start, end)`` half-open spans."""
    runs = []
    i, n = 0, len(s)
    while i < n:
        if s[i] == ch:
            j = i
            while j < n and s[j] == ch:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def _is_candidate_run(s: str, run: tuple, ch: str) -> bool:
    """Could this run act as an emphasis delimiter at all?

    Only ``_`` has an extra rule: CommonMark forbids INTRAWORD underscore
    emphasis, so an ``_`` flanked by alphanumerics on both sides (``snake_case``)
    can never delimit and must not be escaped. ``*``/`` ` ``/``~`` have no such
    rule — every run is a candidate.
    """
    if ch != "_":
        return True
    i, j = run
    before = s[i - 1] if i > 0 else ""
    after = s[j] if j < len(s) else ""
    return not (before.isalnum() and after.isalnum())


def _emphasis_chars_to_escape(s: str) -> frozenset:
    """Which delimiter chars in ``s`` have TWO+ candidate runs (so could pair)."""
    return frozenset(
        ch
        for ch in _EMPHASIS_CHARS
        if sum(1 for r in _delimiter_runs(s, ch) if _is_candidate_run(s, r, ch)) >= 2
    )


def _escape_emphasis(s: str, chars: frozenset) -> str:
    """Backslash every character of every candidate run of each ch in ``chars``.

    The WHOLE run is escaped, not just its first character: ``\\**x\\**`` still
    leaves a pairable single ``*`` on each side and emphasis would still form.
    """
    if not chars:
        return s
    positions = set()
    for ch in chars:
        for run in _delimiter_runs(s, ch):
            if _is_candidate_run(s, run, ch):
                positions.update(range(*run))
    if not positions:
        return s
    return "".join(("\\" + c) if i in positions else c for i, c in enumerate(s))


def _escape_line_leading(line: str) -> str:
    """Escape the block marker ``line`` starts with, if any (else return it as-is)."""
    m = _LINE_LEADING_RE.match(line)
    if not m:
        return line
    if m.group("odelim"):
        # Escape the `.`/`)` — a backslash before the digit is not an escape.
        i = m.start("odelim")
    else:
        # The marker starts right after the 0-3 spaces of allowed indent.
        matched = m.group(0)
        i = len(matched) - len(matched.lstrip(" "))
    return line[:i] + "\\" + line[i:]


def _escape_structural(s: str, at_line_start: bool, block: bool, chars=None) -> str:
    """Escape only what would otherwise parse as STRUCTURE in ``s``.

    :param at_line_start: the fragment begins at a block-content line start (so
        its FIRST line can carry a live block marker). Lines after an embedded
        ``\\n`` are always line starts.
    :param block: the fragment is in BLOCK context at all. ``False`` for an
        inline-only context (a GFM table cell, a Sheets cell) where a block
        marker cannot form and escaping one would be pure backslash noise; the
        pair-wise emphasis escaping still applies there.
    :param chars: which emphasis delimiters to escape; ``None`` decides from
        ``s`` itself (the caller overrides it when the pairing decision spans a
        wider run than this fragment — see :meth:`MarkdownRenderer._text_out`).
    """
    if not s:
        return s
    # Emphasis FIRST: it may insert a backslash at a line start, and a line
    # already beginning with `\` matches no line-leading marker — so the two
    # passes compose without ever double-escaping.
    if chars is None:
        chars = _emphasis_chars_to_escape(s)
    out = _escape_emphasis(s, chars)
    if not block:
        return out
    lines = out.split("\n")
    return "\n".join(
        _escape_line_leading(ln) if (i or at_line_start) else ln
        for i, ln in enumerate(lines)
    )


# --------------------------------------------------------------------------- #
# Layer 2 — the escape-literals policy, and its EXACT INVERSE.                  #
#                                                                              #
# The two live side by side on purpose: they are one codec, and a decoder that #
# drifts from its encoder silently corrupts the text it claims to restore.     #
# --------------------------------------------------------------------------- #

def _escape_literals(s: str) -> str:
    """Backslash EVERY escapable character in ``s`` (the escape-literals policy).

    The layer-2 escaper. It is deliberately total rather than clever: a backslash is
    itself escapable, so the output is prefix-free and :func:`unescape_literals`
    inverts it exactly.
    """
    out = []
    for ch in s:
        if ch in _ESCAPABLE:
            out.append("\\")
        out.append(ch)
    return "".join(out)


def unescape_literals(text: str) -> str:
    """Turn escaped Markdown back into the literal text it was made from.

    The exact inverse of the reader's escape-literals output policy: under that
    policy a backslash always introduces exactly one escapable character, so the
    decode is a single left-to-right pass with no lookahead and no heuristics.
    ``unescape_literals(escaped) == original`` for any text the policy produced —
    literal backslashes, escaped metacharacters, a line made only of escapes, CRLF
    and LF line endings, and the verbatim body of a code fence all round-trip.

    A backslash that introduces a character the policy never escapes — or one that
    ends the text — cannot have come from the escaper. Two readings are then
    possible and neither is safe to assume, so this **refuses** with
    :class:`~larkdocio.errors.LarkEscapeError` and a ``detail`` naming the position
    and the character, rather than dropping the backslash or keeping it and calling
    the text restored.
    """
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= n:
            raise LarkEscapeError(
                f"a backslash at position {i} ends the text: the escape policy never "
                f"emits a trailing backslash (a literal one is written '\\\\'), so this "
                f"text was not produced by it and cannot be decoded without guessing"
            )
        nxt = text[i + 1]
        if nxt not in _ESCAPABLE:
            raise LarkEscapeError(
                f"a backslash at position {i} introduces {nxt!r}, which the escape "
                f"policy never escapes, so this text was not produced by it; decoding "
                f"would have to guess whether the backslash is literal or a truncated "
                f"escape"
            )
        out.append(nxt)
        i += 2
    return "".join(out)


# --------------------------------------------------------------------------- #
# The block-identity marker — one canonical shape, defined once.                #
# --------------------------------------------------------------------------- #

#: The one canonical marker shape: single-line, namespaced, and carrying nothing but
#: the block's own identifier.
_BLOCK_ID_MARKER = "<!-- lark:block:{block_id} -->"

#: The OPAQUE variant (LD-231): the same marker plus a named kind, for a block the
#: projection conserves rather than invites an edit to. One optional attribute rather
#: than a second marker shape, so every reader of a marker keeps working and "is this
#: block opaque" is a group test rather than a heuristic. See
#: :mod:`larkdocio.model.conservation` for which types take it and why.
_OPAQUE_BLOCK_ID_MARKER = "<!-- lark:block:{block_id} opaque={kind} -->"

#: The marker's own bytes, unanchored — **the one definition of the marker grammar**, and
#: the pattern both matchers below are built from, so "is this line a marker?" and "does
#: this text carry one anywhere?" cannot drift apart (LD-239 AC5). Group 1 is the
#: identifier; group 2 is the opaque kind, or ``None`` for an editable block.
BLOCK_ID_MARKER_RE = re.compile(r"<!-- lark:block:(\S+)(?: opaque=(\S+))? -->")

#: A whole projected marker LINE. The optional prefix is exactly the two line-leading
#: transforms the renderer applies to an already-serialized block — a list item's
#: indent tabs and a quote/callout's ``>`` — so a marker nested inside either is still
#: recognized, and nothing else is. Same groups as :data:`BLOCK_ID_MARKER_RE`, which is
#: literally what it wraps.
#:
#: **This stays line-shaped on purpose.** Reading an edited projection, a marker *is* a
#: line by grammar; matching one mid-sentence here would delete a consumer's prose out of
#: the middle of their own writing. It is the write path's compile guard — where the text
#: is arbitrary prose nobody parses — that asks the position-independent question.
BLOCK_ID_MARKER_LINE_RE = re.compile(
    r"^[ \t>]*" + BLOCK_ID_MARKER_RE.pattern + r"[ \t]*$"
)

#: A line that **claims** to be a marker: an HTML comment opening a line and naming the
#: marker's own namespace. Anything this matches that :data:`BLOCK_ID_MARKER_LINE_RE`
#: does **not** is **mangled** — marker-shaped but not byte-exact — and a reader of an
#: edited projection refuses it rather than repairing it, because a marker-shaped line
#: that is not byte-exact may be content that merely looks like one.
#:
#: It is deliberately narrow in two ways. It requires the **comment opener at the start of
#: the line** (after the same list/quote prefixes the canonical form allows), so prose that
#: merely mentions the namespace mid-sentence is content, not a mangled marker; and it
#: does not match the **escaped** form the projection emits for marker-shaped text inside
#: a block, which is a real, legitimate piece of that block's content.
BLOCK_ID_MARKER_SHAPED_LINE_RE = re.compile(r"^[ \t>]*<!--[^\n]*lark:block:")


def block_id_marker(block_id: str, opaque_kind: Optional[str] = None) -> str:
    """The canonical block-identity marker for ``block_id`` (no trailing newline).

    With ``opaque_kind``, the conserved variant naming that kind.
    """
    if opaque_kind is None:
        return _BLOCK_ID_MARKER.format(block_id=block_id)
    return _OPAQUE_BLOCK_ID_MARKER.format(block_id=block_id, kind=opaque_kind)


class _Esc(NamedTuple):
    """How a literal fragment must be escaped at THIS point in the output.

    Threaded through the inline serializers so a literal run knows whether it
    sits at a block-content line start, in block context at all, or inside
    verbatim content that must never be escaped.
    """

    at_line_start: bool = False
    block: bool = False
    verbatim: bool = False


#: The default for a bare ``render_inline`` call: inline context (a cell value, a
#: heading's own run) — pair-wise emphasis escaping only, no block markers.
_INLINE_ESC = _Esc()


# Auto-linkify bare URLs — ALWAYS ON, NO KNOB (LD-054; maintainer directive). A bare
# ``http(s)://…`` URL in plain/styled text becomes ``[url](url)``. Match the
# scheme plus its run of non-whitespace; the boundary is finished by peeling
# trailing sentence punctuation (below) so a period/paren/comma after the URL
# stays OUTSIDE the link. Deliberately conservative: only ``http``/``https`` —
# ``mailto:`` / ``ftp:`` / bare ``www.`` are left as literal text (LD-054 Out of
# Scope). Double-linking is prevented at the call sites, never here: runs
# already carrying a ``.link`` and ``mention_doc`` output are emitted as links
# directly (bypassing this pass), while inline-code and code-fence content is
# rendered with ``linkify=False`` (verbatim), so a URL there is never rewritten.
_BARE_URL_RE = re.compile(r"https?://\S+")
# Trailing punctuation peeled off a matched URL so it renders outside the link
# (AC3: a sentence-ending ``.`` / ``)`` / ``,`` is not swallowed).
_URL_TRAILING_PUNCT = ".,;:!?)"


# --------------------------------------------------------------------------- #
# LD-144 — the merged-table <td> HTML cell serializer                          #
# --------------------------------------------------------------------------- #

#: Which HTML list wrapper each list-item node kind groups into. Grouping is by
#: EXACT node type, not by this tag: a bullet list and a todo list both wrap in
#: ``<ul>`` but are two distinct lists and must not be folded into one.
_HTML_LIST_TAG = {
    BulletListItemNode: "ul",
    OrderedListItemNode: "ol",
    TodoListItemNode: "ul",
}

#: Inline style flags → their HTML tag, applied INNERMOST-FIRST so the resulting
#: nesting matches the Markdown path's marker order exactly (bold outermost:
#: ``**_~~<u>x</u>~~_**`` ⇒ ``<strong><em><s><u>x</u></s></em></strong>``).
#: ``<s>`` (not ``<del>``) per LD-144 AC1 — ``<del>`` carries an edit-tracking
#: meaning the source run does not; the ``use_html_tags`` *Markdown* policy keeps
#: its own ``<del>`` and is a separate, unrelated knob.
_HTML_STYLE_TAGS = (("underline", "u"), ("strikethrough", "s"),
                    ("italic", "em"), ("bold", "strong"))


def _split_edge_whitespace(s: str) -> tuple[str, str, str]:
    """Split ``s`` into ``(leading_ws, core, trailing_ws)``.

    ``core`` is ``s`` with only its edge whitespace removed (interior whitespace
    preserved). A whitespace-only or empty string yields ``("", "", "")``-style
    empty ``core`` with the original returned to the caller via ``s`` itself — the
    caller detects ``core == ""`` and emits the raw whitespace with no markers.
    """
    core = s.strip()
    if not core:
        return "", "", ""
    lead = s[: len(s) - len(s.lstrip())]
    trail = s[len(s.rstrip()):]
    return lead, core, trail


class MarkdownRenderer:
    """Serialize a block :class:`~larkdocio.model.nodes.Node` to Markdown.

    Dispatches per node type. ``escape_literals`` defaults to ``False`` (raw
    passthrough — exactly today's output).

    ``emit_block_ids`` is the third rendering policy and it too defaults **off**, so
    a default renderer's bytes are unchanged. Turned on, every block-level node that
    carries an identifier and renders content is preceded by a single-line
    identity marker, and :attr:`emitted_block_ids` accumulates the identifiers in
    document order as they are emitted — the authoritative list, which is why nothing
    downstream has to recover it by pattern-matching the text.
    """

    def __init__(self, escape_literals: bool = False, use_html_tags: bool = False,
                 emit_block_ids: bool = False):
        self.escape_literals = escape_literals
        # Table-cell rendering context (LD-130), set only for the duration of a
        # cell's recursion by :meth:`_cell_text` and restored after:
        #   "md"   — a GFM pipe-table cell: an INLINE-only context (a block
        #            marker cannot form there), so line-leading escaping is off.
        #            This is also what keeps the cell pipe-escape single (the
        #            escaper never emits a `\|` for the table pass to re-escape).
        #   "html" — a merged-table <td>: raw HTML, NOT markdown-parsed at all,
        #            so ANY escaping there would show a literal backslash.
        self._cell_mode = None
        # Rendering policy (like escape_literals): when on, bold/italic/strike
        # emit HTML tags (<strong>/<em>/<del>) instead of Markdown markers. Fed
        # from Config.output.use_html_tags by the Parser. Underline is always the
        # HTML <u> wrapper regardless (Markdown has no underline).
        self.use_html_tags = use_html_tags
        # Rendering policy #3 — the block-identity marker projection. OFF by default,
        # so a default renderer emits exactly the bytes it always has. `emitted_block_ids`
        # is the authoritative record of what the projection actually emitted, in
        # DOCUMENT order (a parent's identifier precedes its children's), appended as
        # each marker is decided rather than recovered from the finished text.
        self.emit_block_ids = emit_block_ids
        self.emitted_block_ids: List[str] = []
        # Which of those markers went out OPAQUE (LD-231) — a parallel flag list rather
        # than a second id list, so the conserved subset inherits the same DOCUMENT
        # order and the same withdraw-the-claim bookkeeping for free. A reconciler must
        # be able to ask "may I touch this block?" without re-parsing the text it was
        # just handed; `emitted_opaque_block_ids` is that answer.
        self._emitted_opaque_flags: List[bool] = []
        self._dispatch = self._build_dispatch()
        # The SECOND dispatch table (LD-144): block node -> its HTML form, used
        # only inside a merged table's <td>. Separate from _dispatch because the
        # two answer different questions — "what Markdown is this block?" vs.
        # "what HTML is this block?" — and a <td> can accept only the latter.
        self._html_cell_dispatch = self._build_html_cell_dispatch()

    # -- block-level dispatch -------------------------------------------------
    #
    # ONE exact-type ``{type: bound_method}`` table dispatches a block node to
    # its serializer (LD-085; converted from the prior ~73-line linear isinstance
    # chain). Every serializer takes the UNIFORM ``(node, depth)`` signature so
    # the table can call each the same way — ``depth`` is the list-nesting level,
    # consumed ONLY by the list-item serializer (which owns its own leading indent
    # tab) and threaded unchanged by the own-depth recursers (grid/view/
    # unknown-block/agenda/source_synced); every other serializer ignores it. See
    # the recursion/indent contract at the top of ``read/parser.py``.
    #
    # Exact-type (``type(node)``) dispatch is equivalent to the old isinstance
    # chain ONLY because every block Node is a DIRECT ``@dataclass(Node)`` leaf —
    # no Node subclass extends another Node, so no node ever relied on matching a
    # BASE-class arm, and dispatch order is irrelevant (no arm could shadow
    # another). The three agenda wrappers (44/45/47) share the ONE transparent
    # serializer, exactly as their single combined isinstance arm did. This
    # invariant is pinned by ``test_block_nodes_are_direct_node_leaves``; a future
    # Node subclass would need an explicit registration here.

    def _build_dispatch(self):
        return {
            PageNode: self._page,
            DocumentNode: self._document,
            RawBlock: self._raw_block,
            DividerNode: self._divider,
            QuoteNode: self._quote,
            HeadingNode: self._heading,
            BulletListItemNode: self._bullet_item,
            OrderedListItemNode: self._ordered_item,
            TodoListItemNode: self._todo_item,
            TextNode: self._text_block,
            CodeNode: self._code,
            EquationBlockNode: self._equation_block,
            TableNode: self._table,
            TableCellNode: self._table_cell,
            CalloutNode: self._callout,
            QuoteContainerNode: self._quote_container,
            GridNode: self._grid,
            GridColumnNode: self._grid_column,
            ViewNode: self._view,
            UnknownBlockNode: self._unknown_block,
            AgendaNode: self._transparent,
            AgendaItemNode: self._transparent,
            AgendaItemContentNode: self._transparent,
            AgendaItemTitleNode: self._agenda_item_title,
            IframeNode: self._iframe,
            ImageNode: self._image,
            BoardNode: self._board,
            AddOnsNode: self._add_ons,
            FileNode: self._file,
            SourceSyncedNode: self._source_synced,
            ReferenceSyncedNode: self._reference_synced,
            BitableNode: self._bitable,
            SheetNode: self._sheet,
            ReferenceBaseNode: self._reference_base,
        }

    def render(self, node: Node, depth: int = 0) -> str:
        marker, body = self._render_parts(node, depth)
        return marker + body

    def _render_parts(self, node: Node, depth: int = 0) -> Tuple[str, str]:
        """Serialize ``node`` as ``(identity_marker_line, body)``.

        :meth:`render` simply concatenates the two. The pair exists because one
        caller — the list-item serializer — has to decide its blank-line separator
        from what the CHILD BLOCK rendered, and prefixing a marker onto that string
        first would answer a different question. Splitting the two keeps the
        projection strictly additive: with the marker removed, every branch in this
        renderer sees byte-for-byte what it saw before.

        ``marker`` is ``""`` whenever the projection is off or this node has nothing
        to anchor — see :meth:`_block_id_marker_line`.
        """
        serializer = self._dispatch.get(type(node))
        if serializer is None:
            raise TypeError(
                f"MarkdownRenderer has no serializer for block node "
                f"{type(node).__name__}"
            )
        if not self._marker_wanted(node):
            return "", serializer(node, depth)
        # Claim this node's place in the emitted sequence BEFORE serializing its body,
        # so the identifiers come back in DOCUMENT order (parent before children)
        # rather than in the post-order the recursion finishes in. The claim is
        # withdrawn below if the body turns out to be empty.
        slot = len(self.emitted_block_ids)
        kind = _opaque_kind(node.block_type)
        self.emitted_block_ids.append(node.block_id)
        self._emitted_opaque_flags.append(kind is not None)
        body = serializer(node, depth)
        marker = self._block_id_marker_line(node, body, kind)
        if not marker:
            del self.emitted_block_ids[slot]
            del self._emitted_opaque_flags[slot]
        return marker, body

    @property
    def emitted_opaque_block_ids(self) -> List[str]:
        """The conserved subset of :attr:`emitted_block_ids`, in document order."""
        return [
            block_id
            for block_id, opaque in zip(
                self.emitted_block_ids, self._emitted_opaque_flags
            )
            if opaque
        ]

    def _marker_wanted(self, node: Node) -> bool:
        """Whether ``node`` is eligible for an identity marker at all.

        Three conditions, all structural. The projection must be on; the node must
        carry an identifier (inline content never does — an identifier is a
        block-level fact); and rendering must not be inside a TABLE CELL, where a
        marker is not expressible: a pipe-table row is one line and a merged table's
        cell is raw HTML, so a marker line there would tear the table rather than
        annotate it. Cells are therefore annotated at the table block itself.
        """
        return bool(self.emit_block_ids and node.block_id and self._cell_mode is None)

    def _block_id_marker_line(self, node: Node, body: str,
                              kind: Optional[str] = None) -> str:
        """The marker line to place before ``body``, or ``""`` for no marker.

        An EDITABLE block that rendered nothing gets none: a marker pointing at no
        content is an anchor to a place in the document that does not exist. An
        OPAQUE one gets its marker regardless, and that asymmetry is the whole point
        of the opaque form — a block whose content the Markdown cannot carry is
        exactly the block that must still be anchored, or a reconciler reading the
        projection would have no evidence it exists at all. The leaf unknown-type
        block (which renders nothing of its own by design) is the case.

        The line carries the body's own leading indent so a marker inside a nested
        list sits at the same column as the item it introduces, which is what keeps
        the surrounding list structure intact instead of breaking out of it.
        """
        if not body.strip() and kind is None:
            return ""
        indent = body[: len(body) - len(body.lstrip("\t"))]
        return f"{indent}{block_id_marker(node.block_id, kind)}\n"

    # -- inline ---------------------------------------------------------------

    def render_inline(
        self,
        nodes: List[Inline],
        linkify: bool = True,
        *,
        block_context: bool = False,
        verbatim: bool = False,
    ) -> str:
        # ``linkify`` gates the always-on bare-URL pass (LD-054). It is threaded
        # through to the literal-text sites and defaults ON; the code-fence
        # serializer (:meth:`_code`) passes ``linkify=False`` so a URL inside a
        # ``` fence stays verbatim (code content is verbatim, like inline code).
        #
        # ``block_context`` (LD-130) says this run is emitted at a BLOCK-content
        # line start — a paragraph, a list item's own text, a quote line — so a
        # line-leading ``#``/``-``/``|``/… in LITERAL text would parse as
        # structure and is escaped. Default OFF: a bare call is an inline
        # context (a Sheets cell value, a heading's own run), where only the
        # pair-wise emphasis escaping applies. ``verbatim`` turns layer 1 off
        # entirely for already-formatted or verbatim content.
        ctx = _Esc(at_line_start=block_context, block=block_context, verbatim=verbatim)
        if self._cell_mode == "html":
            ctx = ctx._replace(verbatim=True)
        elif self._cell_mode == "md":
            ctx = ctx._replace(at_line_start=False, block=False)
        out = []
        cur = ctx
        for n in nodes:
            piece = self._inline(n, linkify, cur)
            out.append(piece)
            if piece:
                # Only a run that ENDED a line leaves the next one at a line
                # start; an empty piece leaves the position unchanged.
                cur = ctx._replace(at_line_start=piece.endswith("\n"))
        return "".join(out)

    def _inline(self, n: Inline, linkify: bool = True, ctx: _Esc = _INLINE_ESC) -> str:
        if isinstance(n, Text):
            return self._text_out(n.content, linkify=linkify, ctx=ctx)
        if isinstance(n, StyledText):
            return self._styled(n, linkify=linkify, ctx=ctx)
        if isinstance(n, MentionUser):
            return f"@{n.user_id}"
        if isinstance(n, MentionDoc):
            return f"[{n.title}]({n.url})"
        if isinstance(n, InlineEquation):
            return f"${n.content}$"
        if isinstance(n, UnsupportedInline):
            return f"[unsupported inline: {n.variant}]"
        if isinstance(n, RawInline):
            # Already-formatted markup — passes through verbatim, never escaped.
            return n.markup
        raise TypeError(
            f"MarkdownRenderer has no serializer for inline node "
            f"{type(n).__name__}"
        )

    def _styled(self, n: StyledText, linkify: bool = True, ctx: _Esc = _INLINE_ESC) -> str:
        # Literal content follows the same escape policy as a bare Text node; the
        # style markers are structural and never escaped. Composition order is
        # bold -> italic -> strikethrough -> underline (each wrapping the last via
        # prefix/prepended-suffix so the markers nest), then inline code, then a
        # Markdown link outermost. This mirrors the legacy text.py formatter
        # exactly; it is the ONE place the composition lives.
        #
        # The marker stack is built FIRST because it decides the content's escape
        # context (LD-130): a run carrying any marker no longer starts the line
        # (``**# x**`` cannot be a heading — the line starts with ``*``), so
        # line-leading escaping is dropped for it. An UNSTYLED StyledText (the
        # common real-payload shape: a style object with every flag false) keeps
        # the line start, exactly like a bare ``Text``.
        prefix = ""
        suffix = ""
        if n.bold:
            if self.use_html_tags:
                prefix += "<strong>"
                suffix = "</strong>" + suffix
            else:
                prefix += "**"
                suffix = "**" + suffix
        if n.italic:
            if self.use_html_tags:
                prefix += "<em>"
                suffix = "</em>" + suffix
            else:
                prefix += "_"
                suffix = "_" + suffix
        if n.strikethrough:
            if self.use_html_tags:
                prefix += "<del>"
                suffix = "</del>" + suffix
            else:
                prefix += "~~"
                suffix = "~~" + suffix
        if n.underline:
            prefix += "<u>"
            suffix = "</u>" + suffix
        # A marker stack, a link's ``[`` wrapper, or a code span all mean the
        # literal content no longer begins the line.
        inner_ctx = ctx if not (prefix or n.link_url is not None) else ctx._replace(at_line_start=False)
        if n.inline_code:
            # Code spans treat ** literally and tolerate internal whitespace, so
            # edge whitespace is harmless here — leave inline-code runs
            # byte-identical (no relocation). Inline code wraps the marker stack.
            # Content inside a code span is VERBATIM: structural escaping there
            # would surface a literal backslash to the reader (LD-130).
            content = self._esc(n.content, inner_ctx._replace(verbatim=True))
            inner = f"`{prefix}{content}{suffix}`"
        else:
            # A run that already carries a link is emitted as ``[inner](link)``
            # below, so its inner text must NOT be auto-linkified (LD-054 AC2 —
            # no double-link). A plain/styled run with no link gets bare-URL
            # linkify applied to its literal content.
            body = (
                self._esc(n.content, inner_ctx)
                if n.link_url is not None
                else self._text_out(n.content, linkify=linkify, ctx=inner_ctx)
            )
            # Relocate leading/trailing whitespace OUTSIDE the marker stack so an
            # emphasis/strike closer is never left-flanked by a space (an invalid
            # CommonMark delimiter that leaks literal `**`). Done once around the
            # whole composed run, not per marker (LD-052). A whitespace-only (or
            # empty) run has no core to emphasize, so its markers drop entirely.
            leading_ws, core, trailing_ws = _split_edge_whitespace(body)
            if core == "":
                inner = body
            else:
                inner = f"{leading_ws}{prefix}{core}{suffix}{trailing_ws}"
        if n.link_url is not None:
            inner = f"[{inner}]({n.link_url})"
        return inner

    def _esc(self, s: str, ctx: _Esc = _INLINE_ESC, chars: frozenset = None) -> str:
        """Escape a literal-text fragment for the position ``ctx`` describes.

        Layer 2 (``escape_literals``, opt-in) supersedes layer 1 when on — it
        already escapes a superset. Otherwise layer 1 (LD-130, always on) escapes
        the structural ambiguity only, and ``verbatim`` content is untouched.

        ``chars`` overrides which emphasis delimiters to escape — used by
        :meth:`_text_out` so the pairing decision is made across the whole run
        (URLs excluded) rather than per URL-split fragment.
        """
        if self.escape_literals:
            return self._escape(s)
        if ctx.verbatim:
            return s
        return _escape_structural(s, ctx.at_line_start, ctx.block, chars)

    def _text_out(self, s: str, linkify: bool = True, ctx: _Esc = _INLINE_ESC) -> str:
        """Escape (per policy) and auto-linkify bare URLs in literal text.

        ALWAYS-ON linkify (LD-054, no knob): a bare ``http(s)://…`` becomes
        ``[url](url)``. Trailing sentence punctuation is peeled off the match so
        it stays outside the link (AC3). The URL destination itself is emitted
        verbatim (never backslash-escaped, so the link stays valid); surrounding
        literal text still follows the escape policy.

        ``linkify=False`` suppresses the URL pass entirely (escape-only), so
        VERBATIM content is preserved byte-for-byte. Two verbatim sites use it:
        inline code (handled in :meth:`_styled` without calling here) and
        code fences (:meth:`_code` passes ``linkify=False``). This keeps the
        no-double-link guardrail (AC2): a URL inside a code span or ``` fence is
        never rewritten to ``[url](url)``.

        The emphasis-pairing decision (LD-130) is taken over the text OUTSIDE the
        URLs and then applied to each fragment, so a URL's own ``_``/``~`` neither
        triggers escaping in the prose nor lets a pair straddling the link slip
        through unescaped.
        """
        if not linkify:
            return self._esc(s, ctx)
        matches = list(_BARE_URL_RE.finditer(s))
        if not matches:
            return self._esc(s, ctx)
        outside = []
        pos = 0
        for m in matches:
            outside.append(s[pos:m.start()])
            pos = m.end()
        outside.append(s[pos:])
        chars = _emphasis_chars_to_escape("".join(outside))
        out: List[str] = []
        pos = 0
        frag_ctx = ctx
        for m in matches:
            out.append(self._esc(s[pos:m.start()], frag_ctx, chars))
            # Past the first URL nothing starts the line any more (a URL match is
            # non-whitespace, so it can never end a line itself); a line start
            # AFTER an embedded newline is still handled inside _esc.
            frag_ctx = ctx._replace(at_line_start=False)
            url = m.group(0)
            core = url.rstrip(_URL_TRAILING_PUNCT)
            trailing = url[len(core):]
            out.append(f"[{core}]({core})")
            out.append(self._esc(trailing, frag_ctx, chars))
            pos = m.end()
        out.append(self._esc(s[pos:], frag_ctx, chars))
        return "".join(out)

    def _escape(self, s: str) -> str:
        # Layer 2 lives at module level beside its exact inverse
        # (:func:`unescape_literals`) so the codec cannot drift apart half at a time.
        return _escape_literals(s)

    # -- block serializers ----------------------------------------------------

    # -- spine roots (types 1 / headless fallback) + verbatim passthrough -----
    #
    # The parser spine builds a NODE TREE rooted here (LD-031). PageNode and
    # DocumentNode carry REAL CHILD NODES (page's children flipped from strings);
    # RawBlock carries a verbatim string — now the missing/unknown-block empty
    # sentinel (its strangler-shim string arm was removed in LD-032). Byte-
    # identical to the prior blocks/container.py page handler + the read/parser.py
    # string fallback.

    def _page(self, node: PageNode, depth: int = 0) -> str:
        # The document root (block type 1). Emit "# " + the rendered title ONLY
        # when that title is non-blank (the .strip() gate — a title-less or
        # whitespace-only page emits no dangling "# "), then a single blank
        # separator line, then each child node's serialization followed by the
        # page's own "\n" child separator.
        buf = []
        title = self.render_inline(node.title)
        if title.strip():
            buf.append("# ")
            buf.append(title)
            buf.append("\n")
        buf.append("\n")
        for child in node.children:
            buf.append(self.render(child, 0))
            buf.append("\n")
        return "".join(buf)

    def _document(self, node: DocumentNode, depth: int = 0) -> str:
        # The headless-document fallback root: concatenate the child
        # serializations with NO separator (byte-identical to the prior "".join
        # fallback in parse_docx_content).
        return "".join(self.render(child, 0) for child in node.children)

    def _raw_block(self, node: RawBlock, depth: int = 0) -> str:
        # Verbatim block-level passthrough — the missing/unknown-block empty
        # sentinel (the strangler string arm it also carried was removed LD-032).
        return node.markup

    def _divider(self, node: DividerNode, depth: int = 0) -> str:
        return "---\n"

    def _blockquote_lines(self, lines: List[str]) -> List[str]:
        # Shared per-line blockquote prefix for _quote and _quote_container: a
        # non-blank line becomes "> {line}"; a blank line becomes a BARE ">" (no
        # trailing space). Callers keep their OWN pre-processing (strip vs.
        # per-child rstrip) and join/trailing — only the per-line rule is shared.
        # NOTE: _callout does NOT use this — it deliberately prefixes EVERY line
        # (blank ones included) with "> " (trailing space); that divergence is kept
        # inline in _callout by design (LD-010's pinned correction).
        return [f"> {line}" if line.strip() else ">" for line in lines]

    def _quote(self, node: QuoteNode, depth: int = 0) -> str:
        # The quote's own text is BLOCK content (it sits after the "> " prefix, so
        # a literal "- x" there would nest a real list inside the quote).
        content = self.render_inline(node.content, block_context=True).strip()
        if not content:
            return ""
        lines = self._blockquote_lines(content.split("\n"))
        return "\n".join(lines) + "\n\n"

    def _heading(self, node: HeadingNode, depth: int = 0) -> str:
        # The marker is CLAMPED to MAX_HEADING_LEVEL (LD-145 / dogfood round-2 T17):
        # Lark stores levels 1-9, CommonMark's ATX marker stops at 6, and 7 ``#`` is not a
        # heading at all to a conforming parser (it reads as a paragraph of literal ``#``,
        # which is why the old emission also failed to compose back). ``node.level`` is
        # deliberately NOT touched — the cap is a render-time projection and the tree keeps
        # the true level for every tree consumer. H7-9 therefore read back as H6, recorded
        # in the dialect lossiness table.
        buf = ["#" * min(node.level, MAX_HEADING_LEVEL), " "]
        if node.content is not None:
            buf.append(self.render_inline(node.content))
            buf.append("\n")
        if node.children:
            buf.append("\n")
        for child in node.children:
            # Recurse-at-0: heading children carry NODES (R-S2 flip) and render at
            # depth 0 — reproducing the prior already-rendered child string at depth 0.
            buf.append(self.render(child, 0))
            buf.append("\n")
        return "".join(buf)

    def _list_item(self, marker: str, content, children: List[Node], depth: int) -> str:
        # ONE list-item serializer, and the ONE place the list indent lives: a
        # leading ``depth`` hard tabs, then the marker prefix, then (when the
        # payload was present) the inline run + the block newline, then each child
        # NODE rendered one level deeper (``depth + 1``) — the list family is the
        # one place indent deepens. The indent tab was relocated here from the
        # parser string boundary (which keyed it on the source block_type); it is
        # now owned by the serializer and keyed on the node kind — a list-item node
        # at depth N carries N tabs, and every other serializer ignores depth so a
        # block-level child (table/code) nested under a list item still renders at
        # column 0 (never corrupted into an indented code block). content None
        # models the SDK payload being absent — the legacy handler emitted just the
        # marker with no newline; a present list emits the run + "\n"
        # (present-but-empty is "marker\n"). Byte-identical to the prior string
        # handlers: render-time depth+1 == the parse-time indent_level+1 the child
        # nodes were built at.
        buf = ["\t" * depth, marker]
        if content is not None:
            # A list item's own text is BLOCK content: "- # x" nests a real ATX
            # heading inside the item, so line-leading markers are escaped here.
            buf.append(self.render_inline(content, block_context=True))
            buf.append("\n")
        for child in children:
            # Rendered as (marker, body) so the breakout decision below is taken on
            # the CHILD BLOCK's own bytes: an identity marker must not make an empty
            # child look non-empty, and the separator belongs BEFORE the marker so the
            # marker still sits immediately against the content it introduces.
            child_marker, rendered = self._render_parts(child, depth + 1)
            if self._is_list_breakout(child) and rendered.strip():
                # A block-level child that BREAKS OUT of list context (a table,
                # code fence, quote, divider — anything rendering at column 0
                # that is not itself a list item) must be separated from the
                # list-item paragraph by a blank line. Without it CommonMark
                # lazy-continuation folds the block into the list paragraph, so a
                # table renders as literal ``|`` pipes and a fenced block can
                # mis-parse (LD-051). The marker line ends with a single "\n";
                # emit one more so the paragraph terminates — but never a triple
                # newline when the prior child already left a trailing blank line.
                if not "".join(buf).endswith("\n\n"):
                    buf.append("\n")
            buf.append(child_marker)
            buf.append(rendered)
        return "".join(buf)

    # List-family children keep list context (the serializer indents them); a
    # plain text/paragraph breakout (``TextNode``) is deliberately NOT separated
    # here — it is already text (no block re-parse to protect) and cleanly
    # separating a bare interruption also requires re-separating a following
    # list, a distinct list-run concern outside this contract. The empty
    # ``RawBlock`` sentinel renders nothing and needs no separator. Everything
    # else that renders at column 0 is a block-level breakout.
    _LIST_CONTEXT_CHILDREN = (
        BulletListItemNode,
        OrderedListItemNode,
        TodoListItemNode,
        TextNode,
        RawBlock,
    )

    def _is_list_breakout(self, node: Node) -> bool:
        return not isinstance(node, self._LIST_CONTEXT_CHILDREN)

    def _bullet_item(self, node: BulletListItemNode, depth: int = 0) -> str:
        return self._list_item("- ", node.content, node.children, depth)

    def _ordered_item(self, node: OrderedListItemNode, depth: int = 0) -> str:
        return self._list_item(f"{node.order}. ", node.content, node.children, depth)

    def _todo_item(self, node: TodoListItemNode, depth: int = 0) -> str:
        marker = "- [x] " if node.done else "- [ ] "
        return self._list_item(marker, node.content, node.children, depth)

    def _text_block(self, node: TextNode, depth: int = 0) -> str:
        # content None models the SDK text attr being absent (legacy emitted
        # nothing); a present list emits the inline run + the block newline.
        if node.content is None:
            return ""
        # THE case dogfood F1 found: a paragraph is block content, so a literal
        # "# Fake H1" here must not emit a real heading (LD-130).
        return self.render_inline(node.content, block_context=True) + "\n"

    def _code(self, node: CodeNode, depth: int = 0) -> str:
        # Code-fence content is VERBATIM — pass ``linkify=False`` so a bare URL
        # inside the fence (e.g. a ``curl``/``pip`` example) is NOT rewritten to
        # ``[url](url)`` (LD-054 AC2: code content is verbatim, mirroring inline
        # code). Without this the always-on URL pass corrupts the code.
        # ``verbatim=True`` (LD-130): source code is verbatim — a structural
        # escape inside a fence would corrupt the code it is quoting.
        #
        # NO TRIM (LD-146). The body is emitted byte-for-byte; the renderer adds only
        # the two fence lines and the single newline that closes the body. The whole-body
        # ``.strip()`` this line used to carry was inherited verbatim from the seed
        # script (never a decision taken here) and silently corrupted whitespace-
        # significant content: it clipped the FIRST line's indentation while every
        # later line kept its own (dogfood round 2 / T9, reproduced twice), and as
        # collateral it also ate the last line's trailing whitespace, a leading blank
        # line, and a whitespace-only body. Code-block content is verbatim by contract,
        # so there is nothing left to trim.
        #
        # This is the exact mirror of the rule ``write/compose.py`` ``_fence`` already
        # states from the other side — "that newline is syntax, not content; everything
        # else is kept verbatim" — which is what makes the code round-trip EXACT: a body
        # ending in "\n" emits a trailing blank line inside the fence, and ``compose``
        # removes precisely that one syntactic newline again.
        body = self.render_inline(node.content, linkify=False, verbatim=True)
        return f"```{node.lang}\n{body}\n```\n"

    def _equation_block(self, node: EquationBlockNode, depth: int = 0) -> str:
        return f"$$\n{node.content}\n$$\n"

    # -- table (types 31 / 32) ------------------------------------------------
    #
    # The renderer owns ALL table-structure serialization: newline flattening,
    # the cell pipe-escape (| -> \|) and HTML-escape, row folding, ragged
    # padding, header promotion, and the merged-cell HTML path. The handler only
    # recurses cells to already-rendered strings and pulls the structural data
    # (col_size / header_row / merge spans) off the SDK block. Byte-identical to
    # the prior blocks/table.py handler.

    @staticmethod
    def _html_escape(text: str) -> str:
        return (text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))

    @staticmethod
    def _table_has_merges(merges: List) -> bool:
        # A table has merges if any (row_span, col_span) pair declares a span > 1.
        # None/0 spans do NOT count (the legacy handler used `... or 0`, so a None
        # span reads as 0 here — distinct from span_for's None -> 1 normalization).
        for rs, cs in (merges or []):
            if (rs or 0) > 1 or (cs or 0) > 1:
                return True
        return False

    def _cell_text(self, cell, mode: str = None) -> str:
        """Render a table cell (or a cell's child block) to its text.

        A cell is a :class:`TableCellNode` and a cell's child is a block node
        (R-S3 flipped both carriages from already-rendered strings to child
        nodes); descend it at depth 0 — a table cell recurses at depth 0, so no
        indent deepens, reproducing the prior already-rendered child string at
        depth 0. A bare already-rendered ``str`` is accepted verbatim: the
        renderer-direct unit path (e.g. the R-S0 markdown-table survivor pins)
        constructs cells as strings; the reader path always carries nodes.

        ``mode`` (LD-130) sets the cell's escape context for the whole recursion
        — ``"md"`` for a GFM pipe-table cell (inline-only), ``"html"`` for a
        merged-table ``<td>`` (raw, never escaped). ``None`` inherits the current
        one, which is what :meth:`_table_cell` needs when the parent table
        already opened the context. Saved/restored so a nested table cannot leak
        its mode outward.
        """
        if isinstance(cell, str):
            return cell
        if mode is None:
            return self.render(cell, 0)
        prev = self._cell_mode
        self._cell_mode = mode
        try:
            return self.render(cell, 0)
        finally:
            self._cell_mode = prev

    def _table(self, node: TableNode, depth: int = 0) -> str:
        if not node.cells:
            return ""
        col_size = node.col_size or 1
        if self._table_has_merges(node.merges):
            return self._table_html(node, col_size)

        # --- Markdown path (no merges) ---
        # Markdown pipe-table cells cannot hold a literal newline (it would
        # break the row), so multi-line cell content is joined with <br>
        # (GitHub-style renderers stack the lines) rather than collapsed to
        # a space (LD-041). Strip the outer whitespace first so leading/
        # trailing blank lines don't become stray <br>; a single-line cell
        # has no internal newline and is therefore unchanged. HTML path
        # (_table_html) is deliberately left as-is (out of scope, LD-041 AC3).
        cell_strs: List[str] = []
        for cell_node in node.cells:
            cell = self._cell_text(cell_node, "md").strip().replace("\n", "<br>")
            # The pipe-escape stays SINGLE (LD-130 AC4c): a GFM cell is an
            # inline-only context, so the plain-text escaper never emits a `\|`
            # for this pass to re-escape into `\\|`.
            cell = cell.replace("|", "\\|")
            cell_strs.append(cell)
        # Fold the flat cells into rows via the shared row-major helper (LD-084)
        # — map each index row to its cell string (the fold no longer re-derives
        # r_idx inline). Ragged final row is padded to col_size below.
        rows: List[List[str]] = [
            [cell_strs[i] for i in idx_row]
            for idx_row in fold_rows(len(cell_strs), col_size)
        ]

        # Pad ragged final row to col_size with empty cells.
        if rows and len(rows[-1]) < col_size:
            rows[-1].extend([""] * (col_size - len(rows[-1])))

        buf = []
        if node.header_row:
            # Default: first row is the header.
            for i, r in enumerate(rows):
                buf.append("| " + " | ".join(r) + " |")
                if i == 0:
                    buf.append("|" + "|".join(["---"] * len(r)) + "|")
        else:
            # header_row False: do NOT promote the first data row. Markdown has
            # no headerless table syntax, so we emit an EMPTY header row above the
            # delimiter and keep every real row (including the first) as data.
            width = len(rows[0]) if rows else col_size
            buf.append("| " + " | ".join([""] * width) + " |")
            buf.append("|" + "|".join(["---"] * width) + "|")
            for r in rows:
                buf.append("| " + " | ".join(r) + " |")
        return "\n".join(buf) + "\n\n"

    def _table_html(self, node: TableNode, col_size: int) -> str:
        """Render a merged table as an HTML <table> with rowspan/colspan.

        **Coverage is COMPUTED, not read** (LD-050). Each cell index folds to a
        grid position ``(row, col) = (i // col_size, i % col_size)``. An anchor
        whose ``row_span``/``col_span`` exceeds 1 *claims* the grid positions its
        span covers; a claimed position emits **no** cell. This is the standard
        HTML-table occupancy algorithm.

        **A claimed position emits no cell, but its CONTENT is not discarded
        (LD-529).** Emitting no ``<td>`` used to drop the covered cell's whole
        subtree — text and images alike, and for an image the token stayed queued
        on ``parser.img_tokens`` so the bytes downloaded and nothing linked them.
        That loss was a side effect of LD-050's *layout* fix, never a ruling about
        content. So the rendered content of every covered position is **absorbed
        into the ``<td>``/``<th>`` of the anchor whose span claims it**, appended
        after the anchor's own content in row-major order of the claimed
        positions, with no marker wrapping it (see :meth:`_html_merged_cell` for
        the join). The grid is untouched: no cell at a covered position, and every
        rendered row still occupies exactly ``col_size`` grid columns.

        Why compute rather than trust ``merge_info`` at the covered position:
        real Lark payloads mark a covered cell **(1,1)**, NOT span-0 (verified
        from the gauntlet 4x4 table — anchors (2,1)@6 and (1,3)@13,
        covered idx 10/14/15 all read (1,1)). Reading the covered cell's own
        span therefore emitted a phantom ``<td>`` and misaligned every row that
        intersects a rowspan. The occupancy grid ignores the covered cell's
        ``merge_info`` entirely.

        Span-0 handling is retained belt-and-braces: a synthetic payload may
        still mark a covered cell with a 0 span, so a 0-span cell is also
        skipped. Anchor cells emit their declared spans (only attributes > 1 are
        written); a cell with no merge entry is a normal 1x1 cell.
        """
        cells = node.cells
        merges = node.merges or []
        header_row = node.header_row
        n = len(cells)

        # Build rows of cell indices via the shared row-major fold (LD-084) —
        # the same fold covered_positions uses, so a merged table folds once
        # per side instead of the fold being reimplemented inline here.
        rows = fold_rows(n, col_size)

        # Grid positions claimed by a preceding anchor's rowspan/colspan, plus
        # which anchor claims each of them. A cell landing on a claimed position
        # emits nothing and its own merge_info is never consulted, but its
        # CONTENT is absorbed into that anchor's cell (LD-529). Computed once up
        # front by the shared occupancy helper (LD-071 extraction of the LD-050
        # semantics, extended additively by LD-529 — the algorithm is not
        # reimplemented here); span_for is the lifted merge_span, used below only
        # for a cell's OWN emitted attrs.
        covered, claimed_by_anchor = occupancy(n, merges, col_size)

        def span_for(idx: int):
            return merge_span(merges, idx)

        lines = ["<table>"]
        body_open = False
        for r_idx, row in enumerate(rows):
            is_header = header_row and r_idx == 0
            if header_row and r_idx == 0:
                lines.append("<thead>")
            elif not body_open:
                # First non-header row (or first row when header_row is False).
                lines.append("<tbody>")
                body_open = True
            lines.append("<tr>")
            for c_idx, idx in enumerate(row):
                # Covered by a preceding anchor -> emit nothing (ignore its span).
                if (r_idx, c_idx) in covered:
                    continue
                rs, cs = span_for(idx)
                # Belt-and-braces: a synthetic 0-span covered marker also skips.
                if rs == 0 or cs == 0:
                    continue
                # (The grid positions this anchor's span covers were claimed up
                # front by covered_positions — no incremental bookkeeping here.)
                # An HTML <td> is raw: GFM markdown-parses NOTHING inside it, so
                # the cell gets its own HTML serializer (LD-144) rather than the
                # Markdown one — Markdown structure would be as inert there as
                # the backslash escape LD-130 already ruled out.
                content = self._html_merged_cell(
                    cells, idx, claimed_by_anchor.get(idx, ()))
                attrs = ""
                if rs and rs > 1:
                    attrs += f' rowspan="{rs}"'
                if cs and cs > 1:
                    attrs += f' colspan="{cs}"'
                tag = "th" if is_header else "td"
                lines.append(f"<{tag}{attrs}>{content}</{tag}>")
            lines.append("</tr>")
            if header_row and r_idx == 0:
                lines.append("</thead>")
        if body_open:
            lines.append("</tbody>")
        lines.append("</table>")
        return "\n".join(lines) + "\n\n"

    def _table_cell(self, node: TableCellNode, depth: int = 0) -> str:
        # A cell's child NODES (R-S3 flip) rendered at depth 0 and concatenated
        # verbatim — reproducing the prior already-rendered child strings (depth 0)
        # the cell used to carry. The parent table renderer collapses newlines +
        # escapes per its path. This is the MARKDOWN (pipe-table) carriage; a
        # merged table's cells go through _html_cell_content instead, joined per
        # merged span by _html_merged_cell (LD-144).
        return "".join(self._cell_text(child) for child in node.children)

    # -- the merged-table HTML cell serializer (LD-144) -----------------------
    #
    # Why a SECOND cell serializer instead of reusing the Markdown one: the
    # merged-table branch emits a raw HTML ``<table>``, and CommonMark/GFM
    # markdown-parses NOTHING inside an HTML block. So every piece of Markdown
    # *structure* the shared serializer produces is inert literal text in a
    # ``<td>``: ``**bold**`` renders as neither bold nor asterisks, ``- x`` is not
    # a list, a ``---`` divider is a stray dash run mid-sentence, and paragraph
    # boundaries — collapsed to spaces so a cell stayed one line — vanished
    # outright. Worse, the ONE tag the Markdown path does emit (the ``<u>``
    # underline wrapper) was destroyed by the blanket HTML-escape this path used
    # to apply to the whole rendered cell (``&lt;u&gt;``). Dogfood round 2 found
    # all four in a single human-authored merged cell (T14) with the tree path
    # fully intact — a silent, read-side-only fidelity loss.
    #
    # The rules this serializer holds to:
    #
    # * **Tags, not markers.** Emphasis → ``<strong>``/``<em>``/``<s>``/``<u>``;
    #   lists → ``<ul>``/``<ol>`` + ``<li>`` (nested lists nest INSIDE the parent
    #   ``<li>``, which is how HTML expresses depth — no indent tabs); a divider →
    #   ``<hr/>``; multiple blocks → real block separation.
    # * **Escaping is HTML-ENTITY escaping of TEXT ONLY** — and only where a
    #   character is ambiguous in HTML (``&`` ``<`` ``>``, plus ``"`` inside an
    #   attribute). A Markdown metachar (``**``, ``#``, ``_``, a backtick) is inert
    #   in HTML and is left completely alone; a backslash is NEVER inserted
    #   (LD-130's pin — in a ``<td>`` a backslash is visible text, not an escape).
    # * **Colour stays dropped** (LD-042's settled capture-only doctrine): the
    #   model carries ``text_color``/``background_color`` so a future writer can
    #   round-trip them; nothing here emits a style, a ``bgcolor`` or a ``<mark>``.
    # * **No literal newline ever leaves a cell.** A blank line TERMINATES a
    #   CommonMark HTML block, which would tear the ``<table>`` in half, so a hard
    #   break inside phrasing content becomes ``<br/>`` and a code block's line
    #   breaks become ``&#10;`` (a real newline to a browser, no newline in the
    #   source). Interior newlines from a NESTED ``<table>`` are safe (that emitter
    #   never produces a blank line) and are kept for readability.

    @staticmethod
    def _html_attr(value: str) -> str:
        """Escape ``value`` for use inside a double-quoted HTML attribute."""
        return (MarkdownRenderer._html_escape(value)
                .replace('"', "&quot;")
                .replace("\n", ""))

    @classmethod
    def _html_phrasing(cls, text: str) -> str:
        """Literal text as HTML phrasing content: entities + ``<br/>`` for a newline."""
        return cls._html_escape(text).replace("\n", "<br/>")

    def _html_link(self, url: str, inner: str) -> str:
        return f'<a href="{self._html_attr(url or "")}">{inner}</a>'

    # -- inline ---------------------------------------------------------------

    def _html_inline(self, nodes: List[Inline], linkify: bool = True) -> str:
        return "".join(self._html_inline_one(n, linkify) for n in (nodes or []))

    def _html_inline_one(self, n: Inline, linkify: bool = True) -> str:
        if isinstance(n, Text):
            return self._html_text(n.content, linkify)
        if isinstance(n, StyledText):
            return self._html_styled(n, linkify)
        if isinstance(n, MentionUser):
            return self._html_phrasing(f"@{n.user_id}")
        if isinstance(n, MentionDoc):
            return self._html_link(n.url, self._html_phrasing(n.title))
        if isinstance(n, InlineEquation):
            return self._html_phrasing(f"${n.content}$")
        if isinstance(n, UnsupportedInline):
            return self._html_phrasing(f"[unsupported inline: {n.variant}]")
        if isinstance(n, RawInline):
            # Already-formatted markup — the verbatim-inline passthrough, exactly
            # as on the Markdown path.
            return n.markup
        raise TypeError(
            f"MarkdownRenderer has no HTML-cell serializer for inline node "
            f"{type(n).__name__}"
        )

    def _html_text(self, s: str, linkify: bool = True) -> str:
        """Literal text, entity-escaped, with the always-on bare-URL pass (LD-054).

        On the Markdown path that pass emits ``[url](url)`` — inert inside a
        ``<td>``. Here it emits a real ``<a>``, with the same trailing-sentence-
        punctuation peel so a final ``.``/``)``/``,`` stays outside the link.
        """
        if not linkify:
            return self._html_phrasing(s)
        matches = list(_BARE_URL_RE.finditer(s))
        if not matches:
            return self._html_phrasing(s)
        out: List[str] = []
        pos = 0
        for m in matches:
            out.append(self._html_phrasing(s[pos:m.start()]))
            url = m.group(0)
            core = url.rstrip(_URL_TRAILING_PUNCT)
            out.append(self._html_link(core, self._html_phrasing(core)))
            out.append(self._html_phrasing(url[len(core):]))
            pos = m.end()
        out.append(self._html_phrasing(s[pos:]))
        return "".join(out)

    def _html_styled(self, n: StyledText, linkify: bool = True) -> str:
        # Composition order mirrors :meth:`_styled` exactly: the emphasis stack
        # (bold outermost), then inline code around it, then the link outermost.
        # A run already carrying a link is NOT auto-linkified (no double link);
        # inline-code content is verbatim, so it is not linkified either.
        verbatim = n.inline_code or n.link_url is not None
        body = (self._html_phrasing(n.content) if verbatim
                else self._html_text(n.content, linkify))
        for attr, tag in _HTML_STYLE_TAGS:
            if getattr(n, attr):
                body = f"<{tag}>{body}</{tag}>"
        if n.inline_code:
            body = f"<code>{body}</code>"
        if n.link_url is not None:
            body = self._html_link(n.link_url, body)
        # n.text_color / n.background_color are DELIBERATELY not consulted —
        # capture-only doctrine (LD-042); LD-144 AC3 pins their absence.
        return body

    # -- blocks ---------------------------------------------------------------

    def _html_cell_content(self, cell) -> Tuple[str, bool]:
        """One cell's HTML, plus whether it is **phrasing-only**.

        ``cell`` is a :class:`TableCellNode` on the reader path; a bare
        already-rendered ``str`` on the renderer-direct unit path (which has no
        node tree to walk, so it stays verbatim TEXT — entity-escaped, never
        backslash-escaped, never re-read as structure).

        The second element is what :meth:`_html_merged_cell` joins on: ``True``
        means the HTML is bare phrasing content (no block-level wrapper), which is
        the ``_sole_paragraph`` case; ``False`` means the cell needed real block
        markup. The distinction already existed here — LD-529 only names it so a
        second cell's content can be appended without inventing a new taxonomy.
        """
        if isinstance(cell, str):
            return self._html_escape(cell.replace("\n", " ").strip()), True
        prev = self._cell_mode
        # Kept for the Markdown FALLBACK below (a block with no HTML form of its
        # own): "html" mode is what keeps LD-130's escaper off inside a <td>.
        self._cell_mode = "html"
        try:
            children = cell.children if isinstance(cell, TableCellNode) else [cell]
            solo = self._sole_paragraph(children)
            if solo is not None:
                # The overwhelmingly common cell: ONE paragraph's worth of
                # content. Emit bare phrasing content with no <p> wrapper —
                # conventional for a table cell, and what keeps every
                # already-shipped merged-table golden (and the live canary doc's
                # own two merged tables) byte-identical through this change.
                return self._html_para_text(solo).strip(), True
            return self._html_blocks(children), False
        finally:
            self._cell_mode = prev

    def _html_merged_cell(self, cells, anchor_idx: int, claimed_idxs) -> str:
        """The anchor cell's own content plus the content of every position it
        covers (LD-529) — the body of ONE ``<td>``/``<th>``.

        **The serialization**, chosen from what this serializer already does and
        stated once here. Each contributing cell (the anchor, then each claimed
        position in row-major order) is serialized **independently** by
        :meth:`_html_cell_content`, so a covered cell's own structure — its list,
        its nested table — stays its own and is never folded into the anchor's.
        A cell that renders to nothing contributes **nothing at all**: no
        separator, no whitespace, which is why a merged table whose covered
        positions are empty is byte-identical through this change. (**How often
        real merged tables look like that is unmeasured** — one document's output
        was checked and did not move, which is one document's worth of evidence
        and no more.) The survivors are then joined:

        * **all phrasing-only → ``<br/>``.** The common case, and the compact one:
          a merged region reads as its anchor's text followed by the covered text
          on the next line, inside one cell.
        * **otherwise → concatenation, with each phrasing-only piece wrapped in
          ``<p>``.** Block markup cannot sit beside bare phrasing content without
          a wrapper, and ``<p>`` is what this serializer already emits for a
          paragraph that needs one (:meth:`_html_paragraph`).

        Neither join can introduce a **blank line**, which would terminate the
        CommonMark HTML block and tear the ``<table>`` in half (the law stated at
        the top of this section). Order is document order and therefore
        deterministic: two renders of one payload are byte-identical. With a
        single contributing cell — every unmerged cell, and every anchor whose
        covered positions are empty — the result is exactly what the anchor alone
        produced before.
        """
        pieces: List[Tuple[str, bool]] = []
        for i in (anchor_idx, *claimed_idxs):
            if i >= len(cells):
                continue
            html, phrasing = self._html_cell_content(cells[i])
            if html:
                pieces.append((html, phrasing))
        if not pieces:
            return ""
        if all(phrasing for _, phrasing in pieces):
            return "<br/>".join(html for html, _ in pieces)
        return "".join(html if not phrasing else f"<p>{html}</p>"
                       for html, phrasing in pieces)

    def _sole_paragraph(self, children: List[Node]):
        """The ONE content-bearing paragraph among ``children``, else ``None``.

        ``None`` means "this cell needs real block markup" — it holds nothing at
        all, two or more real paragraphs, or a block that is not a paragraph.

        Why this is decided on CONTENT-bearing blocks and not on ``len(children)``:
        the Lark UI leaves a trailing **empty** paragraph inside a human-authored
        cell, so a cell holding one line of text arrives with TWO type-2 children.
        Found live on the disposable canary doc (cell
        ``Example1ca40d776daa9e782589``: ``[text "Banana", text ""]``) — an
        ``len(children) == 1`` rule wrapped it in a pointless ``<p>`` and moved
        reader output on a document with no T14 defect in it at all. An empty
        paragraph is not content, and never was: the old collapse dropped it too.
        """
        found = None
        for node in children:
            if type(node) is TextNode:
                if not self._html_para_text(node).strip():
                    continue                      # a blank paragraph is not content
            elif type(node) is RawBlock and not node.markup:
                continue                          # the empty missing-block sentinel
            else:
                return None                       # any other block needs block markup
            if found is not None:
                return None                       # two real paragraphs → separate them
            found = node
        return found

    def _html_blocks(self, nodes: List[Node]) -> str:
        """A run of sibling blocks as HTML, folding consecutive list items into lists."""
        out: List[str] = []
        i, n = 0, len(nodes)
        while i < n:
            kind = type(nodes[i])
            tag = _HTML_LIST_TAG.get(kind)
            if tag is None:
                out.append(self._html_block(nodes[i]))
                i += 1
                continue
            # Group by EXACT type: a bullet run and a todo run both wrap in <ul>
            # but are two separate lists.
            j = i
            while j < n and type(nodes[j]) is kind:
                j += 1
            out.append(self._html_list(nodes[i:j], tag))
            i = j
        return "".join(out)

    def _html_list(self, items: List[Node], tag: str) -> str:
        attrs = ""
        if tag == "ol":
            # A cell's ordered run can begin mid-sequence (a non-ordered sibling
            # resets the handler's run counter), so carry the real first number
            # rather than silently renumbering from 1.
            start = getattr(items[0], "order", 1)
            if isinstance(start, int) and start != 1:
                attrs = f' start="{start}"'
        body = "".join(self._html_list_item(it) for it in items)
        return f"<{tag}{attrs}>{body}</{tag}>"

    def _html_list_item(self, node: Node) -> str:
        box = ""
        if isinstance(node, TodoListItemNode):
            # The GFM task-list rendering: a real (disabled) checkbox, not the
            # literal "[x]"/"[ ]" text markers the Markdown path emits.
            state = " checked" if node.done else ""
            box = f'<input type="checkbox"{state} disabled/> '
        content = getattr(node, "content", None)
        text = "" if content is None else self._html_inline(content)
        # Depth is expressed by NESTING the sub-list inside this <li> — the
        # Markdown path's leading indent tabs have no meaning in HTML.
        return f"<li>{box}{text}{self._html_blocks(node.children)}</li>"

    def _html_block(self, node: Node) -> str:
        handler = self._html_cell_dispatch.get(type(node))
        if handler is None:
            return self._html_fallback(node)
        return handler(node)

    def _build_html_cell_dispatch(self):
        # Only the block kinds that have a genuine HTML form are registered; every
        # other block (a file/iframe/embedded-data marker, an equation block, …)
        # goes to _html_fallback. See that method for the residue this leaves.
        return {
            TextNode: self._html_paragraph,
            AgendaItemTitleNode: self._html_paragraph,
            DividerNode: self._html_divider,
            HeadingNode: self._html_heading,
            CodeNode: self._html_code,
            QuoteNode: self._html_quote,
            QuoteContainerNode: self._html_blockquote_children,
            CalloutNode: self._html_blockquote_children,
            ImageNode: self._html_image,
            TableNode: self._html_nested_table,
            TableCellNode: self._html_children,
            RawBlock: self._html_raw_block,
            GridColumnNode: self._html_nothing,
            GridNode: self._html_grid,
            ViewNode: self._html_children,
            UnknownBlockNode: self._html_children,
            AgendaNode: self._html_children,
            AgendaItemNode: self._html_children,
            AgendaItemContentNode: self._html_children,
            SourceSyncedNode: self._html_source_synced,
        }

    def _html_nothing(self, node: Node) -> str:
        return ""

    def _html_raw_block(self, node: RawBlock) -> str:
        # Verbatim block passthrough (the empty missing/unknown-block sentinel).
        return node.markup

    def _html_children(self, node: Node) -> str:
        # Transparent wrappers — view, the unknown-block fallback, the agenda
        # wrappers, and a nested table_cell: their children, no markup of their own.
        return self._html_blocks(node.children)

    def _html_grid(self, node: GridNode) -> str:
        return "".join(self._html_blocks(column) for column in node.columns)

    def _html_source_synced(self, node: SourceSyncedNode) -> str:
        return self._html_paragraph(node) + self._html_blocks(node.children)

    def _html_para_text(self, node: Node) -> str:
        """A paragraph-ish node's OWN inline run as HTML (``""`` when it has none).

        The single reader of ``content`` for both the emptiness DECISION
        (:meth:`_sole_paragraph`) and the emission (:meth:`_html_paragraph`), so
        the two can never disagree about whether a paragraph is content.
        """
        content = getattr(node, "content", None)
        return "" if content is None else self._html_inline(content)

    def _html_paragraph(self, node: Node) -> str:
        text = self._html_para_text(node)
        # A blank (or whitespace-only) paragraph emits nothing — no dangling
        # <p></p>, the same vanish the Markdown path produced once its newline was
        # collapsed, and the SAME test _sole_paragraph applies.
        return f"<p>{text}</p>" if text.strip() else ""

    def _html_divider(self, node: DividerNode) -> str:
        return "<hr/>"

    def _html_heading(self, node: HeadingNode) -> str:
        content = node.content
        text = "" if content is None else self._html_inline(content)
        if not text:
            head = ""
        elif node.level <= MAX_HEADING_LEVEL:
            head = f"<h{node.level}>{text}</h{node.level}>"
        else:
            # HTML has no <h7>. A Lark heading7-9 degrades to an emphasized paragraph
            # rather than an invented tag. LD-145 settled the MARKDOWN path's own answer
            # (cap the marker at ``######``) and this seam deliberately KEEPS its different
            # one: a heading inside a <td> is no consumer's outline entry, so there is no
            # structural role a capped <h6> would rescue — only a level the tree does not
            # have would be asserted. Both halves share the ceiling constant above and the
            # rule "never invent a marker outside the dialect"; see its comment for the
            # full doctrine, and tests/test_heading_level_cap.py § "The cross-seam pair"
            # for the paired assertion.
            head = f"<p><strong>{text}</strong></p>"
        return head + self._html_blocks(node.children)

    def _html_code(self, node: CodeNode) -> str:
        # Code content is verbatim: no linkify, no escaping beyond entities. Line
        # breaks become "&#10;" — a real newline to a browser, but no literal
        # newline in the source (a blank line would terminate the HTML block and
        # tear the <table> apart).
        body = self._html_inline(node.content, linkify=False).replace("<br/>", "&#10;")
        return f"<pre><code>{body}</code></pre>"

    def _html_quote(self, node: QuoteNode) -> str:
        text = self._html_inline(node.content)
        return f"<blockquote>{text}</blockquote>" if text else ""

    def _html_blockquote_children(self, node: Node) -> str:
        body = self._html_blocks(node.children)
        return f"<blockquote>{body}</blockquote>" if body else ""

    def _html_image(self, node: ImageNode) -> str:
        if node.caption is None:
            return ""
        if node.token:
            # The token stays the src so the T1 pipeline's token→local-link
            # substitution (read/download.py) still rewrites it.
            return (f'<img src="{self._html_attr(node.token)}" '
                    f'alt="{self._html_attr(node.caption)}"/>')
        marker = "[Image: missing token]"
        if node.caption:
            marker += f" {node.caption}"
        return f"<p>{self._html_phrasing(marker)}</p>"

    def _html_nested_table(self, node: TableNode) -> str:
        # A table nested inside a merged cell: a GFM pipe table would be inert
        # here, so nest a real <table> whatever the inner table's merge state.
        if not node.cells:
            return ""
        return self._table_html(node, node.col_size or 1).strip()

    def _html_fallback(self, node: Node) -> str:
        """A block with no HTML form of its own: its Markdown, escaped, as a paragraph.

        The residue this leaves, stated plainly: the marker-emitting families (a
        file attachment, an iframe, the embedded Base/Sheet placeholders, a
        reference-synced notice, an equation block) carry ``**``/backticks inside
        their FIXED marker text, so inside a merged cell those markers still show
        literally — exactly as they did before LD-144, and unchanged by it. The
        cell content an author actually writes (text, emphasis, links, lists,
        dividers, headings, code, quotes, callouts, images, nested tables) all has
        a real HTML form above.
        """
        rendered = self.render(node, 0)
        if not rendered.strip():
            return ""
        return f"<p>{self._html_phrasing(rendered.strip())}</p>"

    # -- container-ish (types 19 / 34 / 24) -----------------------------------
    #
    # Each carries child NODES (callout/quote_container flipped in R-S2, grid in
    # R-S4) and descends them via render(child, depth): callout + quote_container
    # at depth 0 (recurse-at-0), grid at its OWN depth (own-depth recurser).
    # Byte-identical to the prior blocks/callout.py + blocks/container.py string
    # handlers.

    def _callout(self, node: CalloutNode, depth: int = 0) -> str:
        # Callout: concatenate the child strings, then prefix EVERY line (blank
        # lines included) with "> ". A trailing newline yields a final empty
        # split element; drop it so we don't emit a dangling "> " line, then the
        # per-line join restores the single trailing newline. Emits NO emoji
        # (the node carries none — LD-010's pinned correction). Children are child
        # NODES (R-S2 flip) rendered at depth 0 — reproducing the prior
        # already-rendered child strings (depth 0) before concatenation.
        content = "".join(self.render(child, 0) for child in node.children)
        if not content:
            return ""
        lines = content.split("\n")
        if content.endswith("\n"):
            lines = lines[:-1]
        return "".join(f"> {line}\n" for line in lines)

    def _quote_container(self, node: QuoteContainerNode, depth: int = 0) -> str:
        # Quote container: render each child NODE (R-S2 flip) at depth 0, then
        # process that string independently — rstrip its trailing newlines, then
        # prefix each remaining line with "> " (a blank interior line becomes a
        # bare ">"). The per-child rstrip is load-bearing (see QuoteContainerNode
        # docstring); rendering per child preserves it exactly.
        buf = []
        for child in node.children:
            rendered = self.render(child, 0)
            buf.extend(self._blockquote_lines(rendered.rstrip("\n").split("\n")))
        return "\n".join(buf) + "\n\n" if buf else ""

    def _view(self, node: ViewNode, depth: int = 0) -> str:
        # View (type 33) is a TRANSPARENT wrapper and an own-depth recurser
        # (LD-040): emit each child's own serialization at the view's own depth,
        # concatenated verbatim, with NO markup of its own — the wrapper is
        # invisible. Views are NOT homogeneous, so each child is rendered by its
        # own serializer (a file → the 📎 marker, a bitable/sheet → its own
        # 📊 embedded-data placeholder marker, …). Threading `depth` lets a view nested under a list
        # carry that indent through to its children, exactly like _grid.
        return self._transparent(node, depth)

    def _unknown_block(self, node: UnknownBlockNode, depth: int = 0) -> str:
        # Transparent fallback for an UNREGISTERED type (LD-045, Decision e): emit
        # each child's own serialization at the unknown block's own depth,
        # concatenated verbatim, with NO markup of its own — the view/grid
        # own-depth-recurser precedent. A leaf unknown (no children) renders "" (so
        # a genuinely-unknown leaf still contributes nothing), while an unknown
        # CONTAINER surfaces its descendants instead of dropping the whole subtree.
        return self._transparent(node, depth)

    # -- agenda family (types 44 / 45 / 46 / 47) ------------------------------
    #
    # Registered (known) agenda handlers (LD-046, Decision d) — NOT the
    # unknown-type fallback. 44/45/47 are TRANSPARENT structural wrappers (the
    # view/grid own-depth-recurser precedent): emit each child's own
    # serialization at the wrapper's own depth, no markup of the wrapper itself.
    # 46 (agenda_item_title) carries its text in its OWN elements, so it renders
    # the inline run + a trailing newline (nothing when empty).

    def _transparent(self, node: Node, depth: int = 0) -> str:
        # Shared serializer for every TRANSPARENT wrapper — view (type 33), the
        # unknown-block fallback, and the three agenda wrappers (44/45/47):
        # concatenate each child's own serialization at the wrapper's OWN depth
        # with NO markup of its own (the own-depth-recurser precedent). Threading
        # `depth` lets a wrapper nested under a list carry that indent through to
        # its children, exactly like _grid. `children` is the only field these
        # nodes contribute to the emitted string.
        return "".join(self.render(child, depth) for child in node.children)

    def _agenda_item_title(self, node: AgendaItemTitleNode, depth: int = 0) -> str:
        # The item title (46): render its OWN inline elements + a single trailing
        # newline WHEN non-empty; an empty elements list (or absent payload)
        # emits nothing — no dangling marker (the page-title `if title` gate,
        # applied per item). `align` was dropped by the handler (visual).
        text = self.render_inline(node.content, block_context=True)
        return f"{text}\n" if text else ""

    def _grid(self, node: GridNode, depth: int = 0) -> str:
        # Grid (own-depth recurser, R-S4 flip): each column carries its child
        # NODES; render them at the grid's own depth (so a grid nested under a
        # list threads that indent through) and join a column's children
        # verbatim, then join the columns with a blank line. A childless column
        # was omitted by the handler, so no stray "\n\n" separator leaks —
        # byte-identical to the prior flattened-string carriage.
        return "\n\n".join(
            "".join(self.render(child, depth) for child in column)
            for column in node.columns
        )

    # -- media / file / diagram (types 27 / 43 / 40 / 23 / 25) ----------------
    #
    # Emission-only family (LD-029). The renderer emits the token/name/source the
    # node carries; the asset DOWNLOAD + token->local-link substitution stays in
    # the T1 pipeline (read/download.py), which reads parser.img_tokens /
    # parser.board_tokens queued by the handlers at construction time. Byte-
    # identical to the prior string handlers in media.py / file.py / diagram.py.

    def _grid_column(self, node: GridColumnNode, depth: int = 0) -> str:
        # Transparent safety-net: a grid_column reached out of context emits
        # nothing (its content is rendered by the parent Grid handler).
        return ""

    def _iframe(self, node: IframeNode, depth: int = 0) -> str:
        # Iframe (type 26, LD-047): emit the (already percent-decoded) url as a
        # Markdown link `[url](url)`. A missing/empty url (absent iframe/component
        # or an empty url string — url is None here) emits a visible
        # `[Iframe: missing url]` marker rather than a silent drop or a broken
        # empty link (the _image missing-token precedent). `iframe_type` is
        # captured on the node but has no portable Markdown form — dropped here
        # (consumed-into-model, dropped-at-render).
        if not node.url:
            return "[Iframe: missing url]\n"
        return f"[{node.url}]({node.url})\n"

    def _image(self, node: ImageNode, depth: int = 0) -> str:
        # caption None models the SDK image attr being absent (legacy emitted
        # ""); a present image always carries a string caption ("" when unset).
        if node.caption is None:
            return ""
        if node.token:
            return f"![{node.caption}]({node.token})\n"
        # Missing token: a visible marker (never a silent drop), with the caption
        # appended only when non-empty.
        marker = "[Image: missing token]"
        if node.caption:
            marker += f" {node.caption}"
        return f"{marker}\n"

    def _board(self, node: BoardNode, depth: int = 0) -> str:
        if node.token:
            return f"![Whiteboard]({node.token})\n"
        return ""

    def _add_ons(self, node: AddOnsNode, depth: int = 0) -> str:
        # Unsupported add-on: the marker id is already 'unknown'-defaulted by the
        # handler (never None here).
        if node.unsupported_component_id is not None:
            return f"[Unsupported Add-On block: {node.unsupported_component_id}]\n"
        # Mermaid: a falsy source (None / "") emits nothing; otherwise fence the
        # stripped source. The falsy-check mirrors the legacy `if not
        # mermaid_source: return ""` guard BEFORE the strip, so a whitespace-only
        # source still emits an (empty-bodied) fence — byte-identical.
        if not node.mermaid_source:
            return ""
        return f"```mermaid\n{node.mermaid_source.strip()}\n```\n"

    def _file(self, node: FileNode, depth: int = 0) -> str:
        # name None models the SDK file attr being absent (legacy emitted "").
        if node.name is None:
            return ""
        if node.token:
            return f"📎 **File Attachment:** {node.name} (token: `{node.token}`)\n"
        return f"📎 **File Attachment:** {node.name}\n"

    # -- synced (types 49 / 50) -----------------------------------------------
    #
    # source_synced (49): emit the block's OWN inline run, then a trailing
    # newline ONLY when that run is non-empty (the legacy has_text gate — a
    # present-but-empty elements list emits no newline), then each child NODE's
    # serialization at source_synced's own depth (R-S4 flip; source_synced
    # DESCENDS into its children, intentional). reference_synced (50): a traceable placeholder naming the
    # source ids; a None source_doc models an absent payload and emits nothing.
    # Byte-identical to the prior string handlers in blocks/synced.py.

    def _source_synced(self, node: SourceSyncedNode, depth: int = 0) -> str:
        # source_synced is an OWN-DEPTH recurser (R-S4 flip): its child NODES
        # render at the same depth source_synced itself was rendered at, so a
        # source_synced nested under a list threads that indent through to its
        # children — reproducing the prior already-rendered child strings at the
        # block's own depth (parse-time indent_level == render-time depth).
        text = self.render_inline(node.content, block_context=True)
        buf = []
        if text:
            buf.append(text)
            buf.append("\n")
        buf.extend(self.render(child, depth) for child in node.children)
        return "".join(buf)

    def _reference_synced(self, node: ReferenceSyncedNode, depth: int = 0) -> str:
        if node.source_doc is None:
            return ""
        return (
            f"> 🔗 **Synced content** referenced from document `{node.source_doc}` "
            f"(block `{node.source_block}`) — not fetched. The source document must grant "
            f"this integration read access for its content to be pulled.\n"
        )

    # -- embedded data (types 18 / 30 / 53) -----------------------------------
    #
    # Embedded Base (bitable 18) / Sheet (30) / Base-as-named-view
    # (reference_base 53). Each emits a traceable marker naming the block + its
    # id(s) (the reference_synced / file-attachment precedent — never a silent
    # drop). The records / cells / views live in a SEPARATE Base or Sheet
    # document; deep read of those contents is out of scope (a strategic descope). A
    # None token models an absent payload and emits nothing.
    # The 18 and 53 markers name each other (embedding a base = 18; switching it
    # to a named view = 53) so a consumer/maintainer understands both (AC2). The
    # 30 marker is token-only — its row/column dims arrive null.

    def _bitable(self, node: BitableNode, depth: int = 0) -> str:
        # Opt-in deep-read (LD-250), the type-30 pass-through replayed: when the handler
        # resolved the referenced table it stored the rendered GFM table (with its own
        # trailing newline) here — emit it verbatim in place of the marker. On the DEFAULT
        # path this is None, so the traceable placeholder below is byte-identical to today.
        if node.deep_read_markdown is not None:
            return node.deep_read_markdown
        if node.token is None:
            return ""
        return (
            f"> 📊 **Embedded Base** (bitable) — not fetched. token: `{node.token}`. "
            f"Contents (records, views, formulas) live in a separate Base document; "
            f"deep read is out of scope. (Switching an embedded base to a named view "
            f"makes it a reference_base — type 53 — instead.)\n"
        )

    def _sheet(self, node: SheetNode, depth: int = 0) -> str:
        # Opt-in deep-read (LD-105): when the handler resolved the referenced tab
        # it stored the rendered GFM table (with its own trailing newline) here —
        # emit it verbatim in place of the marker. On the DEFAULT path this is None,
        # so the traceable placeholder below is byte-identical to today (D8).
        if node.deep_read_markdown is not None:
            return node.deep_read_markdown
        if node.token is None:
            return ""
        return (
            f"> 📊 **Embedded Sheet** — not fetched. token: `{node.token}`. "
            f"The spreadsheet's cells live in a separate Sheet document; deep read is "
            f"out of scope.\n"
        )

    def _reference_base(self, node: ReferenceBaseNode, depth: int = 0) -> str:
        # The SAME opt-in deep-read pass-through as _bitable: one bridge feeds both embed
        # types, so both emit its table in place of their own marker (LD-250).
        if node.deep_read_markdown is not None:
            return node.deep_read_markdown
        if node.token is None:
            return ""
        return (
            f"> 📊 **Embedded Base — named view** (reference_base) — not fetched. "
            f"token: `{node.token}`, view: `{node.view_id}`. A base switched to a named "
            f"view (distinct from an embedded Base — type 18; consumers hit both "
            f"interchangeably).\n"
        )
