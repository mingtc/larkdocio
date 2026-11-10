"""Two helpers for reading a parsed document's node tree: :func:`walk` and :func:`plain_text`.

These are the functions a consumer needs the moment they choose the tree over the Markdown
projection — "visit every block" and "what does this block say". They are shipped as real
functions rather than left as examples to copy, because both are easy to write in a way that
loses content **silently**:

* a walk that follows only ``children`` never reaches a table's cells (a
  :class:`~larkdocio.model.nodes.TableNode` holds them on ``cells``) or a grid's columns (a
  :class:`~larkdocio.model.nodes.GridNode` holds those on ``columns``). Since a table is where
  a document usually keeps its figures, such a walk reports a costs table as empty rather than
  as unreachable;
* a text reduction that reads ``content`` off each run drops every ``@mention``, because a
  :class:`~larkdocio.model.nodes.MentionUser` carries its ``user_id`` instead — so "@alice
  please own this" reduces to " please own this".

Both are pure functions over an in-memory tree: no credentials, no calls, no Markdown. They
read the model and never mutate it, and they change nothing about what the reader emits.
"""
from typing import Iterator, List, Sequence

from .nodes import (
    Inline,
    InlineEquation,
    MentionDoc,
    MentionUser,
    Node,
    RawInline,
    StyledText,
    Text,
    UnsupportedInline,
)

__all__ = ["walk", "plain_text"]


#: The two ordinary child-sequence field names :func:`_child_sequences` reads by attribute —
#: promoted to a module constant (LD-567) so this function, the guide's generated node-class
#: index (:mod:`larkdocio.model.node_docs`) and nothing else share one spelling of "these are
#: the container fields" rather than a second tuple that could quietly drift from this one.
_CHILD_SEQUENCE_FIELD_NAMES = ("children", "cells")

#: The grid's own container field, kept apart from the tuple above because a grid's columns are
#: a LIST OF LISTS (one list per column), not a single flat sequence.
_GRID_COLUMNS_FIELD_NAME = "columns"


def _child_sequences(node) -> List[Sequence]:
    """Every ordered child-block sequence a node owns, across the container shapes.

    Most containers own one ``children`` list; a table owns ``cells``; a grid owns one list per
    entry of ``columns``. Read by attribute rather than by node class, so a container added to
    the model is walked here without a change. The three shapes are returned in document
    order, and no node in the model owns more than one of them — a node is therefore reached
    once, never twice.
    """
    out: List[Sequence] = []
    for name in _CHILD_SEQUENCE_FIELD_NAMES:
        sequence = getattr(node, name, None)
        if isinstance(sequence, list):
            out.append(sequence)
    columns = getattr(node, _GRID_COLUMNS_FIELD_NAME, None)
    if isinstance(columns, list):
        for column in columns:
            if isinstance(column, list):
                out.append(column)
    return out


def walk(root: Node) -> Iterator[Node]:
    """Every block node in a parsed document, outermost first — the whole tree.

    **It is a FUNCTION, not a method:** ``walk(tree)``, imported from ``larkdocio.model``.
    Neither a node nor the tree the parser hands back carries a walk method, so reaching for one
    raises ``AttributeError`` — which is the first thing a reader of this docstring tends to try.

    Yields ``root`` itself, then each of its child blocks in document order, descending into
    every one. **All three container shapes are followed**, which is the whole reason this is a
    shipped function: ``children`` (headings, list items, callouts, quote containers, table
    cells, views, agenda blocks, the page root), ``cells`` (a table's cells) and ``columns`` (a
    grid's columns, one list per column). A walk that follows only ``children`` silently stops
    at every table and every grid.

    Inline content is **not** yielded: this walks blocks, and a block's own words are
    :func:`plain_text`'s job. The two compose — ``walk`` decides *which* blocks,
    ``plain_text`` says what each one says — and because ``plain_text`` reads only a block's
    own content, the pair never counts the same words twice.

    A **generator**, so a caller may stop early on a large document; calling it again walks the
    tree again. The traversal assumes a tree (which is what the reader builds — every block
    appears under exactly one parent).
    """
    yield root
    for sequence in _child_sequences(root):
        for child in sequence:
            if isinstance(child, Node):
                yield from walk(child)


def _inline_plain_text(inline: Inline) -> str:
    """One inline run as readable text — **read** semantics: nothing is silently dropped.

    Each kind contributes the text the reader shows for it, minus the wrappers that are pure
    markup (a styled run's ``**``/``_``, a document mention's link target): a literal or styled
    run contributes its words, a user mention its ``@`` token, a document mention its title, an
    inline equation its ``$…$`` source, already-formatted inline markup itself, and an inline
    variant the reader cannot render its visible ``[unsupported inline: …]`` marker.

    An :class:`~larkdocio.model.nodes.Inline` kind this function does not know raises
    ``TypeError`` naming it, exactly as the Markdown serializer does for the same reason: a new
    inline type must be handled deliberately, and returning ``""`` for one would be the silent
    drop this function exists to prevent.
    """
    # The arms are in the same order as the Markdown serializer's own inline dispatch, so the
    # two can be read side by side.
    if isinstance(inline, Text):
        return inline.content
    if isinstance(inline, StyledText):
        return inline.content
    if isinstance(inline, MentionUser):
        return f"@{inline.user_id}"
    if isinstance(inline, MentionDoc):
        return inline.title
    if isinstance(inline, InlineEquation):
        return f"${inline.content}$"
    if isinstance(inline, UnsupportedInline):
        return f"[unsupported inline: {inline.variant}]"
    if isinstance(inline, RawInline):
        return inline.markup
    raise TypeError(
        f"larkdocio.model.plain_text has no reduction for inline node "
        f"{type(inline).__name__} — a new inline kind must be handled explicitly rather "
        f"than contributing nothing"
    )


#: The field names :func:`plain_text` tries FIRST, in order, for a node's own text: the first
#: of these that carries a non-empty ``str`` or a ``list`` of :class:`Inline` wins. Promoted to
#: a module constant (LD-567) for the same reason as :data:`_CHILD_SEQUENCE_FIELD_NAMES` above
#: — one spelling, read here and by the guide's generated node-class index, never a second one
#: hand-typed beside it.
_TEXT_FIELD_NAMES = ("content", "title")

#: The fallback field names tried when neither of the above carries text — a block whose "own
#: words" live on a single string attribute rather than an inline run (an image's caption, an
#: iframe's url, an unrenderable block's raw markup).
_TEXT_FALLBACK_FIELD_NAMES = ("caption", "url", "markup")


def plain_text(node) -> str:
    """One node's OWN readable text — a block's words, or a single inline run's.

    **It is a FUNCTION, not a method:** ``plain_text(node)``, imported from ``larkdocio.model``
    beside :func:`walk`. A node carries no ``.plain_text()`` — the word *"pass"* below means
    pass it as an argument. The pair composes: ``walk`` chooses **which** blocks,
    ``plain_text`` says what each one says, and the guide's
    § "Recipe: you re-ingested a document that never changed — the revision_id change detector"
    uses both in three lines to find a quotable anchor.

    Pass a block node and you get that block's own text: its inline run (a paragraph, heading,
    list item, quote, code body, agenda title), a page's title, a block equation's source, an
    image's caption, an embedded component's url. **Never its child blocks** — a heading's text
    is its heading line, not the section beneath it — so a pure container (a table, a table
    cell, a grid, a callout) reports ``""`` and :func:`walk` is what reaches the blocks inside
    it. Pass a single inline run (the shape a word-level review anchor sits on) and you get
    that run's text.

    **Read semantics: an ``@mention`` is included**, as the raw ``@ou_…`` token the reader
    itself emits (this library never resolves an id to a display name), and so is an inline
    equation and the visible marker for an inline variant the reader cannot render. Nothing a
    block says is dropped.

    **This is deliberately NOT ``larkdocio.write.block_plain_text``, and the difference
    matters.** That function answers a different question — "what text in this block could a
    person literally quote back to me" — because it backs anchor matching for a write, and a
    mention is not quotable text, so it omits mentions **on purpose**. That is correct for
    anchoring and wrong for reading: use this one to read a document, that one when you are
    matching an anchor quote. On a block holding a mention the two return different strings,
    and the test suite pins that they do.
    """
    if isinstance(node, Inline):
        return _inline_plain_text(node)
    for name in _TEXT_FIELD_NAMES:
        value = getattr(node, name, None)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "".join(_inline_plain_text(run) for run in value if isinstance(run, Inline))
    for name in _TEXT_FALLBACK_FIELD_NAMES:
        value = getattr(node, name, None)
        if isinstance(value, str):
            return value
    return ""
