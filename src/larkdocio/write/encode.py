"""larkdocio.write.encode — typed creatable content → real docx v1 block payloads
(LD-134, extended with the table kind by LD-135).

The one seam that turns a :class:`~larkdocio.write.model.NewBlock` (or the legacy
:class:`~larkdocio.write.model.NewParagraph`) into the ``children`` payload the docx v1
``create_children`` endpoint accepts. It is **pure**: no client, no credential, no
transport, no socket — it maps typed data to dicts. The gated
``dry_run`` → :class:`~larkdocio.write.preview.Plan` → ``apply`` chain is still the only
path a payload reaches Lark by.

**The payload oracle is the reader.** Every shape below is the shape
``src/larkdocio/blocks/`` parses back out, key for key:

===============  ====  ====================================================
kind             type  container the reader reads
===============  ====  ====================================================
paragraph        2     ``text.elements``            (``blocks/text.py``)
heading(L)       L+2   ``heading{L}.elements``      (``blocks/headings.py``)
bullet           12    ``bullet.elements``          (``blocks/lists.py``)
ordered          13    ``ordered.elements``         (``blocks/lists.py``)
todo             17    ``todo.elements`` + ``todo.style.done``
code             14    ``code.elements`` + ``code.style.language``
quote            15    ``quote.elements``           (``blocks/quote.py``)
table            31    ``table.property``           (``blocks/table.py``)
mermaid          40    ``add_ons.record`` (JSON)    (``blocks/diagram.py``)
===============  ====  ====================================================

So a per-kind unit test can encode a block, deserialize it with the SDK's own
``Block(...)``, and render it with the reader's registered handler — "what the reader
parses, the encoder emits" is *asserted*, not asserted-about.

**Tables are the one two-step kind (LD-135).** A table carries no ``elements`` of its own:
its payload is the **grid property** (``row_size`` / ``column_size`` / ``header_row``), and
Lark **auto-provisions the cell grid from it** — each cell (type 32) wrapping one inner text
block (type 2), live-proven by the W2 gate (LD-073). So the encoder emits the shell payload
**plus** the authored cell texts (:func:`table_cell_texts`, row-major, carried on
:class:`EncodedChild.cell_texts`) **plus, for a cell authored as a span sequence, its spans**
(:func:`table_cell_spans` on :class:`EncodedChild.cell_spans` — LD-619, the in-cell **link
anchor**), and the apply engine fills each cell by patching its inner block — the same
``update_text_elements`` patch a whole-cell edit performs, no new endpoint. A **merged** cell is not expressible from Markdown and is refused when the grid is
built (``merge-not-expressible``), never approximated here. ``header_row`` is emitted
**always** (never left to Lark's promote-row-0 default) — though a *false* flag, while
stored, is omitted from the payload Lark hands back, so the reader's absent ⇒ promoted rule
makes a headerless authored table read back promoted: documented lossiness in the Markdown
projection (live-verified in LD-135), and the reason ``NewBlock.table`` defaults to True.

**Nesting (an earlier open question, now answered).** ``create_children`` creates **one level
deep**, so an authored tree is encoded to a **flat pre-order sequence with parent
pointers** (:class:`EncodedChild`) and applied as **one call per parent**
(:func:`create_batches`), each deeper call parented on the **real block id Lark returned**
for its parent. This reuses the endpoint the engine already ships and has live-proven
rather than adopting the unproven ``descendant`` subtree endpoint (still the documented
future optimization: it would collapse a whole tree into one call via a temp-id map). The
cost is one round trip per parent, which is why the depth cap
(:data:`~larkdocio.write.model.MAX_NEST_DEPTH`) exists — and a deeper tree is **refused
with the cap named, never silently flattened**.

**Mermaid is the one kind whose payload is not text (LD-192).** A diagram is an ``add_ons``
block (type 40) whose content is a **JSON string** in ``add_ons.record`` — so instead of
``elements`` it carries the three fields a real block carries, and :func:`mermaid_record`
serializes the record in the exact form the server stores. It is **create-only**: there is no
``add_ons`` updater on the block-patch surface, so editing a diagram is *delete + create at
the same index* (a new ``block_id``) — see :meth:`~larkdocio.write.model.NewBlock.mermaid`.

Text is emitted **verbatim**: MD metacharacters in authored text are content, and escaping
them is the *reader's* job on the way back out (LD-130), never the encoder's on the way in.

**Created runs are unstyled — with exactly ONE exception, the LINK anchor.** The reason the
rest are unstyled is unchanged: a created run carries no run styling at all, and no styling
field exists on a :class:`~larkdocio.write.model.TextSpan`, so every one of them stays
inexpressible by construction rather than refused at runtime. What moved is the conclusion
for the **link** alone, because a use case needed it and Lark was measured to accept it: a
span carrying ``link_url`` emits ``text_element_style.link.url`` on its ``text_run``
(:func:`_span_elements`) — the URL **verbatim**, never re-spelled. The general styled-run
rung is still a documented future extension.
"""
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from larkdocio.blocks.diagram import MERMAID_COMPONENT_TYPE_ID
from larkdocio.langs import MD_LANG_TO_DOCX_CODE, PLAIN_TEXT_LANGUAGE
from larkdocio.mermaid.ruleset import DEFAULT_THEME
from larkdocio.write.client import MAX_DESCENDANTS_PER_CALL
from larkdocio.write.model import NewBlockKind, NewParagraph

#: kind → (block_type, container key) for the fixed-type kinds. Headings are computed
#: (``heading{L}`` ⇒ type ``L + 2``) because their type varies with the level.
_FIXED_KINDS: Dict[NewBlockKind, Tuple[int, str]] = {
    NewBlockKind.PARAGRAPH: (2, "text"),
    NewBlockKind.BULLET: (12, "bullet"),
    NewBlockKind.ORDERED: (13, "ordered"),
    NewBlockKind.TODO: (17, "todo"),
    NewBlockKind.CODE: (14, "code"),
    NewBlockKind.QUOTE: (15, "quote"),
}

#: The docx block type of an authored **table** — its cells are type 32, provisioned by
#: Lark from the table's grid property rather than sent as children.
TABLE_BLOCK_TYPE = 31
TABLE_CELL_BLOCK_TYPE = 32

#: The largest ``row_size`` / ``column_size`` the **create-time property form** of
#: ``create_children`` accepts — **9 per axis, measured** (LD-431). It is the whole root
#: cause of the bug that earned this constant: 9×3 and 9×5 create and read back, 10×3 and
#: 10×5 answer ``1770001 invalid param``, in one run on one disposable with the 9-row writes
#: as the positive control (the table-row-boundary probe, § 1; its findings were retired from the dev repo on 2026-09-18).
#: Cell count is not
#: the variable — 9×5 = 45 cells lands where 10×3 = 30 cells does not.
#:
#: **It is a ceiling on the DECLARATION, not on the table.** The same document accepted a
#: 10-row table two other ways in the same run, so the encoder seeds at this number and
#: :func:`~larkdocio.write.apply._grow_table_grid` appends the rest — which is why no row cap
#: exists anywhere in this library.
MAX_CREATE_GRID_AXIS = 9

#: The docx block type of an authored **mermaid diagram** — an ``add_ons`` block (LD-192).
MERMAID_BLOCK_TYPE = 40

#: The ``record``'s ``view`` value. A hand-typed Mermaid block carries exactly this string
#: (LD-192's probe § 3 read it off the specimen), and emitting it is part of what makes an
#: authored block **shape-identical** to one a person typed. It is deliberately **not** a
#: knob: the probe found the server keeps any value it is sent (``view: "notAView"`` is
#: accepted ``code 0`` and stored), so a caller-chosen view would only ever be a way to store
#: a block that cannot render.
MERMAID_RECORD_VIEW = "codeChart"

#: The characters Go's ``encoding/json`` HTML-escapes by default, and therefore the ones the
#: stored ``record`` string carries in escaped form.
#:
#: **This is a measured law, not a style choice** (LD-192's probe § 8, derived offline from the
#: committed captures): Lark stores the record in Go's default form — keys **sorted**, **compact**
#: separators, and ``<`` / ``>`` / ``&`` escaped. It is why the specimen's own record round-trips
#: **byte**-identically through :func:`mermaid_record` while a naively-dumped one would come back
#: semantically equal but byte-different. An encoder that wants byte-stable round-trips must emit
#: this exact form, so it does.
#: Held as the characters themselves, with the escape **derived** from each code point
#: (:func:`go_json_escape`) rather than written out as a literal — so the constant cannot be
#: corrupted by a tool that rewrites backslash escapes, and the pairing is arithmetic.
_GO_JSON_ESCAPED_CHARS = "<>&"


def go_json_escape(char: str) -> str:
    """One character as Go's ``encoding/json`` writes it — ``<`` becomes the 6-byte escape.

    Lowercase hex, which is the form the specimen's own record carries (LD-192's probe § 8).
    """
    return "\\u%04x" % ord(char)


#: The block types this rung can bring into existence — text 2, heading1..9 (3–11),
#: bullet 12, ordered 13, code 14, quote 15, todo 17, the **table family** 31/32
#: (LD-135: a table is authored as a grid; its cells come into existence **with** it —
#: Lark auto-provisions them — which is why 32 is creatable with no kind of its own), and
#: the **mermaid diagram** 40 (LD-192, on the gate probe's specimen-shaped create).
#: **The code truth the ``creatable`` write-support rows of the matrix in the source repository, not
#: in the wheel — BLOCKS.md — are guarded against** (``tests/test_blocks_md_matrix.py``),
#: so a kind added here without its matrix row reddens the suite — and, read the other way,
#: BLOCKS.md row 40's word could not flip to ``creatable`` until ``40`` appeared here. The two halves move together by construction.
CREATABLE_BLOCK_TYPES = frozenset(
    {bt for bt, _ in _FIXED_KINDS.values()}
    | {level + 2 for level in range(1, 10)}
    | {TABLE_BLOCK_TYPE, TABLE_CELL_BLOCK_TYPE, MERMAID_BLOCK_TYPE}
)


def mermaid_record(source: str, theme: Optional[str] = None) -> str:
    """A diagram's ``add_ons.record`` — a **JSON string**, in the form the server stores.

    ``record`` is a *string* field carrying JSON, not a JSON object: sending the object
    instead is refused ``9499`` with the value echoed back (LD-192's probe § 4 row g), so the
    serialization happens here rather than being left to the transport.

    Three keys, exactly the three a hand-typed block carries: ``data`` (the Mermaid source
    the reader consumes), ``theme``, ``view``. Emitted in **Go's default ``encoding/json``
    form** — keys sorted, compact separators, and ``<`` / ``>`` / ``&`` escaped — which is the
    form Lark hands back, so the specimen's own record round-trips through this function
    **byte for byte**. (A ``<br/>`` inside a node label is ordinary Mermaid, so the escaping
    is the common case rather than an edge.)

    ``theme`` is validated at construction (:meth:`~larkdocio.write.model.NewBlock.mermaid`),
    not here: this function is the serializer, and the whitelist belongs with the typed value
    that carries it.
    """
    record = {
        "data": source,
        "theme": theme or DEFAULT_THEME,
        "view": MERMAID_RECORD_VIEW,
    }
    # ensure_ascii=False so a non-ASCII label stays UTF-8 exactly as Go emits it; the three
    # HTML escapes Go *does* apply are then applied explicitly. Neither substitution can
    # introduce another escapable character, so the order of the replacements is irrelevant.
    out = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    for char in _GO_JSON_ESCAPED_CHARS:
        out = out.replace(char, go_json_escape(char))
    return out


def _heading_key(level: int) -> str:
    return f"heading{level}"


def block_type_for(item) -> int:
    """The docx v1 ``block_type`` ``item`` will be created as.

    ``item`` is a :class:`~larkdocio.write.model.NewBlock` or the legacy
    :class:`~larkdocio.write.model.NewParagraph` (always type 2).
    """
    if isinstance(item, NewParagraph):
        return 2
    if item.kind is NewBlockKind.HEADING:
        return item.level + 2
    if item.kind is NewBlockKind.TABLE:
        return TABLE_BLOCK_TYPE
    if item.kind is NewBlockKind.MERMAID:
        return MERMAID_BLOCK_TYPE
    return _FIXED_KINDS[item.kind][0]


def _elements(text: str) -> List[dict]:
    """One unstyled ``text_run`` element carrying ``text`` verbatim.

    Verbatim is the contract: an authored ``- not a list`` is *text*, and it is the
    reader that escapes it on the way back out so it can never masquerade as structure
    (LD-130). Escaping here would put a backslash into the document.
    """
    return [{"text_run": {"content": text}}]


def _span_elements(spans) -> List[dict]:
    """One ``text_run`` per :class:`~larkdocio.write.model.TextSpan` (LD-434).

    A span carrying ``link_url`` emits ``text_element_style.link.url`` — **the URL
    verbatim**, byte for byte as the caller gave it. That is the measured shape: Lark stored
    exactly what was sent and read it back unchanged, for both the raw and the
    percent-encoded spelling (media-spike captures 541 / 542, since retired from the dev repo on 2026-09-18),
    and the raw spelling is the one a click confirmed opens. The percent-encoded spelling is
    refused at construction (:class:`~larkdocio.write.model.TextSpan`), so nothing is encoded,
    normalised or re-spelled here.

    A span with no link emits the same bare ``{"text_run": {"content": …}}``
    :func:`_elements` has always emitted — so an unlinked span is byte-identical to the
    unstyled run, and **no other style key is ever written**: link is the one anchor this
    rung opens.
    """
    out: List[dict] = []
    for span in spans:
        run = {"content": span.text}
        if span.link_url is not None:
            run["text_element_style"] = {"link": {"url": span.link_url}}
        out.append({"text_run": run})
    return out


#: The span encoder, under the name the apply engine imports it by. One definition, two
#: routes: the create-time ``descendant`` body (:func:`table_subtree`) and the fill-time
#: ``update_text_elements`` body
#: (:func:`larkdocio.write.apply.build_span_elements_update`) both emit **these** elements,
#: because Lark was measured to accept the identical shape on both (LD-619 / D-110).
span_elements = _span_elements


def _content_elements(item) -> List[dict]:
    """The ``elements`` payload for a text-bearing block — spans if it has them."""
    spans = getattr(item, "spans", ())
    return _span_elements(spans) if spans else _elements(item.text)


def encode_block(item) -> dict:
    """One typed block → its ``create_children`` child payload (**own content only**).

    Children are *not* nested into the payload — ``create_children`` creates one level
    deep, so a tree is expressed as batches (:func:`encode_content`). A
    :class:`~larkdocio.write.model.NewParagraph` encodes **byte-identically** to
    ``NewBlock.paragraph(...)`` — the same dict :func:`~larkdocio.write.client.text_block`
    has always produced — so an existing consumer's writes are unchanged.
    """
    if isinstance(item, NewParagraph):
        return {"block_type": 2, "text": {"elements": _elements(item.text)}}

    kind = item.kind
    if kind is NewBlockKind.HEADING:
        return {
            "block_type": block_type_for(item),
            _heading_key(item.level): {"elements": _content_elements(item)},
        }
    if kind is NewBlockKind.TABLE:
        # A table carries no elements: the GRID PROPERTY is the payload, and Lark
        # provisions the R×C cells from it (each wrapping one inner text block). The
        # authored cell texts travel separately (:func:`table_cell_texts`) because they
        # are written by patching those provisioned inner blocks, not by this call.
        #
        # LD-431: the property form validates each axis at MAX_CREATE_GRID_AXIS, so what is
        # DECLARED here is the SEED grid — never the authored one when it is bigger. The
        # authored grid rides along on the EncodedChild (:func:`table_grid`) and the apply
        # engine appends the shortfall. Declaring the true size instead is the bug: Lark
        # answers `1770001` and the batch dies with earlier batches already written.
        return {
            "block_type": TABLE_BLOCK_TYPE,
            "table": {"property": {
                "row_size": min(item.row_count, MAX_CREATE_GRID_AXIS),
                "column_size": min(item.column_count, MAX_CREATE_GRID_AXIS),
                # emitted ALWAYS (never left to Lark's default, which promotes row 0) so
                # the created table's header state is exactly what was authored.
                "header_row": bool(item.header_row),
            }},
        }

    if kind is NewBlockKind.MERMAID:
        # THE SPECIMEN SHAPE, field for field (LD-192's probe § 3 read it verbatim off a
        # block the maintainer typed by hand; § 4 row (a) replayed exactly this body and it was
        # accepted `code 0` at both endpoints and at both positions).
        #
        # `component_id` is emitted EMPTY on purpose. It is the one id-looking field, and a
        # real block carries `""` — there is nothing server-minted to synthesize, which is
        # the finding that made the create possible at all. Rows (b)/(c)/(h) prove OMITTING
        # it also works; emitting it is what makes the body shape-identical to a hand-typed
        # block, so a stored diagram of ours cannot be told apart from one of theirs.
        #
        # `component_type_id` is the READER's own constant, imported rather than re-declared:
        # the handler that parses type 40 and the encoder that creates one must agree about
        # which add-on a Mermaid block is, and one definition is how that is guaranteed. It is
        # also the field the server calls REQUIRED in its own words (row (e)'s named field
        # violation: `children[*].add_ons.component_type_id is required`).
        return {
            "block_type": MERMAID_BLOCK_TYPE,
            "add_ons": {
                "component_id": "",
                "component_type_id": MERMAID_COMPONENT_TYPE_ID,
                "record": mermaid_record(item.text, theme=item.theme),
            },
        }

    block_type, key = _FIXED_KINDS[kind]
    container: dict = {"elements": _content_elements(item)}
    if kind is NewBlockKind.TODO:
        # the reader reads the checkbox from todo.style.done — emit it there.
        container["style"] = {"done": bool(item.done)}
    elif kind is NewBlockKind.CODE:
        # the reader reads the fence token from code.style.language (an enum int).
        container["style"] = {
            "language": MD_LANG_TO_DOCX_CODE.get(item.language, PLAIN_TEXT_LANGUAGE)
            if item.language is not None
            else PLAIN_TEXT_LANGUAGE
        }
    return {"block_type": block_type, key: container}


def table_cell_texts(item) -> Tuple[str, ...]:
    """A table's authored cell texts, **row-major** — or ``()`` for any other content.

    Row-major is the order Lark provisions (and returns) the cell grid in, so this tuple
    lines up index-for-index with the table block's ``children`` and the apply engine can
    zip the two without re-deriving coordinates. Texts are **verbatim**, like every other
    kind's text — the reader escapes MD metacharacters on the way back out, and
    the table renderer additionally escapes a cell's ``|``.

    **A RICH cell (a sequence of TextSpan) appears here as its PLAIN-TEXT PROJECTION** — its anchor text, concatenated — exactly as
    :class:`~larkdocio.write.model.NewBlock`'s own ``text`` is the projection of its
    ``spans``. That keeps every existing reader of this tuple (the preview, the refusal
    messages, the reconciler's marker guard) working unchanged: the link is an added layer,
    never a replacement of the text. The **elements** that carry the anchor come from
    :func:`table_cell_spans`, which travels beside this tuple.
    """
    if isinstance(item, NewParagraph) or item.kind is not NewBlockKind.TABLE:
        return ()
    return tuple(cell_plain_text(cell) for row in item.rows for cell in row)


def cell_plain_text(cell) -> str:
    """One **authored** table cell → its plain text: a ``str`` as-is, spans concatenated.

    The authored side. Not to be confused with
    :func:`larkdocio.write.resolve._cell_plain_text`, which reads the text out of a **live**
    cell node the resolver matched in a document — same words, opposite direction.
    """
    if isinstance(cell, str):
        return cell
    return "".join(span.text for span in cell)


def table_cell_spans(item) -> Tuple[Optional[tuple], ...]:
    """A table's cells as **span sequences where it has them**, row-major — ``()`` otherwise.

    One entry per cell, aligned index-for-index with :func:`table_cell_texts`: the cell's
    tuple of :class:`~larkdocio.write.model.TextSpan` if it was authored as one, and ``None``
    for a plain-text cell. ``None`` rather than a one-span tuple **on purpose** — a plain
    cell must keep travelling the exact code path (and emitting the exact bytes) it always
    did, and a value that is only sometimes a projection is a value every reader has to
    re-derive.

    The elements a span sequence encodes to are :func:`_span_elements`', which is the shape
    Lark was measured to accept and store inside a cell on both write routes — read back
    fresh, on both, rather than inferred from a create's success code
    (``tests/captures/ld517-in-cell-link/captures/001-in-cell-link-readback.json``, in the source repository).
    """
    if isinstance(item, NewParagraph) or item.kind is not NewBlockKind.TABLE:
        return ()
    return tuple(None if isinstance(cell, str) else tuple(cell)
                 for row in item.rows for cell in row)


def table_grid(item) -> Optional[Tuple[int, int]]:
    """A table's **authored** ``(rows, columns)`` — or ``None`` for any other content.

    The counterpart to :func:`encode_block`'s seed (LD-431). The payload declares at most
    :data:`MAX_CREATE_GRID_AXIS` per axis because that is all the create endpoint's property
    form accepts; this is what the table is *supposed* to be, so the apply engine knows how
    many rows / columns to append once the seed exists. Carried even when no growth is
    needed — a value that is only sometimes present is a value every reader has to re-derive.
    """
    if isinstance(item, NewParagraph) or item.kind is not NewBlockKind.TABLE:
        return None
    return (item.row_count, item.column_count)


def content_kind(item) -> str:
    """The block's kind as a plain word — ``"paragraph"``, ``"table"``, ``"heading"``….

    Exists for one reason: when Lark refuses a create mid-batch, the error names **which
    block** the engine was writing (LD-431 AC6), and a kind word is the half of that
    identification a caller can act on without the authored text ever entering the message.
    """
    if isinstance(item, NewParagraph):
        return NewBlockKind.PARAGRAPH.value
    return item.kind.value


@dataclass(frozen=True)
class EncodedChild:
    """One block in an encoded tree, flattened for the one-level-deep create endpoint.

    * ``payload`` — the ``create_children`` child dict (:func:`encode_block`);
    * ``parent`` — the **position in this same sequence** of the block that parents it, or
      ``None`` for a top-level block (which goes at the plan's insertion point). A
      position, not a block id: real ids do not exist until Lark returns them, and the
      apply engine substitutes them as it walks the batches;
    * ``depth`` — 1-based nesting depth (a top-level block is 1), for previews and the
      depth-cap check;
    * ``cell_texts`` — a **table**'s authored cell texts, row-major (empty for every other
      kind). They are not part of ``payload``: Lark provisions the cells from the grid
      property, and the apply engine fills each one afterwards.
    * ``cell_spans`` — the same grid's cells as **span sequences where it has them**
      (:func:`table_cell_spans`), ``None`` per plain cell, ``()`` for every non-table kind.
      It travels beside ``cell_texts`` rather than replacing it, so a plain cell keeps the
      code path and the bytes it always had and the link is an added layer;
    * ``grid`` — a **table**'s *authored* ``(rows, columns)``, ``None`` otherwise. The
      ``payload`` declares at most :data:`MAX_CREATE_GRID_AXIS` per axis, so this is how the
      apply engine knows what the seed still has to grow into;
    * ``kind`` — the block's kind as a plain word, so an API refusal can name what it was
      writing without quoting a single character of the caller's content.
    """

    payload: dict
    parent: Optional[int]
    depth: int
    cell_texts: Tuple[str, ...] = ()
    cell_spans: Tuple[Optional[tuple], ...] = ()
    grid: Optional[Tuple[int, int]] = None
    kind: str = ""


def encode_content(content) -> Tuple[EncodedChild, ...]:
    """A request's ``content`` tuple → the flat **pre-order** encoded sequence.

    Pre-order (parent immediately before its subtree) means a parent's position is always
    lower than its children's, so :func:`create_batches` can walk the sequence once and
    every parent id is already known by the time its children are created.

    The :data:`~larkdocio.write.model.MAX_NEST_DEPTH` cap is **not** re-checked here: a
    :class:`~larkdocio.write.model.NewBlock` refuses an over-deep subtree in its own
    ``__post_init__``, which every route into this function (including a tree rebuilt from
    JSON) must pass through, so the tree that arrives here is already within the cap. One
    enforcement point, structurally unavoidable — a second copy here would be dead code
    pretending to be a guard.
    """
    out: List[EncodedChild] = []

    def walk(item, parent: Optional[int], depth: int) -> None:
        position = len(out)
        out.append(EncodedChild(
            payload=encode_block(item),
            parent=parent,
            depth=depth,
            cell_texts=table_cell_texts(item),
            cell_spans=table_cell_spans(item),
            grid=table_grid(item),
            kind=content_kind(item),
        ))
        for child in getattr(item, "children", ()):
            walk(child, position, depth + 1)

    for item in content:
        walk(item, None, 1)
    return tuple(out)


# --------------------------------------------------------------------------- #
# LD-482 — the ONE-CALL table subtree (the `descendant` route)                   #
# --------------------------------------------------------------------------- #

#: The most cells a table may carry and still be authored in **one** ``descendant`` call —
#: **derived arithmetic over a measured ceiling, never a second measurement**. A table subtree
#: is ``2 × cells + 1`` descendants (the table block, one type-32 cell per cell, one type-2
#: text block inside each cell), so the largest whole table inside
#: :data:`~larkdocio.write.client.MAX_DESCENDANTS_PER_CALL` is ``(1000 − 1) // 2 = 499``.
#: The spike bisected exactly that boundary: 1×499 = 999 descendants ``code 0``, 1×500 = 1001
#: descendants ``99992402`` with nothing created
#: (the 2026-08-14 table-cell-creation spike, § 3b; its write-up was retired from the dev repo on 2026-09-18).
#:
#: It is **not** an authoring cap — :data:`~larkdocio.write.model.MAX_TABLE_CELLS` (500) is,
#: and it is larkdocio's own. This is a **route** boundary: a table at or under it is built
#: atomically in one call, and a table over it (up to the authoring cap) takes the
#: create-seed-grow-fill route exactly as it always has. Nothing is refused for being over it.
#:
#: **D-59 route scope** (inherited from the ceiling it is derived from): one tenant,
#: ``tenant_access_token``, docx v1, block type 31, on documents the spike created — not
#: wiki-wrapped. ``user_access_token``, other tenants and wiki-wrapped documents are
#: **unmeasured, not refuted**.
MAX_ONE_CALL_TABLE_CELLS = (MAX_DESCENDANTS_PER_CALL - 1) // 2

#: The prefix of every caller-minted temporary id in a ``descendant`` body. Temporary ids live
#: only for the duration of the one call that mints them (Lark maps each to a real block id in
#: its ``block_id_relations`` answer), so they need to be unique **within the body** and
#: nothing more — but they are also what an operator reads in a captured request, so they are
#: spelled to say where they came from.
TEMP_ID_PREFIX = "larkdocio_"


def table_descendants(cells: int) -> int:
    """How many descendants a ``cells``-cell table subtree costs — ``2 × cells + 1``.

    The table block itself, one type-32 cell per authored cell, and one type-2 text block
    inside each cell. **Measured, then derived**: the spike's 36×6 = 216-cell body carried 433
    descendants and its 50×10 = 500-cell body 1001, both of which this reproduces exactly
    (the same spike, § 3a; retired from the dev repo on 2026-09-18). A cell with
    **no** text child is not a cheaper spelling: Lark refuses that shape ``1770041 open schema
    mismatch``, so the ``2 ×`` is the platform's, not a choice this library makes.
    """
    return 2 * cells + 1


def fits_one_call(child: "EncodedChild") -> bool:
    """Is ``child`` a **table** small enough to author in one ``descendant`` call?

    Three conditions, all necessary and each cheap to check offline:

    * it is a table — ``grid`` is the field only a table carries;
    * its authored cell texts are exactly ``rows × columns`` of them, so the subtree this
      builds cannot be short or long of the grid it declares (a mismatch means something
      upstream changed shape, and the answer to that is the old route, not a guess);
    * it fits :data:`MAX_ONE_CALL_TABLE_CELLS`.

    A ``False`` is never a refusal — it selects the create-seed-grow-fill route, which has no
    such ceiling and reaches the whole authoring cap.
    """
    if child.grid is None:
        return False
    rows, columns = child.grid
    cells = rows * columns
    return (cells == len(child.cell_texts)
            and 0 < cells <= MAX_ONE_CALL_TABLE_CELLS)


def table_subtree(child: "EncodedChild") -> Tuple[str, Tuple[dict, ...]]:
    """One table :class:`EncodedChild` → ``(root_temp_id, descendants)`` for
    :meth:`~larkdocio.write.client.WriteClient.create_descendant`.

    The shape is the spike's own request body, field for field (its § 3a body is what answered
    ``code 0`` for the consumer's 36×6 grid and read back ``row_size 36, column_size 6``):

    * the **table** carries its ``block_id`` (a temporary id), the real
      ``row_size`` / ``column_size`` / ``header_row``, and ``children`` — every cell's
      temporary id, **row-major**;
    * each **cell** is ``{"block_type": 32, "table_cell": {}}`` with one child, its inner text
      block. A **childless** cell is refused by Lark on shape (``1770041``), so every cell
      carries one whether or not the caller authored text into it;
    * each **inner text block** is the identical ``{"block_type": 2, "text": {"elements": …}}``
      :func:`encode_block` emits for a paragraph, over the same :func:`_elements` — or, for a
      cell authored as a span sequence, over the same :func:`_span_elements` (LD-619) — so a
      cell's content is byte-for-byte what the create-then-fill route would have patched into
      it. **That the LINKED shape is accepted and stored on THIS route is measured**, not
      inferred from the paragraph control. Verified by a fresh read-back; the findings are
      kept in the source repository
      (``tests/captures/ld517-in-cell-link/captures/001-in-cell-link-readback.json`` § sent.route_A_descendant_body).

    Note what the table payload here does **not** do: it declares the **authored** grid, not
    the :data:`MAX_CREATE_GRID_AXIS` seed. The 9-per-axis ceiling is the *create* endpoint's
    property-form validation, and this route does not go through it — the spike created a
    36-row table in one call, which is the whole point. The seeded payload
    (:func:`encode_block`) is untouched and still what the other route sends.

    **An empty authored cell** gets a text block whose one run carries the empty string — the
    same ``_elements("")`` an authored empty paragraph produces. The alternatives are both
    worse: a childless cell is *refused* (measured), and dropping the cell would change the
    grid. That this exact spelling is accepted **in a descendant body** is
    **unmeasured, not refuted** — the spike's own bodies gave every cell a non-empty run.
    """
    rows, columns = child.grid
    header_row = bool(
        ((child.payload.get("table") or {}).get("property") or {}).get("header_row")
    )
    table_id = f"{TEMP_ID_PREFIX}t"
    cell_ids = [f"{TEMP_ID_PREFIX}c{n}" for n in range(rows * columns)]
    descendants: List[dict] = [{
        "block_id": table_id,
        "block_type": TABLE_BLOCK_TYPE,
        "table": {"property": {
            "row_size": rows,
            "column_size": columns,
            "header_row": header_row,
        }},
        "children": list(cell_ids),
    }]
    spans_per_cell = child.cell_spans or (None,) * len(child.cell_texts)
    for n, (cell_id, text, spans) in enumerate(
            zip(cell_ids, child.cell_texts, spans_per_cell)):
        inner_id = f"{TEMP_ID_PREFIX}x{n}"
        descendants.append({
            "block_id": cell_id,
            "block_type": TABLE_CELL_BLOCK_TYPE,
            "table_cell": {},
            "children": [inner_id],
        })
        descendants.append({
            "block_id": inner_id,
            "block_type": 2,
            # A RICH cell (LD-619) emits _span_elements — the exact element Lark accepted
            # and stored on THIS route, quoted in the probe's own capture
            # (in the source repository:
            # tests/captures/ld517-in-cell-link/captures/001-…json § sent.route_A_descendant_body).
            # A plain cell keeps _elements, byte-for-byte what it always sent.
            "text": {"elements": _span_elements(spans) if spans else _elements(text)},
        })
    return table_id, tuple(descendants)


def create_batches(encoded) -> Tuple[Tuple[Optional[int], Tuple[int, ...]], ...]:
    """Group an encoded sequence into the ordered ``create_children`` calls to issue.

    Returns ``((parent_position_or_None, (child_position, ...)), ...)`` — the ``None``
    group first (the top-level blocks, created at the plan's insertion point), then one
    group per parent **in pre-order**, so a parent is always created before the call that
    parents children on it. Flat content therefore yields **exactly one** group, which is
    exactly the single call the paragraphs-only engine made.
    """
    groups: Dict[Optional[int], List[int]] = {None: []}
    for position, child in enumerate(encoded):
        groups.setdefault(child.parent, []).append(position)
    ordered: List[Tuple[Optional[int], Tuple[int, ...]]] = []
    if groups[None]:
        ordered.append((None, tuple(groups[None])))
    for position in range(len(encoded)):
        if position in groups:
            ordered.append((position, tuple(groups[position])))
    return tuple(ordered)
