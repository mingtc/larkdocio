"""The opt-in block-identity projection: the reader's Markdown, plus which block each
piece of it came from.

A document read hands back Markdown that says everything about a document except
*which block said it*. That is fine to read and useless to edit: an agent that wants to
change one paragraph and write the change back has no way to name the paragraph, so it
reconstructs an anchor out of a verbatim quote and hopes the quote is unique.

:func:`project_block_ids` answers the missing half. It renders a parsed tree to the
same Markdown, with one single-line marker before each block-level node that carries an
identifier, and returns the identifiers **with** the text:

    <!-- lark:block:doxcnAbC123 -->
    The uptime was 99\\.9 percent\\.

Four properties make the result safe to build on, and each is a test rather than a
promise:

* **Nothing changes unless you ask.** The projection is off by default and this module
  is the only way to turn it on for a whole document, so a caller who does not use it
  sees byte-identical output.
* **It is additive.** :func:`strip_block_id_markers` of a projection is the renderer's
  own output for the same escaping policy, byte for byte — a marker line is inserted,
  nothing is modified.
* **Prose cannot forge a marker.** The projection renders with literal text escaped, so
  a document whose own words are ``<!-- lark:block:X -->`` emits them as
  ``\\<\\!\\-\\- lark:block:X \\-\\->`` and cannot be mistaken for the real thing. The
  price of that safety is that the block text you compare against is *escaped* text;
  :func:`unescape_literals` is its exact inverse and refuses rather than guess.
* **The identifier list is authoritative.** It comes back as part of the result, in
  document order, so nothing downstream has to scrape the text for identifiers and
  nothing downstream can be fooled into trusting one that was never emitted.
  :func:`strip_block_id_markers` takes that list for exactly this reason: it removes the
  markers **it** emitted, not every line that looks like one, which is what keeps a
  document whose own text is marker-shaped intact through a round trip.

Markers are emitted for nested blocks too — a list item at depth, a quote's children, a
table block — at the indentation of the block they introduce, so the surrounding
structure still parses as itself. Two kinds of block get none: an **editable** one that
renders no content (there would be nothing to anchor to), and one inside a table cell,
where a pipe-table row is a single line and a merged cell is raw HTML, so a marker line
would tear the table apart instead of annotating it. A table is annotated at the table
block.

**Opaque blocks, and the conservation contract.**

Not everything the reader renders is something an edit can be applied back to. An image,
a synced block, an embed, a whiteboard, a block type this release has never heard of —
the authoring dialect cannot create any of them. A table, and a mermaid add-on, it can
create, but the reader's Markdown for each is a *reshaping* of the block rather than the
block's own content. Those blocks carry the opaque form of the marker instead::

    <!-- lark:block:doxcnAbC123 opaque=image -->
    ![](boxedHoM834)

which names the block **and** its kind, while the block's readable content still shows —
opaque means "do not reconcile me", not "hide me". The distinction is a named attribute
and a list on the result (``.opaque_block_ids``), never something to infer from content.

The contract that marker states, in full:

    **An opaque-marked block is left exactly alone by any reconciliation.**
    It is **not edited**, **not deleted**, and **not re-created** — even if the
    edited projection **omits it entirely**.
    Conservation is the default posture and destruction is never inferred:
    the absence of a block from edited Markdown is evidence about the Markdown, not an
    instruction about the document.

**A table is opaque as a whole**, and its cells are deliberately not individually
addressable here — no cell carries a marker, so an edited cell has no anchor. The
supported route for changing a cell is the **table-cell patch** path in
``larkdocio.write``, which addresses a cell directly (by table anchor, row key and
column) instead of inferring it from prose.

Which types are on which side is **derived** from the reader's own handler registry, the
writer's creatable set and the shipped per-type read-lossiness — not from a hand-written
list — so a type that becomes supported lands on one side by construction. See
:mod:`larkdocio.model.conservation`.
"""
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

from .nodes import Node
from .renderer import (
    BLOCK_ID_MARKER_LINE_RE,
    BLOCK_ID_MARKER_RE,
    MarkdownRenderer,
    block_id_marker,
    unescape_literals,
)

__all__ = [
    "BlockIdProjection",
    "block_id_marker",
    "block_markdown",
    "find_emitted_block_id_marker",
    "project_block_ids",
    "replace_block_markdown",
    "strip_block_id_markers",
    "unescape_literals",
]


@dataclass(frozen=True)
class BlockIdProjection:
    """A projected document: its Markdown, and the identifiers that Markdown carries.

    ``block_ids`` is the authoritative emitted sequence in document order — what the
    renderer actually wrote, not what a search of ``markdown`` would find. The two are
    kept together in one value because separating them is how a caller ends up
    re-deriving one from the other.

    :meth:`to_dict` is JSON-native (a list, never a tuple), so the whole result can be
    handed to ``json.dumps`` and read back on the other side of a process boundary.
    """

    markdown: str
    block_ids: Tuple[str, ...]
    #: The subset of ``block_ids`` whose markers carry ``opaque=<kind>`` — the blocks
    #: :data:`~larkdocio.model.conservation.CONSERVATION_CONTRACT` covers. A value rather
    #: than a re-scan of the text, for the same reason ``block_ids`` is: the reconciler's
    #: "may I touch this block?" must not be answered by pattern-matching prose.
    opaque_block_ids: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, object]:
        """The JSON-serializable form:
        ``{"markdown": str, "block_ids": [...], "opaque_block_ids": [...]}``."""
        return {
            "markdown": self.markdown,
            "block_ids": list(self.block_ids),
            "opaque_block_ids": list(self.opaque_block_ids),
        }


def project_block_ids(root: Node, *, use_html_tags: bool = False) -> BlockIdProjection:
    """Render ``root`` to Markdown carrying one identity marker per block-level node.

    ``root`` is a parsed document tree — what ``Parser.parse_docx_tree`` returns. The
    escaping policy is **fixed**, not a parameter: literal text is escaped, because that
    is what makes a marker unforgeable by the document's own prose, and letting a caller
    turn it off would let them turn the guarantee off without noticing. Compare block
    text in the decoded domain (:func:`unescape_literals`) rather than against the raw
    projected line.

    ``use_html_tags`` mirrors the reader's own output setting so a projection matches the
    Markdown that read produced.
    """
    renderer = MarkdownRenderer(
        escape_literals=True, use_html_tags=use_html_tags, emit_block_ids=True
    )
    markdown = renderer.render(root)
    return BlockIdProjection(
        markdown=markdown,
        block_ids=tuple(renderer.emitted_block_ids),
        opaque_block_ids=tuple(renderer.emitted_opaque_block_ids),
    )


def strip_block_id_markers(text: str, block_ids: Iterable[str]) -> str:
    """Remove the identity markers for ``block_ids`` from ``text``.

    The inverse of the projection's one addition, and the reason the emitted identifier
    list travels with the text. A line is removed only when it is a marker **and** its
    identifier is one that was emitted; a marker-shaped line carrying anything else is
    the document's own content and is left exactly where it is. Stripping every
    marker-shaped line instead would delete a consumer's prose about markers — which is
    a real document, not a hypothetical one.

    ``text`` may be a whole projection or any part of one; the markers a quote or a
    nested list indented are recognized at their own indentation.
    """
    known = set(block_ids)
    return "".join(
        line
        for line in text.splitlines(keepends=True)
        if not _is_emitted_marker_line(line, known)
    )


def find_emitted_block_id_marker(text: str, block_ids: Iterable[str]) -> Optional[str]:
    """The identifier of the first identity marker for one of ``block_ids`` in ``text``,
    **wherever it sits** — or ``None`` when the text carries no such marker.

    The same set-aware question :func:`strip_block_id_markers` asks, asked without the line
    grammar, and it lives here so there is one answer to "is this id one we emitted".
    The write path needs it: on the **edit** path a replacement is arbitrary
    consumer prose that nobody parses and Lark stores verbatim, so a marker for an emitted
    block is identity leaking into content whether it sits on a line of its own or in the
    middle of a sentence. A marker-**shaped** string naming anything else is that
    document's own writing and is not found here — the fence that makes refusing safe.

    Reading an *edited projection* is the other direction and keeps the line grammar: see
    :func:`strip_block_id_markers`, which is deliberately NOT widened.
    """
    known = set(block_ids)
    for match in BLOCK_ID_MARKER_RE.finditer(text):
        if _names_emitted_block(match, known):
            return match.group(1)
    return None


# --------------------------------------------------------------------------- #
# Editing a projection BY BLOCK — the pair that closes the line-splice garble.   #
#                                                                              #
# A marker introduces a block; it does not promise the block is ONE LINE. A     #
# paragraph whose own text carries a soft return (a literal newline inside one  #
# text run — Lark stores them, and the Markdown shows one as an ordinary wrap)  #
# occupies two projected lines with a marker only above the first. So "find the #
# line that starts with X and replace that line" — the shape every line-based   #
# editor reaches for, and the shape this library's own copy-this recipe used to #
# teach — rewrites PART of a block and leaves the rest. The reconciler cannot   #
# catch it: by contract whatever comes back is authored intent, and a caller    #
# legitimately editing one line of a two-line block is byte-indistinguishable   #
# from one who garbled it. The measured outcome was `plan.ok: True` over a      #
# sentence with its ending written twice (LD-455 arm B).                        #
#                                                                              #
# The fix is to make the block, not the line, the unit a caller can address —   #
# so these two functions are a read/write PAIR over the same segment boundary,  #
# derived from the emitted id set exactly as `strip_block_id_markers` is.       #
# --------------------------------------------------------------------------- #

def block_markdown(projection: "BlockIdProjection", block_id: str) -> str:
    """The Markdown ``block_id`` occupies in ``projection``, its marker excluded.

    **However many lines that is** — which is the whole point. Counting the lines of this
    string is how a caller sees that a block carries a soft return before editing it, and
    the string itself is what :func:`replace_block_markdown` takes back.

    The text comes back at the block's **own** indentation (a nested list item's marker
    carries the item's indentation, and it is stripped here for the same reason the
    reconciler strips it: the indentation is the projection's, not the block's). Trailing
    blank lines — the projection's separators, not content — are excluded.

    Raises ``ValueError`` if ``block_id`` is not one the projection emitted: identity comes
    from ``projection.block_ids`` here as it does everywhere else, never from a search of
    the text.
    """
    lines, start, end, indent = _segment_lines(projection, block_id)
    body = lines[start:end]
    return "".join(
        line[len(indent):] if indent and line.startswith(indent) else line
        for line in body
    ).rstrip("\n")


def replace_block_markdown(
    projection: "BlockIdProjection", block_id: str, markdown: str
) -> str:
    """``projection.markdown`` with everything ``block_id`` occupies replaced by ``markdown``.

    The block-safe splice, and the one the shipped update recipe uses: it replaces the
    block's **whole segment**, so a block spanning two projected lines is replaced by two
    lines' worth of text and never half-rewritten. The marker line stays exactly where it
    is (identity is not content), the block's own indentation is re-applied to every line
    of ``markdown``, and the blank line separating this segment from the next survives.

    ``markdown`` is written as **plain** Markdown — not pre-escaped. The projection escapes
    literal text so a document's own prose cannot forge a marker, and the reconciler
    compares decoded on both sides (:func:`unescape_literals`), so a replacement that
    escaped itself would be comparing against the wrong domain.

    Passing ``""`` empties the segment, which is a **deletion of the block's text, not of
    the block** — the marker survives and the reconciler will read the result under its own
    absence rules. Raises ``ValueError`` for an id the projection did not emit.
    """
    lines, start, end, indent = _segment_lines(projection, block_id)
    # The blank lines that close the segment are the projection's separators, not the
    # block's content: they are left standing so the splice cannot weld two blocks together.
    while end > start and not lines[end - 1].strip():
        end -= 1
    replacement = (
        [indent + line + "\n" for line in markdown.split("\n")] if markdown else []
    )
    return "".join(lines[:start] + replacement + lines[end:])


def _segment_lines(projection: "BlockIdProjection", block_id: str):
    """``(all lines, body start, body end, the marker's indentation)`` for ``block_id``.

    One definition of "where does this block's text start and stop", shared by the read and
    the write half so the pair cannot drift into two answers.
    """
    known = set(projection.block_ids)
    if block_id not in known:
        raise ValueError(
            f"{block_id!r} is not a block this projection emitted — identity comes from "
            f"projection.block_ids ({len(known)} ids), never from searching the Markdown"
        )
    lines = projection.markdown.splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if not _is_emitted_marker_line(line, known):
            continue
        if start is not None:
            return lines, start, index, _marker_indent(lines[start - 1])
        match = BLOCK_ID_MARKER_LINE_RE.match(line.rstrip("\r\n"))
        if match.group(1) == block_id:
            start = index + 1
    if start is None:  # pragma: no cover - an emitted id always has its marker
        raise ValueError(f"the marker for {block_id!r} is not in projection.markdown")
    return lines, start, len(lines), _marker_indent(lines[start - 1])


def _marker_indent(marker_line: str) -> str:
    """A marker takes the indentation of the block it introduces (the reconciler's own
    rule, quoted here rather than re-derived)."""
    return marker_line[: len(marker_line) - len(marker_line.lstrip(" \t>"))]


def _is_emitted_marker_line(line: str, known: set) -> bool:
    match = BLOCK_ID_MARKER_LINE_RE.match(line.rstrip("\r\n"))
    return match is not None and _names_emitted_block(match, known)


def _names_emitted_block(match, known: set) -> bool:
    """The set-awareness itself, in one place: group 1 of either matcher is the id."""
    return match.group(1) in known
