"""larkdocio.write.compose — Markdown fragment → typed creatable content
(LD-136).

The **authoring** entry point. :func:`compose` compiles a Markdown fragment into the
ordered typed :class:`~larkdocio.write.model.NewBlock` content an
:class:`~larkdocio.write.model.InsertRequest` carries; :func:`compose_insert` is the thin
convenience that pairs that content with an anchor + position. It is **pure**: no client,
no credential, no transport, no socket — it produces *requests*, and the gated
``dry_run`` → :class:`~larkdocio.write.preview.Plan` → ``apply`` chain is still the only
path anything reaches Lark by.

**The dialect is exactly what our own reader emits (D4).** Not "Markdown" in the
abstract — the GFM subset ``larkdocio``'s reader produces, *including the LD-130 escaping
rules read in reverse*: an escaped metachar (``\\#``, ``\\-``, ``\\*\\*``, ``1\\.``) is
**literal text**, never structure. That symmetry is the whole point, and it is what makes
the binding round-trip property provable:

    the reader's Markdown for blocks composed from ``X`` **is** ``X``
    (or ``X``'s documented normalization), and composing *that* is a fixed point.

**Why this module parses with ``markdown-it-py`` instead of hand-rolling.** The dialect IS
CommonMark + GFM tables + strikethrough, and ``markdown-it-py`` is the reference
implementation the reader's own escaping tests already measure against
(``tests/test_md_metachar_escaping.py``). A first-party parser would be a *second*
definition of the dialect — the round-trip property would then only prove the two
hand-rolled halves agree with each other — and would have to reimplement CommonMark's
escape table to get AC2 right. So ``markdown-it-py`` is a **runtime** dependency (the
architect's recorded call, overriding an earlier "no new dependency" line): pure Python, one
transitive dep, and the same parser the tests reference.

**What composes** — every kind S1/S2 made creatable:

=========================  ==================================================
Markdown                   composes to
=========================  ==================================================
``# H`` … ``###### H``     ``NewBlock.heading(1..6, text)`` (setext too)
a paragraph                ``NewBlock.paragraph(text)`` (soft break ⇒ ``\\n``)
``- x`` / ``* x`` / ``+``  ``NewBlock.bullet(text, children=…)``
``1. x`` / ``1) x``        ``NewBlock.ordered(text, children=…)``
``- [ ] x`` / ``- [x] x``  ``NewBlock.todo(text, done=…, children=…)``
```` ```lang ````          ``NewBlock.code(text, language=lang)``
``> x``                    ``NewBlock.quote(text)``
a GFM pipe table           ``NewBlock.table(rows, header_row=True)``
```` ```mermaid ````       ``NewBlock.mermaid(source)`` — a diagram (type 40)
=========================  ==================================================

**What refuses** — :data:`NOT_EXPRESSIBLE_CONSTRUCTS` is the closed set, and the shipped
lossiness table in ``write/README.md`` § "The composable Markdown dialect" is guarded
against it. A construct outside the dialect is **refused with the construct and its
1-based line named** (:meth:`Refusal.not_in_dialect`, carried by
:class:`~larkdocio.write.model.RefusedError`) — **never silently dropped, never
flattened, never approximated**. A caught construction refusal (a documented cap, an
impossible block) is re-raised the same way, so **the only error out of this module is a
typed refusal**.

**Whose token is it?** A fence's info string is not always a code language, and the three
cases are deliberately kept apart:

* ```` ```mermaid ```` is a **diagram**. The reader emits that fence for an ``add_ons`` block
  (docx type 40), and it now **composes back into one**
  (:meth:`~larkdocio.write.model.NewBlock.mermaid`) — so feeding a document containing a
  diagram straight back to :func:`compose` works, where it used to refuse.
  :data:`MERMAID_FENCE_TOKEN` is the shared word.
* a token the **caller** invented is ``unknown-code-language`` — Lark has no enum for it, and
  picking a supported one is real advice, unchanged.
* a token the **reader itself** emits for a block with no creatable form here is
  ``non-creatable-projection``: the fence is a **projection** of that block, not a code block,
  so no language choice could author it back and blaming the caller's token would be advice
  that cannot succeed. :data:`READER_PROJECTION_FENCES` is that (guarded) set — **empty
  today**, because the diagram fence that was its one row became authorable in the same change
  that made it creatable, exactly as that table's standing note required. The invariant it
  serves is unchanged: every fence token the reader emits either composes or has a row there.

One trap worth naming: **GFM silently repairs a ragged table** — it pads a short row and
*truncates* a long one — so the token stream reports every row at the header's width and a
ragged grid would compose with invented or dropped cells. :func:`compose` therefore counts
each source row's pipe-delimited cells itself (an escape-aware scan) and refuses the
``merged-table`` construct, because a ragged grid is the shape a **merged** table produces
and Markdown has no span syntax (LD-135).
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from larkdocio.langs import MD_LANG_TO_DOCX_CODE, supported_code_languages
from larkdocio.write.model import (
    MAX_CHILDREN_PER_CALL,
    MAX_NEST_DEPTH,
    InsertPosition,
    InsertRequest,
    NarrativeAnchor,
    NewBlock,
    Refusal,
    RefusalReason,
    RefusedError,
    TextSpan,
)

#: Every construct the compiler can refuse → **why** it is inexpressible and what to do
#: instead. The closed, documented set (AC4/AC5): the shipped lossiness
#: table in ``write/README.md`` is drift-guarded against these keys, so a construct added
#: here without its row reddens the suite.
NOT_EXPRESSIBLE_CONSTRUCTS: Dict[str, str] = {
    # SUPERSEDED IN PART: the REASON below is the original and is unchanged — this compiler
    # has no bytes. Only the CONCLUSION moved. It used to end "or wait for the media rung";
    # that rung shipped, so it now names the op instead of telling a caller to wait.
    "image": (
        "an image is not creatable from Markdown: a ![](…) carries a path or a token, and "
        "this compiler has no bytes and makes no network call, so there is nothing to "
        "upload — author the prose here and put the picture in with "
        "larkdocio.write.media.put_image_in_document, which creates the image block, "
        "uploads the bytes bound to it and binds them"
    ),
    # SUPERSEDED IN PART (LD-434, then LD-619): the REASON below is the original and is
    # unchanged — an inline link is a STYLED run, and this COMPILER creates unstyled runs.
    # Only the CONCLUSION has moved, twice. LD-434: an anchored link CAN be authored, as a
    # TYPED shape, so the refusal names it instead of leaving a caller stuck. LD-619: inside
    # a TABLE CELL the dialect itself now composes one, because Lark was measured to accept
    # and store the run there on both write routes (measured) and the reader already projects it
    # back as [label](url) — so the round-trip property this refusal protects is what ADMITS
    # that one position rather than what forbids it. The dialect stays closed everywhere else
    # on purpose, and the [url](url) autolink special case below is unchanged.
    "link": (
        "an inline link is a STYLED run and this Markdown compiler creates unstyled runs — "
        "with ONE position excepted: inside a TABLE CELL a [label](url) does compose, and "
        "reads back as the same Markdown. Everywhere else, author the URL as plain text (the "
        "reader auto-links a bare http(s) URL on the way back out, so [url](url) is the one "
        "shape that does compose), or author the anchor as the TYPED shape instead: "
        "NewBlock.rich_paragraph with a TextSpan carrying link_url, which creates a run "
        "whose anchor text is not the URL"
    ),
    "bold": (
        "bold is a STYLED run and created runs are unstyled in this rung — author the "
        "plain text, or escape the markers (\\*\\*x\\*\\*) to keep them literal"
    ),
    "italic": (
        "italic is a STYLED run and created runs are unstyled in this rung — author the "
        "plain text, or escape the markers to keep them literal"
    ),
    "strikethrough": (
        "strikethrough is a STYLED run and created runs are unstyled in this rung — "
        "author the plain text, or escape the markers to keep them literal"
    ),
    "inline-code": (
        "an inline code span is a STYLED run and created runs are unstyled in this rung — "
        "author a fenced code block, or escape the backticks to keep them literal"
    ),
    "html": (
        "raw HTML has no creatable block (the reader emits HTML only for what Markdown "
        "cannot express: an underline run, a merged table) — author the Markdown "
        "equivalent instead. Prose in angle brackets counts as HTML here (\"Lorem <ipsum "
        "dolor>\" is a well-formed open tag), so escape the bracket (\\<) or write &lt;"
    ),
    "merged-table": (
        "a merged (colspan/rowspan) table is not expressible — Markdown has no span "
        "syntax, so an authored table is always a plain rectangular grid (give every row "
        "the header's cell count; use an empty string for a blank cell). The grid is never "
        "padded or truncated to fit"
    ),
    "thematic-break": (
        "a divider (docx block type 22) is not creatable in this rung — drop the rule, or "
        "escape it (\\-\\-\\-) to author it as literal text"
    ),
    "indented-code-block": (
        "an indented code block is outside the dialect (the reader always emits a FENCED "
        "block) — use a ``` fence with its language token"
    ),
    "hard-break": (
        "a hard line break has no docx representation (the reader never emits one) — use a "
        "soft break: a plain newline inside the paragraph"
    ),
    "footnote": (
        "a footnote is not part of the dialect and has no creatable block — author the "
        "note as its own paragraph or a quote"
    ),
    "list-item-block-child": (
        "a list item carries its own text plus NESTED LIST ITEMS only; any other block "
        "child (a second paragraph, a fence, a table, a quote) renders at column 0 — i.e. "
        "as a SIBLING in Markdown — so author it as a sibling block. It is never silently "
        "relocated"
    ),
    "blockquote-block-child": (
        "the creatable quote block (docx type 15) carries ONE text run and a quote "
        "CONTAINER (type 34) is not creatable, so a blockquote holding a second paragraph, "
        "a nested quote or a fence is not expressible — author one quote per run of lines"
    ),
    "empty-list-item": (
        "a list item is a marker plus content, and a bare marker carries nothing — give "
        "the item text (or drop the item). A leading # or > is the usual cause: it opens a "
        "NEW block inside the item and leaves the marker itself empty, so escape it (\\#) "
        "to keep it literal"
    ),
    "empty-heading": (
        "a heading is a marker plus content, and a bare marker carries nothing — give the "
        "heading text (or drop the heading)"
    ),
    "empty-quote": (
        "a quote is a marker plus content, and a bare marker carries nothing — give the "
        "quote text (or drop the quote)"
    ),
    "empty-mermaid": (
        "a ```mermaid fence with no diagram source would author a block that renders as "
        "NOTHING AT ALL — Lark accepts an empty diagram and stores it, and the reader emits "
        "no fence and no marker for one, so it would be an invisible block rather than a "
        "visible mistake — give the fence its Mermaid source (or drop the fence)"
    ),
    "code-fence-info": (
        "a fence info string carrying more than the bare language token is not expressible "
        "— Lark stores a code block's language as a single enum, so drop the extra "
        "attributes"
    ),
    "unknown-code-language": (
        "Lark has no language enum for that fence token — use one of "
        "larkdocio.langs.supported_code_languages(), or a bare ``` fence (it is never "
        "silently downgraded)"
    ),
    "non-creatable-projection": (
        "that fence is a PROJECTION this library's own reader wrote, not a code block: the "
        "block behind it (named below) has no creatable form here today, so the fence token "
        "is not a language and no supported token would author the block back — the token is "
        "not the caller's mistake. Drop the fence and leave that block to the editor, or "
        "keep the text under a bare ``` fence to author it verbatim as a code block; "
        "everything around it composes"
    ),
    "nesting-too-deep": (
        "the authored list nests deeper than larkdocio's documented cap (each level costs "
        "its own throttled create-children call) — split the authoring into batches; a "
        "deeper tree is never silently flattened"
    ),
    "block": (
        "that block construct has no creatable docx block in this rung — see the "
        "composable-dialect table in write/README.md for what does compose"
    ),
    "inline": (
        "that inline construct has no creatable representation in this rung (created runs "
        "are plain, unstyled text) — author the plain text instead"
    ),
    "table-cap": (
        "the authored table is larger than larkdocio's own 500-cell authoring cap, which is "
        "anchored on a measured platform envelope (Lark takes a 499-cell table subtree in "
        "one call and refuses the next) and is NOT one of Lark's own ceilings — those are "
        "100 columns (1770010 \"too many table column\") and no row cap at all — so split "
        "the authored grid into tables of 500 cells or fewer and author them one after "
        "another; it is never truncated"
    ),
    "table-column-cap": (
        "the authored table is wider than the measured column ceiling LARK itself enforces "
        "(it refuses the 101st column, 1770010 \"too many table column\") — split the table "
        "into two narrower ones; it is never truncated. Deliberately distinct from "
        "table-cap, which is larkdocio's own cost-based cell cap, and there is no row "
        "equivalent of either: a table's HEIGHT is not limited this way"
    ),
}

#: The fence token the reader emits for a **diagram add-on** (docx block type 40), and the
#: token this module compiles back into one.
#:
#: The renderer writes the fence and this module reads it, so the two must agree on the word;
#: ``tests/test_non_creatable_projection_refusal.py`` asserts the renderer's own emission
#: equals this constant, which is what keeps the pairing from rotting.
MERMAID_FENCE_TOKEN = "mermaid"

#: Fence tokens **this library's own reader emits** as the PROJECTION of a block it does not
#: create today — the token is not a code language and the fence is not a code block, so the
#: caller's choice of token is not the problem when one comes back in. Each value says what
#: the underlying block actually is, so the refusal can name the real cause instead of
#: advising a token swap that cannot succeed.
#:
#: **EMPTY today, and that is the mechanism working rather than the mechanism gone.** Its one
#: row was ``mermaid``, carrying the standing note that *a token that later becomes authorable
#: leaves this table in the same change that makes it creatable*. That change is this one: a
#: diagram is now a creatable kind (:meth:`~larkdocio.write.model.NewBlock.mermaid`), so the
#: reader's ```` ```mermaid ```` fence **composes** and there is nothing left to refuse about
#: it. The reader emits exactly two fence forms — a code block's language token and this one —
#: so the table is legitimately empty, and the invariant behind it is unchanged and still
#: guarded: **every fence token the reader emits either composes or has a row here.** Add a
#: row the moment a new projection fence appears; the refusal path below is fully exercised in
#: the guard so it will work on the day one does.
READER_PROJECTION_FENCES: Dict[str, str] = {}

#: The reference parser, configured to **exactly** the dialect the reader emits: CommonMark
#: plus the two GFM extensions the renderer produces (pipe ``table``s and ``~~strike~~``).
#: The same configuration ``tests/test_md_metachar_escaping.py`` measures the reader's
#: escaping against — one definition of the dialect, not two.
_DIALECT_PRESET = "commonmark"
_DIALECT_EXTENSIONS = ("table", "strikethrough")

#: The parser's own nesting limit, **derived from larkdocio's documented depth cap** so the
#: cap is the only ceiling a consumer can hit.
#:
#: This is load-bearing, not tidiness. ``markdown-it``'s default ``maxNesting`` (20) is
#: reached at roughly ten list levels — two per level — and past it the parser **silently
#: drops** the over-deep item's inline content (verified: a ten-level tab-indented list
#: comes back with the tenth item EMPTY). Composing that would author an empty block, i.e. a
#: silent content drop, which is exactly what the authoring doctrine forbids. Deriving the
#: limit from :data:`~larkdocio.write.model.MAX_NEST_DEPTH` (with headroom, so an
#: over-deep fragment still parses *fully* and is refused by **our** cap naming itself)
#: keeps the failure mode a typed refusal instead of quiet data loss.
_MAX_NESTING = 4 * (MAX_NEST_DEPTH + 2)

#: Inline node types that are **not** structure: plain text and the newline forms.
_TEXT_NODE = "text"
_SOFT_BREAK = "softbreak"

#: The three checkbox prefixes the reader emits for a todo item (``- [x] `` / ``- [ ] ``).
_TODO_PREFIXES = {"[ ] ": False, "[x] ": True, "[X] ": True}

#: markdown-it node type → the construct label a refusal names it by.
_INLINE_CONSTRUCTS = {
    "image": "image",
    "link": "link",
    "strong": "bold",
    "em": "italic",
    "s": "strikethrough",
    "code_inline": "inline-code",
    "html_inline": "html",
    "hardbreak": "hard-break",
}
_BLOCK_CONSTRUCTS = {
    "hr": "thematic-break",
    "code_block": "indented-code-block",
    "html_block": "html",
}

#: A footnote **definition** (``[^label]: the note``) — footnotes are an *extended*-Markdown
#: family, so CommonMark hands the line back as literal text rather than a construct, and a
#: definition composed as text would author a visibly broken footnote. It is therefore
#: refused by shape.
#:
#: Deliberately **only** the definition: a bare ``[^1]`` *reference* (and a regex character
#: class like ``[^a-z]`` in technical prose, which is the same shape) is literal text in GFM
#: too unless a definition exists, so it composes verbatim **and round-trips** — refusing it
#: would refuse content that provably survives, which is its own kind of dishonesty.
_FOOTNOTE_DEFINITION_RE = re.compile(r"^\[\^[^\]\s]+\]:")

#: The ``<br>`` forms the renderer emits for a newline inside a pipe-table cell (LD-041).
_BR_FORMS = {"<br>", "<br/>", "<br />"}

#: What a refused construct with NO text of its own contributes in **collecting mode**
#: (:meth:`_Compiler._plain_of`). U+FFFC OBJECT REPLACEMENT CHARACTER is Unicode's own
#: "an object stands here", and it is chosen for three properties: it is **non-empty and
#: non-whitespace**, so ``text.strip()`` — the exact test the empty-heading /
#: empty-list-item / empty-quote checks make — sees content and no phantom empty-marker
#: refusal is invented; it is a character **no Markdown author types**, so it cannot be
#: confused with real content; and it **reaches nobody**, because collecting mode discards
#: every block it builds (:meth:`_Compiler.check`) and the serial compile never takes this
#: path at all.
#:
#: It is a FALLBACK, not a blanket placeholder — and the reason is that a stand-in is
#: **strictly less faithful** than the author's own text, not that anything depends on it.
#: What the fallback buys is that the assembled text every enclosing check strips
#: (``_heading`` / ``_list`` / ``_blockquote``) is the author's own wherever there is one, so
#: the collecting pass reports exactly the refusals :func:`compose` raises and invents no
#: empty-marker refusal, and a character no Markdown author types stays confined to the one
#: case that has no text at all.
#:
#: **What it is NOT: it is not what lets a nested construct inside a refused one be found.**
#: That discovery is a side effect of :meth:`_Compiler._plain_of` recursing through
#: :meth:`_Compiler._inline_text`, which ``_record``\ s each nested refusal on the way down —
#: before, and independently of, which string is finally returned. This docstring claimed
#: otherwise until LD-623; the claim was disproved by mutating the return to a **blanket**
#: ``_REFUSED_STANDIN``, under which the whole offline suite stays green and
#: ``[**bold label**](url)`` still reports ``["link", "bold"]`` — the nested-link case of
#: ``tests/test_compose_check_batch_discovery.py``, in the source repository. The correct
#: attribution was already twenty lines below, in :meth:`_Compiler._plain_of`'s own docstring
#: (*"descending into a styled construct's children"*); only the constant's was wrong. The
#: code is unchanged, because a fallback that keeps real text is the more conservative of the
#: two whatever the reason written beside it.
_REFUSED_STANDIN = "\ufffc"


def _parser() -> MarkdownIt:
    md = MarkdownIt(_DIALECT_PRESET, {"maxNesting": _MAX_NESTING})
    for extension in _DIALECT_EXTENSIONS:
        md = md.enable(extension)
    return md


@dataclass(frozen=True)
class ComposeRefusal:
    """One inexpressible construct, **located** — what :func:`compose_check` reports a row
    of.

    It carries no new wording of anything: :attr:`refusal` is the very typed
    :class:`~larkdocio.write.model.Refusal` :func:`compose` raises for that construct, so
    the recovery text a caller reads here and the one they would have met serially cannot
    drift into two opinions. :attr:`construct` and :attr:`line` are the same two facts the
    ``detail`` names in prose, lifted out so a caller reads them **programmatically**
    instead of parsing a sentence.
    """

    construct: str
    line: int
    refusal: Refusal

    @property
    def detail(self) -> str:
        """The refusal's own actionable text — construct, line, why, and the fix."""
        return self.refusal.detail

    @property
    def reason(self) -> RefusalReason:
        """The typed reason (``not-in-dialect``, or ``merge-not-expressible`` for a grid)."""
        return self.refusal.reason

    def to_dict(self) -> dict:
        """JSON-native, for a caller that reports the list rather than reading it."""
        return {
            "construct": self.construct,
            "line": self.line,
            "reason": self.reason.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ComposeCheck:
    """What :func:`compose_check` returns: a **read-only** result carrying every construct
    the fragment cannot express, in document order.

    ``ok`` is the one question most callers ask (*"will this compose?"*); ``refusals`` is
    the whole list, one :class:`ComposeRefusal` per occurrence — **per occurrence**, not
    per construct, because two bold spans on two lines are two edits to make. ``constructs``
    is the de-duplicated construct list for a caller reporting *kinds* rather than sites.

    Deliberately **no** ``__bool__``/``__len__``: a result object whose truthiness could be
    read either as *"it checked out"* or as *"there are findings"* is a coin flip at the
    call site, so the question is asked by name.
    """

    refusals: Tuple[ComposeRefusal, ...] = field(default=())

    def __post_init__(self):
        object.__setattr__(self, "refusals", tuple(self.refusals))

    @property
    def ok(self) -> bool:
        """``True`` when the fragment names nothing the dialect cannot express."""
        return not self.refusals

    @property
    def constructs(self) -> Tuple[str, ...]:
        """The construct names, de-duplicated, in first-seen order."""
        seen: List[str] = []
        for row in self.refusals:
            if row.construct not in seen:
                seen.append(row.construct)
        return tuple(seen)

    def to_dict(self) -> dict:
        """JSON-native, same discipline as every other machine-readable shape here."""
        return {"ok": self.ok, "refusals": [row.to_dict() for row in self.refusals]}


#: Where :func:`_refuse` parks the :class:`ComposeRefusal` it built, on the error it
#: returns. The collecting pass reads it back rather than re-parsing the ``detail`` — the
#: construct and the line are known where the refusal is built, and a checker that scraped
#: them out of a sentence would break the first time a word of that sentence moved.
_LOCATED = "compose_refusal"


def _refuse(construct: str, line: int, extra: str = "") -> RefusedError:
    """The one refusal builder: name the construct, its 1-based line, and the recovery."""
    why = NOT_EXPRESSIBLE_CONSTRUCTS[construct]
    detail = (
        f"{construct} at line {line}: not expressible as creatable Lark docx content — "
        f"{why}."
    )
    if extra:
        detail = f"{detail} {extra}"
    refusal = (
        Refusal.merge_not_expressible(detail)
        if construct == "merged-table"
        else Refusal.not_in_dialect(detail)
    )
    error = RefusedError(refusal)
    # Invisible to every existing caller (``.refusal`` and the message are untouched); it
    # exists so the collecting pass can record WHAT and WHERE without a second definition.
    setattr(error, _LOCATED, ComposeRefusal(construct, line, refusal))
    return error


def _cells_in_row(line: str) -> int:
    """How many pipe-delimited cells a GFM table source row declares.

    An **escape-aware** scan (not a regex): a ``\\|`` is a literal pipe inside a cell and a
    ``\\\\`` is a literal backslash, so only an unescaped ``|`` delimits. A leading and a
    trailing pipe are the optional row fence and contribute no cell.
    """
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    cells, i, n, last = 1, 0, len(stripped), 0
    while i < n:
        ch = stripped[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "|":
            cells += 1
            last = i
        i += 1
    if last == n - 1 and n:                 # a trailing fence pipe closes the row
        cells -= 1
    return cells


class _Compiler:
    """One compile of one fragment. Holds the normalized source lines for the raggedness
    check and the refusal line numbers; carries no state a caller can observe.

    ``collect`` is the **only** difference between :func:`compose` and
    :func:`compose_check`, and it changes exactly one thing: whether a refusal ends the
    compile (``False`` — the shipped, first-failure behaviour, untouched) or is **recorded
    and walked past** (``True``) so one pass can name every construct. It never changes
    *what* is refused: every refusal is built by the same :func:`_refuse` call at the same
    place, with the same construct, the same line and the same words.
    """

    def __init__(self, markdown: str, *, collect: bool = False):
        # markdown-it normalizes CRLF/CR to LF before it assigns source maps, so the line
        # index this class reports (and slices) must be taken over the SAME normalization.
        self.source = markdown.replace("\r\n", "\n").replace("\r", "\n")
        self.lines = self.source.split("\n")
        self.collect = collect
        self.found: List[ComposeRefusal] = []

    # -- entry ---------------------------------------------------------------- #

    def compose(self) -> Tuple[NewBlock, ...]:
        tokens = _parser().parse(self.source)
        tree = SyntaxTreeNode(tokens)
        return tuple(self._blocks(tree.children, depth=1))

    def check(self) -> Tuple[ComposeRefusal, ...]:
        """Every refusal the fragment earns, in document order (``collect=True`` only).

        The blocks it builds along the way are **discarded**: this is a read-only walk of
        the same compile, not a partial one — nothing is ever half-composed and nothing is
        returned that could be inserted.
        """
        tokens = _parser().parse(self.source)
        tree = SyntaxTreeNode(tokens)
        self._blocks(tree.children, depth=1)
        return tuple(self.found)

    def _record(self, refused: RefusedError) -> None:
        """Record a refusal and let the walk continue — collecting mode's whole mechanism.

        An **unlabelled** refusal is re-raised rather than turned into a row: every refusal
        in this module's own call tree comes from :func:`_refuse` and therefore carries its
        construct and line, so a labelless one would mean a refusal from somewhere else
        entirely — and inventing a construct name for it is how a checker starts reporting
        things the compiler cannot refuse.
        """
        located = getattr(refused, _LOCATED, None)
        if located is None:                      # pragma: no cover — unreachable by design
            raise refused
        self.found.append(located)

    def _refuse_or_record(self, refused: RefusedError) -> None:
        """Strict mode raises the refusal; collecting mode records it and walks on.

        The refusal is re-raised **as the same object** — never rebuilt, re-wrapped or
        copied — so the row :func:`compose_check` reports carries the very reason, construct,
        line and recovery words :func:`compose` raises. The guard that would catch a re-wrap
        is ``test_ac1_the_checker_reports_the_VERY_refusal_compose_raises`` in
        ``tests/test_compose_check_batch_discovery.py``, in the source repository.

        **Four of the six statements of this rule route through here** (LD-629). The other
        two — the ``except RefusedError`` clauses in :meth:`_blocks` and :meth:`_list` — do
        **not**, and that is a decision rather than an oversight: their ``raise`` is a bare
        re-raise inside an active handler (it re-raises the exception *being handled*, keeping
        its traceback), so folding them in would take a context manager, which costs a reader
        more than the two lines of duplication it would remove.
        """
        if not self.collect:
            raise refused
        self._record(refused)

    # -- block level ---------------------------------------------------------- #

    def _blocks(self, nodes: Sequence[SyntaxTreeNode], depth: int) -> List[NewBlock]:
        out: List[NewBlock] = []
        for node in nodes:
            try:
                out.extend(self._block(node, depth))
            except RefusedError as refused:
                if not self.collect:
                    raise
                self._record(refused)            # …and on to the next SIBLING
        return out

    def _block(self, node: SyntaxTreeNode, depth: int) -> List[NewBlock]:
        """One block node → the blocks it composes to (a list only because a Markdown list
        composes to one block per item)."""
        kind = node.type
        if kind == "heading":
            return [self._heading(node)]
        if kind == "paragraph":
            return [self._paragraph(node)]
        if kind in ("bullet_list", "ordered_list"):
            return self._list(node, depth)
        if kind == "fence":
            return [self._fence(node)]
        if kind == "blockquote":
            return [self._blockquote(node)]
        if kind == "table":
            return [self._table(node)]
        if kind in _BLOCK_CONSTRUCTS:
            construct = _BLOCK_CONSTRUCTS[kind]
            if construct == "html" and self._is_html_table(node):
                construct = "merged-table"
            raise _refuse(construct, self._line(node))
        raise _refuse("block", self._line(node), extra=f"(construct: {kind})")

    def _heading(self, node: SyntaxTreeNode) -> NewBlock:
        level = int(node.tag[1:])
        # The inline run is extracted OUTSIDE _build so a precise inline refusal (image /
        # bold / link …) propagates with its own construct and line, instead of being
        # re-labelled as a generic block failure.
        text = self._inline_of(node)
        if not text.strip():
            raise _refuse("empty-heading", self._line(node))
        return self._build(lambda: NewBlock.heading(level, text), node, "empty-heading")

    def _paragraph(self, node: SyntaxTreeNode) -> NewBlock:
        text = self._inline_of(node)
        # A footnote DEFINITION (``[^label]: …``) is the unambiguous marker of footnote
        # intent, and it has no creatable block. A bare ``[^1]`` *reference* — and a regex
        # character class like ``[^a-z]`` — is literal text in CommonMark and in GFM
        # without a definition, so it composes verbatim and round-trips; refusing those
        # would refuse content that provably survives.
        if _FOOTNOTE_DEFINITION_RE.match(text.split("\n", 1)[0]):
            raise _refuse("footnote", self._line(node))
        return self._build(lambda: NewBlock.paragraph(text), node, "block")

    def _fence(self, node: SyntaxTreeNode) -> NewBlock:
        line = self._line(node)
        info = node.info.strip()
        if info and len(info.split()) > 1:
            raise _refuse("code-fence-info", line, extra=f"(info string: {info!r})")
        language: Optional[str] = info or None
        if language == MERMAID_FENCE_TOKEN:
            # A DIAGRAM, not a code block. This fence is the reader's own projection of a
            # type-40 add-on, and it now composes back into one — which is what closes the
            # round trip for a document containing a diagram. It is checked BEFORE the
            # language table on purpose: `mermaid` is not a Lark code-language enum and never
            # will be, so falling through would reach the unknown-token advice.
            body = node.content
            if body.endswith("\n"):
                body = body[:-1]
            return self._build(
                lambda: NewBlock.mermaid(body), node, "empty-mermaid",
            )
        if language is not None and language not in MD_LANG_TO_DOCX_CODE:
            # WHOSE token is it? A fence the reader itself emitted for a block with no
            # creatable form is not the caller's mistake, and the "pick a supported token"
            # advice cannot succeed for it — so it gets its own construct naming the real
            # cause. Any other unknown token IS a caller token choice, and keeps the
            # (correct) language advice unchanged (LD-177 / dogfood round 3 F7).
            projected = READER_PROJECTION_FENCES.get(language)
            if projected is not None:
                raise _refuse(
                    "non-creatable-projection", line,
                    extra=(
                        f"(fence token: {language!r} — the reader emits it for "
                        f"{projected}, which has no creatable form in this rung yet)"
                    ),
                )
            raise _refuse(
                "unknown-code-language", line,
                extra=(
                    f"(fence token: {language!r}; {len(supported_code_languages())} "
                    f"tokens are supported)"
                ),
            )
        # A fence's payload always ends with the newline that precedes the closing fence;
        # that newline is syntax, not content. Everything else is kept verbatim.
        body = node.content
        if body.endswith("\n"):
            body = body[:-1]
        return self._build(lambda: NewBlock.code(body, language=language), node, "block")

    def _blockquote(self, node: SyntaxTreeNode) -> NewBlock:
        children = list(node.children)
        if not children:
            raise _refuse("empty-quote", self._line(node))
        if len(children) != 1 or children[0].type != "paragraph":
            offender = next(
                (c for c in children if c.type != "paragraph"), children[-1],
            )
            raise _refuse("blockquote-block-child", self._line(offender))
        text = self._inline_of(children[0])
        if not text.strip():
            raise _refuse("empty-quote", self._line(node))
        return self._build(lambda: NewBlock.quote(text), node, "empty-quote")

    def _list(self, node: SyntaxTreeNode, depth: int) -> List[NewBlock]:
        if depth > MAX_NEST_DEPTH:
            too_deep = _refuse(
                "nesting-too-deep", self._line(node),
                extra=f"(depth {depth} > the {MAX_NEST_DEPTH}-level cap)",
            )
            # …and, in collecting mode, keep hunting inside the tree
            self._refuse_or_record(too_deep)
        ordered = node.type == "ordered_list"
        out: List[NewBlock] = []
        for item in node.children:
            try:
                out.append(self._list_item(item, ordered=ordered, depth=depth))
            except RefusedError as refused:
                if not self.collect:
                    raise
                self._record(refused)            # …and on to the next ITEM
        return out

    def _list_item(self, item: SyntaxTreeNode, *, ordered: bool, depth: int) -> NewBlock:
        children = list(item.children)
        if not children or children[0].type != "paragraph":
            raise _refuse("empty-list-item", self._line(item))
        text = self._inline_of(children[0])
        if not text.strip():
            raise _refuse("empty-list-item", self._line(item))
        nested: List[NewBlock] = []
        for extra_node in children[1:]:
            if extra_node.type not in ("bullet_list", "ordered_list"):
                raise _refuse("list-item-block-child", self._line(extra_node))
            nested.extend(self._list(extra_node, depth + 1))
        kids = tuple(nested)

        if ordered:
            return self._build(
                lambda: NewBlock.ordered(text, children=kids), item, "block",
            )
        # A checkbox prefix is a TODO — but only on a ``-`` item, which is the only shape
        # the reader ever emits one on.
        for prefix, done in _TODO_PREFIXES.items():
            if text.startswith(prefix):
                todo_text = text[len(prefix):]
                return self._build(
                    lambda: NewBlock.todo(todo_text, done=done, children=kids),
                    item, "block",
                )
        return self._build(lambda: NewBlock.bullet(text, children=kids), item, "block")

    def _table(self, node: SyntaxTreeNode) -> NewBlock:
        self._refuse_ragged(node)
        # Cells are extracted BEFORE _build so a precise per-cell refusal keeps its own
        # construct and line rather than being re-labelled.
        rows: List[List[object]] = []
        for section in node.children:            # thead / tbody
            for row in section.children:         # tr
                rows.append([self._cell_content(cell) for cell in row.children])
        return self._build(
            lambda: NewBlock.table(rows, header_row=True), node, "merged-table",
            cap_constructs=(("column cap", "table-column-cap"), ("cap", "table-cap")),
        )

    def _refuse_ragged(self, node: SyntaxTreeNode) -> None:
        """Refuse a table whose SOURCE rows disagree in width.

        GFM repairs raggedness silently (pad short, truncate long), so the tokens cannot
        show it — and a repaired grid would carry invented or dropped cells. The source is
        therefore the oracle: row 0 is the header, row 1 is the delimiter row (its width is
        already pinned to the header's by GFM's own table detection), and every remaining
        row must match.
        """
        start, end = node.map or (0, 0)
        row_lines = [
            (start + offset, text)
            for offset, text in enumerate(self.lines[start:end])
            if text.strip()
        ]
        if not row_lines:
            return
        width = _cells_in_row(row_lines[0][1])
        for index, (line_no, text) in enumerate(row_lines):
            if index == 1:                        # the delimiter row
                continue
            found = _cells_in_row(text)
            if found != width:
                ragged = _refuse(
                    "merged-table", line_no + 1,
                    extra=(
                        f"(row has {found} cell(s) but the header row has {width}; GFM "
                        f"would silently pad or truncate it)"
                    ),
                )
                # …and, in collecting mode, on to the next ROW
                self._refuse_or_record(ragged)

    def _cell_content(self, cell: SyntaxTreeNode):
        """One pipe-table cell → its plain ``str``, or a tuple of :class:`TextSpan`.

        **A LABELLED LINK INSIDE A CELL IS THE ONE INLINE CONSTRUCT THIS DIALECT ACCEPTS
        HERE (LD-619)**, and it is accepted because it was *measured*: Lark accepts and
        stores a ``text_run`` carrying ``text_element_style.link.url`` inside a docx table
        cell, on both write routes, read back fresh
        — the measurement is kept in the source repository at ``tests/captures/ld517-in-cell-link/captures/001-in-cell-link-readback.json``.
        The reader already projects that stored run back as ``[label](url)``, so
        the round-trip property — the thing the blanket ``link`` refusal protects — is what
        *admits* this one shape rather than what forbids it.

        **Everywhere else the link refusal is unchanged**, and so is every other inline
        construct in a cell: bold, italic, strikethrough and inline code in a cell are
        **unmeasured, not refuted**, and shipping them on the strength of the link result is
        evidence-borrowing, which is refused. A cell with no link composes to the same
        ``str`` it always did.
        """
        children = list(cell.children)
        if not children:
            return ""
        spans: List[TextSpan] = []
        text = self._inline_text(children[0], cell=True, spans=spans)
        if not any(span.link_url for span in spans):
            return text
        return tuple(spans)

    @staticmethod
    def _is_html_table(node: SyntaxTreeNode) -> bool:
        return node.content.lstrip().lower().startswith("<table")

    # -- inline level --------------------------------------------------------- #

    def _inline_of(self, node: SyntaxTreeNode) -> str:
        """The text of a block whose single child is an ``inline`` node."""
        children = list(node.children)
        if not children:
            return ""
        return self._inline_text(children[0])

    def _inline_text(self, inline: SyntaxTreeNode, *, cell: bool = False,
                     spans: Optional[List[TextSpan]] = None,
                     line: Optional[int] = None) -> str:
        """One inline run → its **plain** text, refusing every styled construct.

        Escapes arrive already decoded (``\\#`` ⇒ ``#`` with ``markup="\\#"``), which IS
        the LD-130 rule read in reverse. ``line`` advances across breaks so a refusal names
        the line the construct actually sits on, not the line the paragraph started on
        (an explicit ``line`` is for a node with no source map of its own — the children of a
        link, whose refusals must still name the line the link sits on).

        ``spans``, when a list is supplied, is where a **labelled link** is collected
        (LD-619 — :meth:`_cell_content` supplies one, nothing else does): the plain text
        accumulated so far is flushed into a span, the link becomes its own span carrying
        ``link_url``, and the returned string stays the **plain-text projection** of the
        whole run. With ``spans=None`` a labelled link refuses exactly as it always did.
        """
        if line is None:
            line = (inline.map or (0, 0))[0] + 1
        out: List[str] = []
        pending: List[str] = []

        def flush() -> None:
            joined = "".join(pending)
            pending.clear()
            if joined and spans is not None:
                spans.append(TextSpan(joined))

        def emit(text: str) -> None:
            out.append(text)
            pending.append(text)

        for child in inline.children:
            kind = child.type
            if kind == _TEXT_NODE:
                emit(child.content)
            elif kind == _SOFT_BREAK:
                emit("\n")
                line += 1
            elif cell and kind == "html_inline" and child.content.lower() in _BR_FORMS:
                # The renderer emits <br> for a newline inside a pipe cell (LD-041) — this
                # reverses exactly that projection, and only inside a cell.
                emit("\n")
            elif kind == "link" and self._is_bare_url_autolink(child):
                # The reader auto-links a bare http(s) URL (LD-054, always on, no knob), so
                # [url](url) composes back to the literal URL it was made from.
                emit(child.attrGet("href") or "")
            elif kind == "link" and spans is not None:
                out.append(self._link_span(child, spans, line, flush))
            elif kind in _INLINE_CONSTRUCTS:
                if kind == "hardbreak":
                    line += 1
                refused = _refuse(_INLINE_CONSTRUCTS[kind], line)
                self._refuse_or_record(refused)
                emit(self._plain_of(child, cell=cell, line=line))
            else:
                refused = _refuse("inline", line, extra=f"(construct: {kind})")
                self._refuse_or_record(refused)
                emit(self._plain_of(child, cell=cell, line=line))
        flush()
        return "".join(out)

    def _plain_of(self, child: SyntaxTreeNode, *, cell: bool, line: int) -> str:
        """A refused construct's own plain text — **collecting mode only**.

        Recording a construct and emitting nothing would leave the enclosing block looking
        EMPTY, and the very next check would report an ``empty-heading`` /
        ``empty-list-item`` / ``empty-quote`` that :func:`compose` never raises. A checker
        that invents a refusal is as wrong as one that misses a real one, so the construct's
        own text stands in for it — and descending into a styled construct's children means
        a construct **nested inside** a refused one is reported too, which is right: the
        caller has to fix both before the batch lands.

        **A construct's own text is not always there**, which is the whole reason for
        :data:`_REFUSED_STANDIN`: an alt-less ``![](media/dashboard.png)`` (the default
        spelling of most exporters), an empty link label ``[](url)``, a whitespace-only
        code span — each carries nothing, so keeping "its own text" would leave the
        enclosing block looking empty after all and reinvent the very phantom
        ``empty-list-item`` this method exists to prevent. The construct's own text is
        preferred whenever it has one; the stand-in is the fallback, not the rule.
        """
        if child.type == "hardbreak":
            return "\n"
        if child.children:
            plain = self._inline_text(child, cell=cell, line=line)
        else:
            plain = child.content or ""
        # ``strip()`` is the test deliberately: it is the SAME test _heading /
        # _blockquote / _list make on the assembled text before they refuse an empty
        # marker, so whitespace-only text is as empty here as it is there.
        return plain if plain.strip() else _REFUSED_STANDIN

    def _link_span(self, link: SyntaxTreeNode, spans: List[TextSpan], line: int,
                   flush) -> str:
        """A labelled link → one :class:`TextSpan` carrying ``link_url``; returns its label.

        The **anchor text must itself be plain**: a construct inside the anchor refuses with
        its own name and this line, because a styled run inside a cell is exactly what stays
        unmeasured. The URL is authored **verbatim** — every spelling rule
        (:class:`~larkdocio.write.model.TextSpan`) applies unchanged, and a rule it breaks
        becomes a typed dialect refusal here rather than a bare ``ValueError`` escaping the
        compiler.
        """
        label = self._inline_text(link, cell=True, line=line)
        href = link.attrGet("href") or ""
        flush()
        try:
            span = TextSpan(label, link_url=href)
        except ValueError as invalid:
            raise _refuse("link", line, extra=f"({invalid})") from invalid
        spans.append(span)
        return label

    @staticmethod
    def _is_bare_url_autolink(link: SyntaxTreeNode) -> bool:
        """Is this link the shape the reader's own linkify pass produces?

        ``[http://x](http://x)`` (and the ``<http://x>`` autolink) — a bare http(s) URL
        whose visible text IS its destination. Any other link is a styled run and refuses.
        """
        href = link.attrGet("href") or ""
        if not href.startswith(("http://", "https://")):
            return False
        children = list(link.children)
        return (
            len(children) == 1
            and children[0].type == _TEXT_NODE
            and children[0].content == href
        )

    # -- shared ---------------------------------------------------------------- #

    def _line(self, node: SyntaxTreeNode) -> int:
        return (node.map or (0, 0))[0] + 1

    def _build(
        self, factory, node: SyntaxTreeNode, construct: str, cap_constructs=(),
    ) -> NewBlock:
        """Build a ``NewBlock``, turning a construction refusal into a compile refusal.

        ``NewBlock`` refuses impossible content at construction (LD-134) and a ragged grid
        with the typed merge refusal (LD-135). Both are re-raised here **with the source
        line attached**, so every failure out of :func:`compose` is one typed refusal
        carrying a construct, a position and the original explanation.

        A refusal this compiler already raised (:func:`_refuse`) passes through
        **unchanged**: it already names its own construct and line, and re-wrapping it
        would bury the precise construct (``image``, ``bold``, …) under a generic label.
        Inline runs are extracted before ``factory`` is even called, so that case is rare
        by construction — this is the belt to that braces.
        """
        try:
            return factory()
        except RefusedError as already_typed:
            if already_typed.refusal.reason is RefusalReason.NOT_IN_DIALECT:
                raise
            # A MODEL-level typed refusal (the LD-135 merge refusal) carries no source
            # position — attach one.
            raise _refuse(
                construct, self._line(node),
                extra=f"({already_typed.refusal.detail})",
            ) from already_typed
        except ValueError as invalid:
            label = construct
            for marker, capped in cap_constructs or ():
                # ordered, first match wins — a table over BOTH caps keeps the label it has
                # always refused under (the model checks the cell cap first for the same
                # reason), so no existing refusal changes name (LD-431).
                if marker in str(invalid):
                    label = capped
                    break
            raise _refuse(
                label, self._line(node), extra=f"({invalid})",
            ) from invalid


def compose(markdown: str) -> Tuple[NewBlock, ...]:
    """Compile a Markdown fragment into ordered typed creatable content.

    :param markdown: a fragment in **our reader's dialect** (see the module docstring):
        headings, paragraphs, nested bullet / ordered / todo lists, fenced code, quotes and
        GFM tables — with the **reader's escaping rules honored in reverse** (an escaped
        metachar is literal text, never structure).
    :returns: the blocks **in document order**, ready to be an
        :class:`~larkdocio.write.model.InsertRequest`'s ``content``. An empty or
        whitespace-only fragment composes to ``()`` — there is nothing to create.
    :raises RefusedError: carrying a typed :class:`~larkdocio.write.model.Refusal` whose
        mandatory ``detail`` names the **construct and its 1-based line** — for any
        construct outside the dialect, and for any documented cap the fragment exceeds.
        Nothing is ever partly composed, silently dropped, flattened or approximated.

    **The 50-per-call cap is NOT one of those refusals.** ``compose()`` places no ceiling
    on the number of top-level blocks it returns — the count is
    ``len(compose(markdown))``. The docx v1 ``create_children`` endpoint creates at most
    :data:`~larkdocio.write.model.MAX_CHILDREN_PER_CALL` (<<MAX_CHILDREN_PER_CALL>>) blocks
    per call, so wrapping the returned content in an
    :class:`~larkdocio.write.model.InsertRequest` raises past that count — a plain
    ``ValueError`` from ``InsertRequest``'s own constructor, **not a `RefusedError`**.
    Check ``len(compose(markdown)) > MAX_CHILDREN_PER_CALL`` before building the request,
    and split a longer fragment across more than one insert.

    **It never writes.** No client, no credential, no transport: the returned content only
    reaches Lark through the existing ``dry_run`` → ``Plan`` → ``apply`` gate.

    >>> compose("## Plan\\n\\n- [x] ship it\\n")   # doctest: +SKIP
    (NewBlock(kind=HEADING, text='Plan', level=2), NewBlock(kind=TODO, text='ship it', done=True))
    """
    if not isinstance(markdown, str):
        raise TypeError(
            f"compose() takes a Markdown fragment as a str, got "
            f"{type(markdown).__name__}"
        )
    return _Compiler(markdown).compose()


# The cap's value is written ONCE (:data:`MAX_CHILDREN_PER_CALL`) and projected into
# compose()'s own docstring, so a constant move cannot leave a stale number behind (the
# same discipline ``WriteClient._patch_block``'s docstring already uses for its own cost).
compose.__doc__ = (compose.__doc__ or "").replace(
    "<<MAX_CHILDREN_PER_CALL>>", str(MAX_CHILDREN_PER_CALL))


def compose_check(markdown: str) -> ComposeCheck:
    """Report **every** construct a fragment cannot express — one pass, with line numbers.

    :param markdown: the same fragment :func:`compose` takes, in the same dialect.
    :returns: a read-only :class:`ComposeCheck`. ``ok`` says whether the fragment would
        compose; ``refusals`` is one :class:`ComposeRefusal` per inexpressible construct
        **occurrence**, in document order, each carrying the construct, its **1-based
        line**, and the very typed refusal :func:`compose` raises for it — the same words,
        because it is the same object.
    :raises TypeError: for a non-``str`` argument, exactly as :func:`compose` does. There
        is **no** ``RefusedError``: reporting is what this function does instead of raising.

    **It is a CHECKER, not a permissive mode.** Nothing here becomes writable that was not
    writable before: :func:`compose` still refuses the whole batch on the **first**
    construct, with the same message and the same code, and no refusal moved. The only
    thing that changed is **how many refusals you learn about per attempt** — the defect
    this answers is that a consumer migrating ~27,000 words needed eight attempts to
    discover eight constructs, one round trip each.

    It never composes anything: the blocks the walk builds are discarded, so there is no
    partial compile, no best-effort content and nothing that could be inserted. Like
    :func:`compose` it holds no client, no credential and no transport, and makes no
    network call.

    Two properties worth knowing before you loop over the result:

    * **Per occurrence, not per construct.** Two bold spans on two lines are two rows,
      because they are two edits. :attr:`ComposeCheck.constructs` is the de-duplicated
      view.
    * **A construct inside a fenced code block is not a refusal** — a fence's body is
      content. That is the whole reason this ships as a function rather than as a
      grep-the-markers recipe: the parsing is the part that is hard to get right.

    >>> compose_check("**bold** and `code`\\n").constructs      # doctest: +SKIP
    ('bold', 'inline-code')
    """
    if not isinstance(markdown, str):
        raise TypeError(
            f"compose_check() takes a Markdown fragment as a str, got "
            f"{type(markdown).__name__}"
        )
    return ComposeCheck(_Compiler(markdown, collect=True).check())


def compose_insert(
    markdown: str,
    reference: NarrativeAnchor,
    position: InsertPosition = InsertPosition.AFTER,
) -> InsertRequest:
    """:func:`compose` a fragment and pair it with an anchor — the thin convenience.

    Returns the **existing** :class:`~larkdocio.write.model.InsertRequest` (no new request
    type, no new gate): ``compose_insert(md, anchor)`` is exactly
    ``InsertRequest(reference=anchor, position=AFTER, content=compose(md))``. An empty
    fragment raises the request's own "needs at least one block" ``ValueError`` — an
    insertion with nothing to create is meaningless.

    ``reference`` is the request's own :data:`~larkdocio.write.model.NarrativeAnchor` union,
    so authoring anchors **either** by quote (:class:`~larkdocio.write.model.Anchor`) **or**
    by ``block_id`` (:class:`~larkdocio.write.model.AnchorById`) — including a
    ``block_id`` a previous ``apply`` just handed back in ``created_block_ids``.
    """
    return InsertRequest(
        reference=reference, position=position, content=compose(markdown),
    )
