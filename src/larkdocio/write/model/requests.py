"""larkdocio.write.model.requests — the findings-agnostic edit-request vocabulary.

The typed requests a consumer expresses against a Lark docx **without leaking its
findings schema into the library**: larkdocio never learns a consumer's findings
vocabulary, layer labels, or status flow. A consumer maps its own accepted edits onto
these values and owns its approval UX; larkdocio only resolves (S2), previews/applies
(S3–S5), and returns the apply-log.

* :class:`EditRequest` — an **anchor** (an :class:`~larkdocio.write.model.anchors.Anchor`
  or :class:`~larkdocio.write.model.anchors.TableLocator`) and a **whole-block replacement
  text** (whole paragraph, or whole cell). The table anchor is **additive** — the paragraph
  path is untouched. It serializes **tagless** (byte-compatible with its W1/W2 form).
* :class:`InsertRequest` / :class:`DeleteRequest` (W3 / LD-074) — the two **block-level**
  operations. An :class:`InsertRequest` carries a reference :class:`~larkdocio.write.model.anchors.Anchor`,
  an :class:`InsertPosition` (before / after / append-into), and non-empty **creatable
  content** — :class:`NewBlock` values (LD-134: heading(level) / paragraph / bullet /
  ordered / todo with nesting / code(language) / quote; LD-135: table(rows, header_row))
  and/or the legacy tagless :class:`NewParagraph`. The kind vocabulary is a **closed enum**
  (:class:`NewBlockKind`), so the types this library does not author (image/board/embed/
  bitable/sheet) stay **inexpressible by construction**. **Mermaid (docx type 40) is the one
  that left that list** — LD-192's gate probe proved a specimen-shaped ``add_ons`` create is
  accepted, so it ships as :meth:`NewBlock.mermaid` (create-only: there is no in-place
  update, see that method). A :class:`DeleteRequest` carries a
  single target anchor (contiguous-range delete is a documented non-goal for phase-1).
  Both are frozen, JSON-round-trippable, and serialize with an ``"op"`` discriminator so
  :func:`_request_from_dict` tells edit / insert / delete / subspan apart; one content
  dispatcher (:func:`_content_from_dict`) tells the tagged :class:`NewBlock` from the
  tagless :class:`NewParagraph`.
* :class:`SubSpanEditRequest` (W3 / LD-077) — edit a **quoted span WITHIN a paragraph**,
  preserving the surrounding run styles; serializes with an ``"op": "subspan"`` tag.

No resolution, no write happens here — this module is dumb typed data. It depends on the
standard library plus the anchor vocabulary (:mod:`larkdocio.write.model.anchors`).
"""
import urllib.parse
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, Union

from larkdocio.langs import MD_LANG_TO_DOCX_CODE

from .anchors import (
    WHOLE_DOCUMENT,
    Anchor,
    AnchorById,
    CommentThread,
    TableLocator,
    WholeDocument,
    _anchor_from_dict,
)
from .refusal import Refusal, RefusedError

#: The anchor shapes a **narrative** request family accepts — the quote+breadcrumb
#: :class:`Anchor` or the by-id :class:`AnchorById` (LD-137). A :class:`TableLocator` is
#: deliberately absent: you insert/delete/sub-span-edit relative to a *block*, not a cell.
#: Named once so the four families share one definition and
#: :func:`larkdocio.capabilities.capabilities` can project the anchor kinds off each
#: family's own annotation instead of a hand-list.
NarrativeAnchor = Union[Anchor, AnchorById]

#: The anchor shapes the **table-grow** family accepts (LD-575) — the table's own
#: :class:`AnchorById`, or a :class:`TableLocator` whose row-key identifies which table. The
#: quote-and-breadcrumb :class:`Anchor` is deliberately absent: a table carries no text of its
#: own, so a quote can never resolve to one (the same reason a whole-block text edit refuses a
#: container). Named once, for the same reason :data:`NarrativeAnchor` is: the anchor kinds
#: ``capabilities()`` reports are projected off this annotation rather than hand-listed.
TableAnchor = Union[AnchorById, TableLocator]


@dataclass(frozen=True)
class EditRequest:
    """A consumer's request to replace one paragraph **or one table cell**.

    ``anchor`` locates the target — an :class:`Anchor` (quote + breadcrumb, the
    narrative/paragraph path), a :class:`TableLocator` (row-key + column-target +
    breadcrumb, the table-cell path), **or** an :class:`AnchorById` (a bare ``block_id``).
    ``replacement`` is the **whole-block** text (whole paragraph, or whole cell)
    that should stand in its place. This is the entire findings-agnostic contract a consumer
    expresses — no finding id, no layer, no status. Frozen: a request is an immutable value.
    Each added anchor shape is **additive** — the paragraph path is untouched.

    ``todo_done`` is the **one non-text property this request carries**: the
    checkbox state of a ``todo`` block, set only when the bit must MOVE. ``None`` — the
    default and every request written before it shipped — means *do not touch the checkbox*,
    and the key is omitted from :meth:`to_dict` so every existing serialization is
    byte-identical. It exists because the alternative was the defect it closes: an edited
    projection whose checkbox was flipped compiled to a text-only request whose replacement
    equalled the live text, and the apply log said ``applied`` while the bit did not move.
    The engine writes it as the block ``PATCH`` endpoint's ``update_text_style`` oneof (see
    :func:`~larkdocio.write.apply.build_todo_done_update`) — no new endpoint and no new
    scope. It is deliberately **not** a general style channel: a second property would need
    its own measured field mask, and the compiler refuses every property it cannot carry
    (``change-not-expressible``) rather than reporting a no-op as success.
    """

    anchor: "Union[Anchor, TableLocator, AnchorById]"
    replacement: str
    todo_done: Optional[bool] = None

    def to_dict(self) -> dict:
        d = {"anchor": self.anchor.to_dict(), "replacement": self.replacement}
        if self.todo_done is not None:
            d["todo_done"] = self.todo_done
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "EditRequest":
        return cls(anchor=_anchor_from_dict(d["anchor"]), replacement=d["replacement"],
                   todo_done=d.get("todo_done"))


# --------------------------------------------------------------------------- #
# InsertRequest / DeleteRequest — the W3 block-level operations (LD-074)          #
# reference/target Anchor + (for insert) a position + text-bearing content only   #
# --------------------------------------------------------------------------- #

class InsertPosition(Enum):
    """Where a new block goes relative to an :class:`InsertRequest`'s reference block.

    * ``BEFORE`` — as the reference's previous sibling (same parent, one index earlier).
    * ``AFTER`` — as the reference's next sibling (same parent, one index later).
    * ``APPEND_INTO`` — as the last child *of* the reference (the reference must be a
      block that can parent children; a leaf paragraph cannot, and the resolver refuses that case
      with :meth:`Refusal.cannot_hold_children`).

    The ``value`` string is the stable serialized form. The actual insertion **index**
    is computed from the resolved reference at plan time — the model carries only
    the *intent*, not a raw index.
    """

    BEFORE = "before"
    AFTER = "after"
    APPEND_INTO = "append-into"


@dataclass(frozen=True)
class NewParagraph:
    """One text-bearing paragraph to create — the **only** shape of insertable content.

    This is the structural exclusion that makes the types this library does not author
    (image / board / embed / bitable / sheet — image/board create only as empty placeholders,
    and bitable/sheet are rejected ``1770001 invalid param``) **inexpressible by
    construction**, not merely refused at runtime: a :class:`NewParagraph` carries **plain
    text only** — there is no block-type discriminator, no image token, no embed url, no
    sheet/bitable reference to smuggle one of them through. A consumer that wants to create
    anything cannot ask for anything but a text-bearing paragraph.

    **Mermaid (docx type 40) is NOT in that list, and the correction matters.** An earlier
    write spike recorded a *naive* ``add_ons``/mermaid create rejected ``1770001 invalid
    param``, and this docstring quoted that code as fact for the whole group. A later probe
    against the live API narrowed it to a **malformed-payload artifact**: a
    **specimen-shaped** ``add_ons`` create is accepted ``code 0`` on both create endpoints
    and at both positions, and ``1770001`` is what Lark answers for a type-40 body carrying
    **no ``add_ons`` object at all**. So **mermaid is API-creatable**, it ships as
    :meth:`NewBlock.mermaid`, and nothing about it was ever an API prohibition. **Nothing
    here is claimed about bitable (18) or sheet (30)** — that probe covered mermaid only, so
    those two remain exactly as the earlier spike left them, and they are the only part of
    the original sentence the ``1770001`` code still describes.

    *Superseded as the floor, kept as the shape.* The additive ``kind``
    this docstring anticipated shipped as :class:`NewBlock` — headings, bullet / ordered /
    todo list items (nested), code blocks, quotes, **tables** and **mermaid diagrams** are
    creatable now. ``NewParagraph`` remains **fully valid** insert content, serializes
    **tagless** exactly as it always did, and is equivalent to ``NewBlock.paragraph(text)``
    (byte-identical Lark payload), so no existing consumer changes. The types larkdocio does
    not author stay **structurally inexpressible** in both shapes — and that is now a
    statement about **larkdocio's own design choice**, not about API hostility:
    :class:`NewBlockKind` is a *closed* enum with no image token, embed url or sheet
    reference to smuggle one through, and a kind joins it only on evidence (mermaid did).
    Styled-run creation (the spike's mixed-run Test 3) is still a documented future extension
    — created text is unstyled.
    """

    text: str

    def to_dict(self) -> dict:
        return {"text": self.text}

    @classmethod
    def from_dict(cls, d: dict) -> "NewParagraph":
        return cls(text=d["text"])


# --------------------------------------------------------------------------- #
# NewBlock — the typed creatable-kind family (LD-134/135)                       #
# The additive `kind` NewParagraph.__doc__ anticipated: heading(level),          #
# paragraph, bullet / ordered / todo (nested), code(language), quote, table.     #
# --------------------------------------------------------------------------- #

#: The deepest nesting a single authored tree may express. Each level costs its **own**
#: ``create_children`` call (the endpoint creates one level deep), and those calls are
#: serialized through the write throttle — so an unbounded depth is an unbounded serial
#: write chain. Past the cap the request is **refused with the cap named**, never silently
#: flattened (an earlier parked nesting question, answered here).
#: This is larkdocio's own documented authoring cap, not a discovered API ceiling.
MAX_NEST_DEPTH = 10

#: ``create_children`` creates **1–50** blocks per call (docx v1). One sibling group is one
#: call, so a group past 50 cannot be created — refused with the limit named rather than
#: left to fail live as an opaque ``1770001`` partway through a batch.
MAX_CHILDREN_PER_CALL = 50

#: The most cells one authored table may carry. **larkdocio's own documented authoring cap,
#: not a discovered API ceiling** — and a SUPERSEDED one: the reason below is LD-135's,
#: preserved word for word; only its conclusion moved (LD-481). The rule it moved under is
#: the supersession rule — preserve the reason, replace only the conclusion.
#:
#: **The historical reason (LD-135, verbatim).** Lark auto-provisions the cell grid
#: from the table's ``row_size``/``column_size`` property, but each **non-empty** cell then
#: costs its own pair of throttled calls (read the cell to find its inner text block, patch
#: that block), so a grid's cost is linear in its cells at ≤3 writes/sec — a 200-cell table
#: is already ~400 serialized calls. That reasoning was sound and its conclusion was
#: ``MAX_TABLE_CELLS = 200``.
#:
#: **What changed (LD-481): the per-cell cost math, because the fill is now BATCHED.** The
#: premise the 200 rested on — *a pair of throttled calls per cell* — is no longer true of
#: this library's own construction. The fill reads every cell's inner block id from one
#: paginated document block list and writes the texts through
#: ``PATCH …/blocks/batch_update`` in runs of 48
#: (:data:`~larkdocio.write.client.MAX_BATCH_UPDATES_PER_CALL`), so a table costs
#: ``1 create + (rows − 9) grow + 1 list per 500 blocks + ⌈cells/48⌉ batch``. Measured on a
#: 6×36 grid, both ends on disposables: **463 write API calls / 158.41 s
#: before, 37 calls / 12.4 s after** — the cost is no longer linear in cells at 2 calls each,
#: so a cap budgeting for that cost is budgeting for a construction that no longer exists.
#:
#: **The new number is a MEASURED ANCHOR, not a budget guess.** 500 sits on Lark's own
#: one-call envelope for a table subtree: ``descendants = 2 × cells + 1``, and the
#: ``descendant`` route accepts **1000 descendants** and refuses 1001 — bisected at two
#: shapes, 1×499 text cells = 999 descendants ``code 0`` and 1×500 = 1001 descendants
#: ``99992402 field validation failed`` — i.e. **499 cells in one call**; the capture is kept
#: in the 2026-08-14 table-cell-creation spike, § 3b, whose write-up was retired on 2026-09-18.
#: 500 is that measured envelope rounded to the next hundred: it keeps the whole authored
#: grid inside one platform-sized unit of work.
#: **Route scope for every number above** (a claim is exactly as wide as its evidence): one tenant, ``tenant_access_token``, docx v1,
#: block type 31, on documents the spike created (not wiki-wrapped). ``user_access_token``,
#: other tenants and wiki-wrapped documents are **unmeasured, not refuted**.
#:
#: Past the cap the table is **refused with the cap named**, at construction and before any
#: network call, never truncated — that behaviour is unchanged and deliberately so.
MAX_TABLE_CELLS = 500

#: The most columns one table may carry — **a MEASURED Lark ceiling, not one of ours**
#: (LD-431). Growing a table past the create-time 9-column grid works column by column until
#: the **101st**, which answers ``1770010 "too many table column"`` in Lark's own words; the
#: 100th reads back ``column_size: 100`` — measured on a disposable the probe created and
#: trashed (the table-row-boundary probe, § 4, probe 04; its findings were retired on 2026-09-18).
#: Under :data:`MAX_TABLE_CELLS` a grid
#: can still *ask* for 101–200 columns at one row, and that window would fail **live**,
#: mid-batch, in a half-written document — the failure this cap exists to move to compile
#: time. There is deliberately **no row cap beside it**: the row axis grew to 200 (the cell
#: cap) with no refusal at any row, so a row cap would memorialise a limit that is not Lark's.
#: Measured on one tenant, ``tenant_access_token``, docx v1, block type 31; other tenants,
#: ``user_access_token`` and wiki-wrapped documents are **unmeasured**.
MAX_TABLE_COLUMNS = 100

#: The **one** spelling of "append at the end" on the docx block PATCH route's table-grow
#: operations — ``insert_table_row {"row_index": -1}`` / ``insert_table_column
#: {"column_index": -1}``. Spelled here and nowhere else in the package, so the value the
#: engine puts on the wire, the default a :class:`GrowTableRequest` carries, and the value its
#: refusal compares against cannot drift apart. (The precedent is
#: :data:`~larkdocio.write.model.applylog.INSERT_WRITE_CALLS_KEY`: a wire literal typed twice
#: is the ``STALE_SHEET`` defect waiting to happen.)
#:
#: **Why ``-1`` and not a computed last index:** it is the spelling that was MEASURED. On the
#: docx block PATCH route it appends at the end and leaves every pre-existing cell id untouched
#: and in order — recorded in :func:`larkdocio.write.apply._grow_table_grid`'s own docstring,
#: which names the captures it was taken from. Any other index is **unmeasured** from this
#: tree, neither refuted nor supported.
APPEND_ROW_INDEX = -1


class NewBlockKind(Enum):
    """The **closed** set of block kinds a consumer may bring into existence.

    Exactly the Markdown-expressible set: a heading (levels 1–9 — Lark's
    heading1..heading9), a paragraph, the three list-item kinds (bullet / ordered / todo,
    each nestable), a code block, a quote, a **table** (an R×C grid of
    cell contents with an optional header row; merged cells are inexpressible, see
    :meth:`NewBlock.table`) — and a **mermaid diagram** (:meth:`NewBlock.mermaid`), the
    reader's own ```` ```mermaid ```` projection made authorable so the round trip closes.

    Closed-ness is the safety property, inherited from :class:`NewParagraph`, and it is a
    statement about **larkdocio's authoring surface** rather than about API hostility: the
    types this library does not author (image / board / embed / bitable / sheet) have **no
    kind**, and :class:`NewBlock` carries no token, url or document reference, so they stay
    **inexpressible by construction** rather than refused at runtime. A kind is admitted
    only on evidence, which is exactly how ``MERMAID`` got here — **mermaid (docx type 40)
    is creatable by the API**, proven by a probe against the live API (a specimen-shaped
    ``add_ons`` create is accepted ``code 0``), so calling it hostile was false; it is also
    the one kind whose payload is not text elements. Whether any *remaining* type becomes
    authorable is likewise larkdocio's design choice on evidence; **nothing is claimed here
    about bitable (18) or sheet (30)**, which that probe never touched.

    The ``value`` string is the stable serialized form (the ``"kind"`` discriminator).
    """

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    BULLET = "bullet"
    ORDERED = "ordered"
    TODO = "todo"
    CODE = "code"
    QUOTE = "quote"
    TABLE = "table"
    MERMAID = "mermaid"


#: The three kinds that may carry ``children`` — nesting is a *list* structure in this
#: rung. A paragraph / heading / code / quote with children is refused rather than
#: silently flattened.
_NESTABLE_KINDS = (NewBlockKind.BULLET, NewBlockKind.ORDERED, NewBlockKind.TODO)

#: The kinds a :class:`TextSpan` sequence may author. Every kind whose Markdown
#: projection is *inline* text, which is the whole of what a link anchor can survive. The
#: three that are absent are absent for reasons a reader can check rather than by taste:
#: ``CODE``'s projection is a **fence** (verbatim content — the reader emits no ``[…](…)``
#: inside one, so an anchor there is a silent content drop), ``MERMAID``'s payload is a JSON
#: record and not text elements at all, and ``TABLE``'s content lives in ``rows``.
#:
#: **``TABLE``'s absence here is NOT the absence of an in-cell anchor (LD-619).** Its reason
#: is unchanged — a table's content lives in ``rows``, so the block-level carrier is the wrong
#: place for one — and only the conclusion moved: a **cell** may itself be a sequence of
#: :class:`TextSpan`, which is where an anchored link inside a table is authored. Lark accepts
#: and stores that run on **both** write routes — measured: the capture is
#: in the source repository (``tests/captures/ld517-in-cell-link/``) and the ruling
#: followed from it: the anchor ships on both routes.
_SPANNABLE_KINDS = (
    NewBlockKind.PARAGRAPH,
    NewBlockKind.HEADING,
    NewBlockKind.BULLET,
    NewBlockKind.ORDERED,
    NewBlockKind.TODO,
    NewBlockKind.QUOTE,
)


#: The TERMINATING sentence, shared by both link-URL refusals (LD-670).
#:
#: The two validators below are each defensible alone and their COMPOSITION was a trap: the
#: percent-encoded refusal advised the decoded spelling, the whitespace refusal advised a
#: spelling with no whitespace in it, and for a URL whose encoding HIDES whitespace (``%20`` —
#: what every browser produces for a space) each one's advice was the other one's input. A
#: caller was ping-ponged between two refusals and was never told the truth: that no spelling
#: of that URL can be authored as a link anchor here. Executed at the pin, both directions.
#:
#: So the fact is stated ONCE and carried by BOTH messages, because a caller can arrive from
#: either side — passing ``a%20b`` (the whitespace check does not fire, the percent one does)
#: or passing ``a b`` (the whitespace check fires first, and a caller who then re-encodes in
#: good faith lands in the loop from the other side). It is deliberately not a third validator:
#: the refusal SET does not move, only what it tells you.
#:
#: The scope is exactly "the percent-DECODED spelling contains whitespace" and nothing wider.
#: ``%2D`` and every other encoding whose decoding is whitespace-free keeps the message it has
#: always had, byte for byte, because there the advice is correct — the raw spelling is a real,
#: authorable URL and a click confirmed it opens.
UNAUTHORABLE_WHITESPACE_URL_ADVICE = (
    "NO spelling of this URL can be authored as a link anchor here: the raw one carries "
    "whitespace, which ends the reader's [anchor](url) projection at the space, and the "
    "percent-encoded one is refused because the reader percent-DECODES it straight back to "
    "the raw one. Two things do work: link to a space-free URL for the same resource (a "
    "redirect, or a shortened URL), or author the URL as PLAIN TEXT rather than as an anchor."
)


@dataclass(frozen=True)
class TextSpan:
    """One run of authored text, optionally carrying a **link URL**.

    The typed shape behind *"For the full details, **open the attached file**"* — a sentence
    whose anchor text is not the URL. A span with no ``link_url`` is exactly the unstyled run
    this library has always created; a span **with** one encodes to
    ``text_element_style.link.url`` on the created ``text_run``, which is the shape Lark
    stored and read back verbatim in one call
    (media-spike captures 541 / 542, since retired on 2026-09-18).

    **THE URL IS AUTHORED VERBATIM, AND THAT SPELLING IS PINNED BY A CLICK.** Lark stores a
    link URL **exactly as sent** — the raw and the percent-encoded spellings were both
    accepted and both echoed back unchanged — so the server does not settle which one a
    caller should send. What settles it is a **human click** on the media spike's living
    fixture (2026-08-12; the media spike's findings note recording it was retired on 2026-09-18): the
    **raw** spelling opens the file in a new tab, both link-wrapped and bare. So this library
    sends what it is given, unencoded, and **refuses a percent-encoded spelling** rather than
    silently normalising one — because the reader's own
    :func:`larkdocio.common.url.unescape_url` percent-**decodes** a link URL on the way back
    out, so an encoded spelling would not survive the round trip through the reader's
    Markdown. That is a round-trip fact about this library, **not** a claim that Lark refuses
    it: Lark accepts it, and the capture says so.

    **Unmeasured, not refuted:** which spelling the *mobile* and *desktop* clients honour,
    and every tenant and region other than the one the click was made in.
    """

    text: str
    link_url: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.text, str):
            raise TypeError(
                f"TextSpan.text must be a str, got {type(self.text).__name__}")
        if not self.text:
            raise ValueError(
                "a TextSpan needs non-empty text — an empty run authors nothing, and an "
                "empty ANCHOR authors a link a reader cannot click. Drop the span instead")
        if self.link_url is None:
            return
        url = self.link_url
        if not isinstance(url, str):
            raise TypeError(
                f"TextSpan.link_url must be a str, got {type(url).__name__}")
        if not url:
            raise ValueError(
                "a TextSpan's link_url is empty — an anchor pointing nowhere is a dead "
                "link, not a link. Pass link_url=None for plain text")
        if any(ch.isspace() for ch in url):
            raise ValueError(
                f"the link URL {url!r} carries whitespace, and the reader's own Markdown "
                f"projection of a linked run is [anchor](url) — a space inside the "
                f"parentheses ends the link there. Nothing is encoded on your behalf: pass "
                f"a URL with no whitespace in it. "
                f"{UNAUTHORABLE_WHITESPACE_URL_ADVICE}")
        decoded = urllib.parse.unquote(url)
        if decoded != url:
            # One preamble, two endings. The REASON is unchanged and is stated the same way
            # whichever ending follows it; what changes is whether the advice that closes it
            # is a spelling this constructor would itself refuse.
            preamble = (
                f"the link URL {url!r} is PERCENT-ENCODED, and this library authors a link "
                f"URL VERBATIM. Lark itself accepts both spellings and echoes each back "
                f"unchanged (measured), so the server does not settle this; what settles it "
                f"is that the reader percent-DECODES a link URL on the way back out "
                f"(larkdocio.common.url.unescape_url), so an encoded spelling does not "
                f"survive the round trip through the reader's own Markdown. The raw "
                f"spelling is the one a click confirmed opens.")
            if any(ch.isspace() for ch in decoded):
                raise ValueError(f"{preamble} {UNAUTHORABLE_WHITESPACE_URL_ADVICE}")
            raise ValueError(f"{preamble} Pass the URL undecorated: {decoded!r}")

    def to_dict(self) -> dict:
        d = {"text": self.text}
        if self.link_url is not None:
            d["link_url"] = self.link_url
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TextSpan":
        return cls(text=d["text"], link_url=d.get("link_url"))


def _normalized_cell(cell):
    """One table cell, frozen: a ``str`` unchanged, a span sequence as a tuple (LD-619).

    A **list** of :class:`TextSpan` from a caller becomes a tuple, so a built plan cannot be
    edited out from under itself. Anything else is returned **untouched** — the per-cell
    refusal in :meth:`NewBlock._validate_table` names its row and column, which a
    ``TypeError`` raised from inside a comprehension could not.
    """
    if isinstance(cell, str):
        return cell
    if isinstance(cell, (list, tuple)):
        return tuple(cell)
    return cell


def _cell_to_wire(cell):
    """A cell in the JSON record: a string stays a string, a rich cell a list of spans."""
    if isinstance(cell, str):
        return cell
    return [span.to_dict() for span in cell]


def _cell_from_wire(cell):
    """The inverse of :func:`_cell_to_wire` — a plan is approved out of process, so a rich
    cell that could not survive the record would be a cell that vanishes between the
    preview and the apply."""
    if isinstance(cell, str):
        return cell
    if isinstance(cell, (list, tuple)):
        return tuple(TextSpan.from_dict(span) if isinstance(span, dict) else span
                     for span in cell)
    return cell

#: The kinds that are a **marker plus content** — with no text the reader would emit a
#: bare marker carrying nothing, so empty text is refused. A paragraph (a blank line) and
#: a code block (an empty fence) are content-only and may legitimately be empty.
#:
#: ``MERMAID`` is here for a **different, measured reason** (LD-192's probe § 8): Lark accepts
#: an empty diagram source ``code 0`` and stores it, and the reader then emits **nothing at
#: all** for it — no fence, no marker — so an empty source authors a block that is invisible
#: in Markdown. That is a silent content drop, which the authoring doctrine forbids.
_TEXT_REQUIRED_KINDS = (
    NewBlockKind.HEADING,
    NewBlockKind.BULLET,
    NewBlockKind.ORDERED,
    NewBlockKind.TODO,
    NewBlockKind.QUOTE,
    NewBlockKind.MERMAID,
)

#: Lark ships heading1..heading9 and nothing else, so this is the whole level range.
#: (Markdown defines only H1–H6; the reader emits 7–9 literal ``#`` for H7–H9 — faithful
#: to the source's depth, and documented in the source repository in BLOCKS.md § Notes.)
_MIN_HEADING_LEVEL, _MAX_HEADING_LEVEL = 1, 9


@dataclass(frozen=True)
class NewBlock:
    """One typed block to create — the creatable-content family.

    A single frozen value with a **closed** :class:`NewBlockKind` discriminator plus the
    per-kind attributes that kind needs, rather than seven sibling classes: one type is
    what the ``InsertRequest.content`` union, the plan wire format, the
    ``capabilities()`` floor projection and a consumer's ``isinstance`` check all see, and
    a closed enum is what keeps hostile types inexpressible.

    Fields (each validated against ``kind`` — a mismatch is refused at construction, so an
    impossible block never reaches a plan, let alone a write):

    * ``kind`` — which block to create;
    * ``text`` — its plain, **unstyled** text. Shipped **verbatim**: MD metacharacters in
      authored text are *content*, and escaping them is the reader's job on the way back
      out, never the encoder's on the way in;
    * ``level`` — the heading level, **required for and only for** ``HEADING``, in 1–9;
    * ``language`` — the Markdown fence token for ``CODE`` only (``None`` ⇒ plain text);
      an unknown token is refused, never silently downgraded;
    * ``done`` — the checkbox state for ``TODO`` only;
    * ``children`` — nested :class:`NewBlock` s, for the three list kinds only, to
      :data:`MAX_NEST_DEPTH` deep and :data:`MAX_CHILDREN_PER_CALL` wide per group;
    * ``rows`` — the **R×C grid of cells**, row-major, for ``TABLE`` only (its cell
      content lives here, not in ``text``), to :data:`MAX_TABLE_CELLS` cells. A cell is a
      ``str`` (plain text) or a sequence of :class:`TextSpan` carrying an anchored link
      — never both, and nothing else;
    * ``header_row`` — for ``TABLE`` only: promote row 0 to the table's header row
      (unset ⇒ ``True``, matching Lark's own create default *and* the reader's read
      default — see :meth:`table` for why that is the honest default here);
    * ``theme`` — for ``MERMAID`` only: the diagram's render theme, one of
      :data:`larkdocio.mermaid.ruleset.THEMES` (unset ⇒ ``"default"``, the value a
      hand-typed block carries). Off-whitelist is refused — see :meth:`mermaid`.

    Frozen and JSON-round-trippable (``kind``-tagged, so one dispatcher tells it from the
    tagless :class:`NewParagraph`). Dumb typed data: it encodes nothing and writes nothing
    — :mod:`larkdocio.write.encode` turns it into a Lark payload and only the gated
    ``dry_run`` → ``Plan`` → ``apply`` chain sends one.
    """

    kind: NewBlockKind
    text: str = ""
    level: Optional[int] = None
    language: Optional[str] = None
    done: bool = False
    children: Tuple["NewBlock", ...] = ()
    rows: Tuple[Tuple[str, ...], ...] = ()
    header_row: Optional[bool] = None
    theme: Optional[str] = None
    spans: Tuple["TextSpan", ...] = ()

    def __post_init__(self):
        kind = self.kind
        if not isinstance(kind, NewBlockKind):
            # accept the serialized form so from_dict/JSON stay one code path
            kind = NewBlockKind(kind)
            object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "children", tuple(self.children))
        object.__setattr__(self, "spans", tuple(self.spans))
        self._validate_spans(kind)
        # A frozen value cannot hold a mutable grid a consumer could edit out from under
        # a built plan, so rows are normalized to tuples-of-tuples on the way in — and a
        # RICH cell (a sequence of TextSpan, LD-619) is frozen to a tuple for the same
        # reason. A cell that is neither is left exactly as it arrived, so
        # :meth:`_validate_table` can name its row and column instead of raising a
        # TypeError from inside a comprehension.
        object.__setattr__(self, "rows", tuple(
            tuple(_normalized_cell(cell) for cell in row) for row in self.rows))
        if kind is NewBlockKind.TABLE:
            # unset ⇒ the documented default (promote row 0), so the resolved value is
            # always a real bool from here on — nothing downstream re-derives it.
            object.__setattr__(
                self, "header_row",
                True if self.header_row is None else bool(self.header_row),
            )

        if not isinstance(self.text, str):
            raise TypeError(
                f"NewBlock.text must be a str, got {type(self.text).__name__}"
            )
        if kind is NewBlockKind.TABLE:
            self._validate_table()
        else:
            if self.rows:
                raise ValueError(
                    f"rows are meaningful only for a table block; a {kind.value} block "
                    f"cannot carry a {len(self.rows)}-row grid"
                )
            if self.header_row is not None:
                raise ValueError(
                    f"header_row is meaningful only for a table block; a {kind.value} "
                    f"block cannot carry header_row={self.header_row!r}"
                )
        if kind in _TEXT_REQUIRED_KINDS and not self.text.strip():
            raise ValueError(
                f"a {kind.value} block needs non-empty text — it is a marker plus "
                f"content, and a bare marker carries nothing. (A paragraph or a code "
                f"block may be empty.)"
            )

        if kind is NewBlockKind.HEADING:
            if not isinstance(self.level, int) or isinstance(self.level, bool):
                raise ValueError(
                    "a heading block needs an integer level in "
                    f"{_MIN_HEADING_LEVEL}..{_MAX_HEADING_LEVEL} (Lark ships "
                    f"heading1..heading9); got level={self.level!r}"
                )
            if not _MIN_HEADING_LEVEL <= self.level <= _MAX_HEADING_LEVEL:
                raise ValueError(
                    f"heading level {self.level} is outside "
                    f"{_MIN_HEADING_LEVEL}..{_MAX_HEADING_LEVEL} — Lark ships "
                    f"heading1..heading9 (block types 3–11) and no deeper level exists"
                )
        elif self.level is not None:
            raise ValueError(
                f"level is meaningful only for a heading block; a {kind.value} block "
                f"cannot carry level={self.level!r}"
            )

        if kind is NewBlockKind.CODE:
            if self.language is not None and self.language not in MD_LANG_TO_DOCX_CODE:
                raise ValueError(
                    f"unknown code language {self.language!r} — Lark has no enum for it. "
                    f"Use one of larkdocio.langs.supported_code_languages(), or None for "
                    f"a plain fence (it is never silently downgraded)."
                )
        elif self.language is not None:
            raise ValueError(
                f"language is meaningful only for a code block; a {kind.value} block "
                f"cannot carry language={self.language!r}"
            )

        if self.done and kind is not NewBlockKind.TODO:
            raise ValueError(
                f"done is meaningful only for a todo block; a {kind.value} block cannot "
                f"carry done=True"
            )

        if kind is NewBlockKind.MERMAID:
            self._validate_mermaid()
        elif self.theme is not None:
            raise ValueError(
                f"theme is meaningful only for a mermaid block; a {kind.value} block "
                f"cannot carry theme={self.theme!r}"
            )

        if self.children:
            if kind not in _NESTABLE_KINDS:
                raise ValueError(
                    f"a {kind.value} block cannot carry children — nesting is a list "
                    f"structure in this rung (bullet / ordered / todo). Insert the "
                    f"blocks as siblings instead; they are never silently flattened."
                )
            if any(child.kind is NewBlockKind.TABLE for child in self.children):
                raise ValueError(
                    f"a table cannot be nested inside a {kind.value} block — Markdown "
                    f"cannot express a table inside a list item either, and the create "
                    f"path authors a table as a top-level block. Insert the table as a "
                    f"sibling instead; it is never silently relocated."
                )
            if len(self.children) > MAX_CHILDREN_PER_CALL:
                raise ValueError(
                    f"{len(self.children)} nested children exceeds the "
                    f"{MAX_CHILDREN_PER_CALL}-per-call limit of the docx create-children "
                    f"endpoint (one sibling group is one call) — split the authoring "
                    f"into batches"
                )
            if self.depth > MAX_NEST_DEPTH:
                raise ValueError(
                    f"nesting depth {self.depth} exceeds the documented cap of "
                    f"{MAX_NEST_DEPTH} levels (each level costs its own throttled "
                    f"create-children call) — split the authoring into batches; the "
                    f"engine never silently flattens a deeper tree"
                )

    # -- the span sequence's own validation (LD-434) ----------------------------- #

    def _validate_spans(self, kind: "NewBlockKind") -> None:
        """Refuse spans where a link cannot survive, and DERIVE ``text`` from them.

        ``text`` stays the block's **plain-text projection** — every existing reader of a
        :class:`NewBlock` (the preview, the refusal messages, the reconciler) keeps working
        unchanged, because ``spans`` adds a layer rather than replacing the field. A caller
        who supplies both must supply the same string twice; a disagreement is refused rather
        than resolved by a precedence rule nobody would remember.
        """
        if not self.spans:
            return
        for span in self.spans:
            if not isinstance(span, TextSpan):
                raise TypeError(
                    f"NewBlock.spans holds TextSpan values, got "
                    f"{type(span).__name__}")
        if kind is NewBlockKind.TABLE:
            # TRANSFORMED, never deleted (LD-619). The REASON is the original and is
            # unchanged: a table's content lives in ROWS, so a span sequence hung on the
            # table BLOCK addresses nothing and would be a silent content drop. Only the
            # CONCLUSION moved — this used to be the whole answer to "can a table carry an
            # anchored link", and the answer is now yes, in the CELL. What the refusal
            # protects is what it always protected: this library does not silently emit
            # content that lands nowhere.
            raise ValueError(
                "a table block cannot carry spans: a table's content lives in rows, so a "
                "span sequence on the table block itself addresses no cell and would be a "
                "silent content drop. An anchored link INSIDE a table cell IS authorable — "
                "pass that cell as a sequence of TextSpan in rows=, e.g. "
                "NewBlock.table([[\"On-time delivery\", (TextSpan(\"Method note\", link_url=url),)]])"
            )
        if kind not in _SPANNABLE_KINDS:
            raise ValueError(
                f"a {kind.value} block cannot carry spans: its Markdown projection is not "
                f"inline text (a code block is a verbatim fence, a mermaid diagram is a "
                f"JSON record), so an anchored link on it would be a silent content drop. "
                f"The kinds that can: "
                f"{', '.join(k.value for k in _SPANNABLE_KINDS)}"
            )
        joined = "".join(span.text for span in self.spans)
        if self.text and self.text != joined:
            raise ValueError(
                f"NewBlock.text and NewBlock.spans disagree: the spans spell "
                f"{joined!r} and text says {self.text!r}. text is the plain-text "
                f"PROJECTION of the spans — leave it unset and it is derived"
            )
        object.__setattr__(self, "text", joined)

    # -- the table grid's own validation (LD-135) -------------------------------- #

    def _validate_table(self) -> None:
        """Refuse anything that is not a plain, non-empty, rectangular grid of strings.

        The **merge refusal** is the load-bearing one (AC4): rows of
        differing width are exactly what a merged (colspan / rowspan) table produces, and
        Markdown has no span syntax — so the request is refused with the typed
        :meth:`~larkdocio.write.model.Refusal.merge_not_expressible` refusal (carried by
        :class:`~larkdocio.write.model.RefusedError`) rather than **padded or truncated
        into shape**, which would silently invent or drop content. The remaining checks
        (empty grid, non-string cell, stray ``text``/``children``, the cell cap) are the
        LD-134 construction-refusal discipline applied to the grid.
        """
        if self.text:
            raise ValueError(
                "a table block carries its content in rows, not text — a table's `text` "
                f"would be silently dropped at encode time; got text={self.text!r}"
            )
        if not self.rows:
            raise ValueError(
                "a table block needs at least one row of cells (an empty table has no "
                "grid for Lark to provision)"
            )
        if any(len(row) == 0 for row in self.rows):
            raise ValueError(
                "every table row needs at least one column (a zero-width row has no "
                "cell to author)"
            )

        width = len(self.rows[0])
        for r, row in enumerate(self.rows):
            if len(row) != width:
                raise RefusedError(Refusal.merge_not_expressible(
                    detail=(
                        f"row {r} has {len(row)} cells but the table's first row has "
                        f"{width} — an authored table must be a plain rectangular grid. "
                        f"Markdown has no colspan/rowspan, so a MERGED cell is not "
                        f"expressible (documented lossiness): give every row {width} "
                        f"cells (use an empty string for a blank cell). The grid is never "
                        f"padded or truncated to fit."
                    )
                ))
            for c, cell in enumerate(row):
                if isinstance(cell, str):
                    continue
                # SUPERSEDED IN PART (LD-619). The REASON below is the original and is
                # unchanged — a cell that is neither plain text nor a typed span sequence is
                # content this library has no way to encode, and refusing it at construction
                # is cheaper than discovering it mid-batch. Only the CONCLUSION moved: a
                # cell may ALSO be a sequence of TextSpan, because Lark accepts and stores a
                # link-carrying run inside a cell on both write routes (measured —
                # in the source repository: tests/captures/ld517-in-cell-link/captures/001-in-cell-link-readback.json).
                if not isinstance(cell, tuple) or not all(
                        isinstance(span, TextSpan) for span in cell):
                    raise ValueError(
                        f"table cell at row {r} / column {c} must be a str (plain cell "
                        f"text) or a sequence of TextSpan (a cell carrying an anchored "
                        f"link); got {type(cell).__name__}"
                    )
                if not cell:
                    raise ValueError(
                        f"table cell at row {r} / column {c} is an empty span sequence, "
                        f"which authors nothing — use \"\" for a deliberately blank cell. "
                        f"A rich cell needs at least one span"
                    )

        cells = len(self.rows) * width
        if cells > MAX_TABLE_CELLS:
            raise ValueError(
                f"{len(self.rows)}×{width} = {cells} cells exceeds the "
                f"{MAX_TABLE_CELLS}-cell authoring cap. That cap is **larkdocio's own**, "
                f"anchored on a measured platform envelope: Lark takes a table subtree of "
                f"499 cells (1000 descendants) in one call and refuses 1001, so the cap "
                f"keeps an authored grid inside one platform-sized unit of work. It is NOT "
                f"one of Lark's own ceilings — those are 100 columns (Lark's own words, "
                f"1770010 \"too many table column\") and no row cap has ever been observed. "
                f"Split the authored grid into tables of 500 cells or fewer — e.g. "
                f"{MAX_TABLE_CELLS // width if width else 0} rows at {width} columns — and "
                f"author them one after another; the grid is never truncated"
            )
        # The cell cap is checked FIRST on purpose: it is the older, broader refusal, and a
        # grid that trips both keeps the label it has always refused under (zero drift).
        if width > MAX_TABLE_COLUMNS:
            raise ValueError(
                f"a table of {width} columns exceeds the measured {MAX_TABLE_COLUMNS}-"
                f"column cap — Lark refuses the {MAX_TABLE_COLUMNS + 1}st column itself "
                f"(1770010 \"too many table column\"), so this refusal fires here rather "
                f"than mid-write against a half-authored document. Split the table into "
                f"two of ≤{MAX_TABLE_COLUMNS} columns; it is never truncated. (There is no "
                f"row cap: the row axis is not limited this way.)"
            )

    # -- the diagram's own validation (LD-192) ----------------------------------- #

    def _validate_mermaid(self) -> None:
        """Refuse a theme the renderer does not know — **the only guard there is**.

        The load-bearing fact behind the strictness (LD-192's probe § 8, measured on a
        disposable): **the server validates nothing inside the record.** ``theme: "wobbly"``
        is accepted ``code 0`` and *kept*; so is a ``view`` that is not a view, an unknown
        extra key, and Mermaid that is not Mermaid. Lark will happily store a diagram it
        cannot draw. So a rule that is not enforced here is a rumor with nothing behind it
        server-side, and the whitelist is refused rather than warned about.

        The whitelist itself is :data:`larkdocio.mermaid.ruleset.THEMES` — **the compiler's
        own constant**, imported rather than re-listed, so the authoring surface and the
        compiler cannot come to disagree about which themes exist.
        """
        from larkdocio.mermaid.ruleset import THEMES

        if self.theme is not None and self.theme not in THEMES:
            raise ValueError(
                f"unknown mermaid theme {self.theme!r} — Lark's renderer knows "
                f"{len(THEMES)}: {', '.join(THEMES)}. It is refused rather than passed "
                f"through because the server validates NOTHING inside a diagram's record "
                f"(an unknown theme is stored as sent and then simply fails to render), so "
                f"this whitelist is the only guard there is."
            )

    @property
    def row_count(self) -> int:
        """A table's row count (``0`` for any other kind)."""
        return len(self.rows)

    @property
    def column_count(self) -> int:
        """A table's column count — its rows are rectangular by construction."""
        return len(self.rows[0]) if self.rows else 0

    @property
    def depth(self) -> int:
        """This block's own nesting depth — 1 for a leaf, 1 + the deepest child.

        A table is always a leaf: its cells are Lark's to provision (they are not
        ``children``), so a grid never deepens the nesting a create chain must walk.
        """
        return 1 + max((c.depth for c in self.children), default=0)

    # -- the per-kind constructors (readable at a call site) -------------------- #

    @classmethod
    def paragraph(cls, text: str) -> "NewBlock":
        """A plain paragraph (block type 2) — the ``NewParagraph`` equivalent."""
        return cls(kind=NewBlockKind.PARAGRAPH, text=text)

    @classmethod
    def rich_paragraph(cls, spans) -> "NewBlock":
        """A paragraph authored as a sequence of :class:`TextSpan` s.

        The shape that authors *"For the full details, **open the attached file**"* — a
        sentence whose **anchor text is not the URL**::

            NewBlock.rich_paragraph((
                TextSpan("For the full details, "),
                TextSpan("open the attached file", link_url=uploaded.url),
            ))

        A span carrying ``link_url`` becomes a created ``text_run`` with
        ``text_element_style.link.url``; a span without one is exactly the unstyled run this
        library has always created. The block's ``text`` is **derived** as the concatenation,
        so everything that reads a :class:`NewBlock`'s plain text keeps working.

        **This opens the LINK anchor and nothing else.** Bold, italic, strikethrough, inline
        code and colour on a created run stay unauthorable — they are not fields on a
        :class:`TextSpan`, so they are inexpressible here by construction rather than refused
        at runtime, exactly as the closed :class:`NewBlockKind` enum makes an unauthored
        block type inexpressible.

        The **Markdown compiler** (:func:`larkdocio.write.compose.compose`) still refuses
        ``[text](url)``: this typed shape is deliberately not reached through the dialect,
        because the round-trip property against the reader's own Markdown is what that
        refusal protects. See :data:`larkdocio.write.compose.NOT_EXPRESSIBLE_CONSTRUCTS`.
        """
        spans = tuple(spans)
        if not spans:
            raise ValueError(
                "a rich paragraph needs at least one span — an empty sequence authors "
                "nothing. Use NewBlock.paragraph('') for a deliberately blank paragraph")
        return cls(kind=NewBlockKind.PARAGRAPH, spans=spans)

    @classmethod
    def heading(cls, level: int, text: str) -> "NewBlock":
        """A heading at ``level`` 1–9 (Lark heading1..heading9 ⇒ block types 3–11)."""
        return cls(kind=NewBlockKind.HEADING, text=text, level=level)

    @classmethod
    def bullet(cls, text: str, children: Tuple["NewBlock", ...] = ()) -> "NewBlock":
        """A bullet list item (block type 12), optionally parenting nested items."""
        return cls(kind=NewBlockKind.BULLET, text=text, children=children)

    @classmethod
    def ordered(cls, text: str, children: Tuple["NewBlock", ...] = ()) -> "NewBlock":
        """An ordered list item (block type 13). Lark computes the ordinal from the
        item's position among its consecutive ordered siblings — there is no number to
        author (and authoring one would let it disagree with the document)."""
        return cls(kind=NewBlockKind.ORDERED, text=text, children=children)

    @classmethod
    def todo(cls, text: str, done: bool = False,
             children: Tuple["NewBlock", ...] = ()) -> "NewBlock":
        """A todo/checkbox list item (block type 17) in either done state."""
        return cls(kind=NewBlockKind.TODO, text=text, done=done, children=children)

    @classmethod
    def code(cls, text: str, language: Optional[str] = None) -> "NewBlock":
        """A code block (block type 14).

        ``language`` is a **Markdown fence token** (``"python"``, ``"go"``, …) — one of the
        **65** tokens :func:`larkdocio.langs.supported_code_languages` lists — mapped to
        Lark's enum at encode time. An unknown token is refused here, **not** downgraded.

        **``language=None`` is a first-class choice, not an omission** (and it is the
        default): it authors a **bare fence**, which is the *correct* choice whenever the
        content is **not code** — ASCII art, a directory tree, a log excerpt, plain
        preformatted text. Reach for it instead of forcing a near-miss token: Lark has no
        ``plaintext``/``text`` enum, so a wrong token is a wrong claim about the content,
        while a bare fence is exactly what the reader emits back for it.

        The body is **verbatim in both directions** — every line's leading
        whitespace, whitespace-only lines and trailing whitespace survive the round trip —
        so an indented snippet or an ASCII diagram comes back byte for byte.
        """
        return cls(kind=NewBlockKind.CODE, text=text, language=language)

    @classmethod
    def quote(cls, text: str) -> "NewBlock":
        """A quote block (block type 15)."""
        return cls(kind=NewBlockKind.QUOTE, text=text)

    # The in-cell LINK ANCHOR is LD-619, on LD-517's measurement. The
    # docstring below states the capability and its scope without either reference: a
    # consumer has only the wheel, and an issue id resolves to nothing there.
    @classmethod
    def table(cls, rows, header_row: bool = True) -> "NewBlock":
        """A table (block type 31) as an **R×C grid of cell texts**, row-major.

        ``rows`` is any iterable of iterables of cells — ``[["Metric", "Value"],
        ["On-time delivery", "97.2%"]]`` — held as tuples. **A cell is either a ``str``
        (plain text) or a sequence of :class:`TextSpan`**, which is how a cell carries an
        **anchored link**::

            NewBlock.table([
                ["Metric", "Owner", "Detail"],
                ["On-time delivery", "Logistics",
                 (TextSpan("Method note", link_url=url),)],
            ])

        ``header_row`` (**default True**) promotes row 0 to the table's header row. True is
        the default because it is what **both ends already do**: Lark's editor promotes the
        first row, and the reader's documented rule is that an *absent* ``header_row``
        renders as promoted. ``header_row=False`` **is** expressible and **is** stored by
        Lark (live-verified: a table created with ``false`` comes back with the flag absent,
        while one created with ``true`` comes back ``header_row: true``) — but Lark **omits a
        false flag** from the block payload, and the reader cannot tell "absent" from
        "false", so a headerless authored table still **reads back through Markdown with row
        0 promoted**. That asymmetry is *documented lossiness in the Markdown projection*,
        not a lost write, and it is the reason the default is True rather than a distinction
        the round-trip cannot show.

        Cell text is shipped **verbatim** exactly as any other kind's text — MD
        metacharacters in a cell are *content*, and the reader escapes them on the way back
        out.

        **THE ONE STYLING A CELL CAN CARRY IS THE LINK ANCHOR, and that is a measurement
        rather than a preference.** Lark **accepts and stores** a ``text_run`` carrying
        ``text_element_style.link.url`` inside a docx table cell, on **both** write routes —
        the atomic ``descendant`` create and the create-grow-fill ``batch_update`` — read
        back fresh rather than inferred from a create's ``code:0``, and shape-identical to the
        same run in a plain paragraph
        — the measurement is kept in the source repository at ``tests/captures/ld517-in-cell-link/captures/001-in-cell-link-readback.json``.
        Bold, italic, strikethrough,
        inline code, underline and colour in a cell are **not** fields on a
        :class:`TextSpan`, so they are inexpressible here **by construction** rather than
        refused at runtime — and that is deliberate: the measurement covered a **link**, and
        nothing else may be shipped on the strength of it.

        **SUPERSEDED IN PART, reason preserved.** This used to say a cell holds
        plain text and *"there is no carrier for a styled run, a link anchor or a nested
        list inside a cell"*. The **reason** stands and still describes the EDIT path: an
        :class:`EditRequest` anchored by a :class:`TableLocator` takes a ``replacement``
        typed ``str`` — one whole cell of plain text, exactly-one-or-refuse — and
        :class:`SubSpanEditRequest`, the only family that edits *within* a block, takes a
        :data:`NarrativeAnchor` (*"a sub-span within a table cell is out of scope this
        tranche"*). **So an anchor is authored when the cell is CREATED, and a later
        whole-cell patch replaces it with plain text.** A nested list inside a cell is still
        not authorable at all.

        **Merged cells are not expressible**. Markdown has no
        colspan/rowspan, so an authored table is always a plain grid: there is no span
        field to ask for one, and a **ragged** grid — the shape a merged table produces —
        is refused with the typed
        :meth:`~larkdocio.write.model.Refusal.merge_not_expressible` refusal (a
        :class:`~larkdocio.write.model.RefusedError`), never padded into shape. Reading a
        merged table is unaffected (the reader's own job — it emits HTML for those).

        Bounded by :data:`MAX_TABLE_CELLS`; a bigger grid is refused with the cap named.
        """
        return cls(
            kind=NewBlockKind.TABLE,
            rows=tuple(tuple(row) for row in rows),
            header_row=header_row,
        )

    @classmethod
    def mermaid(cls, source: str, theme: Optional[str] = None) -> "NewBlock":
        """A **Mermaid diagram** (docx block type 40 — an ``add_ons`` block).

        ``source`` is **already-compiled Mermaid text**, exactly what the reader emits inside
        its ```` ```mermaid ```` fence. Compile a structured spec to that text with
        :func:`larkdocio.mermaid.flowchart` / :func:`larkdocio.mermaid.sequence` (which
        enforce the dialect Lark's renderer accepts), or hand over source you already have.
        The seam between the two halves is deliberately just a ``str``.

        ``theme`` is one of :data:`larkdocio.mermaid.ruleset.THEMES`; unset ⇒ ``"default"``,
        the value a hand-typed block carries. An off-whitelist theme is **refused**, because
        the server validates nothing inside the record and would store an unrenderable
        diagram silently.

        **CREATE-ONLY — there is no in-place update, and that is an API fact, not a
        deferral.** The docx block-patch surface carries **no ``add_ons`` updater** (17
        update descriptors, none of them ``add_ons``; three plausible field spellings each
        refused ``1770001 invalid param``, live). Editing a diagram's source therefore means
        **delete the block and create a new one at the same index** — proven end to end, and
        it **changes the ``block_id``**. Two consequences worth stating once, plainly:

        * a :class:`DeleteRequest` + an :class:`InsertRequest` is the *whole* recipe; larkdocio
          invents no ``add_ons`` updater to hide the shape of the operation;
        * **caching a type-40 block id across an edit is unsound** — any anchor held over a
          diagram edit is stale by construction, so re-resolve after one.

        An **empty** source is refused: Lark accepts it and the reader then emits nothing at
        all for it, so it would author a block that is invisible in Markdown.

        Every claim above was measured against the live API on throwaway documents, and the
        captures behind it are committed in the development repository (not in this wheel).
        """
        return cls(kind=NewBlockKind.MERMAID, text=source, theme=theme)

    # -- serialization (kind-tagged, so NewParagraph stays tagless) ------------- #

    def to_dict(self) -> dict:
        """The wire form: ``kind`` + ``text``, then only the fields that kind uses.

        Emitting only the relevant fields keeps the record readable in a consumer's
        approval UX and makes the round-trip exact (an absent field is the default).
        """
        d: dict = {"kind": self.kind.value, "text": self.text}
        if self.kind is NewBlockKind.HEADING:
            d["level"] = self.level
        if self.kind is NewBlockKind.CODE and self.language is not None:
            d["language"] = self.language
        if self.kind is NewBlockKind.TODO:
            d["done"] = self.done
        if self.kind is NewBlockKind.TABLE:
            # the grid as JSON lists (rows come back as tuples through from_dict), plus
            # the header flag ALWAYS — a table's header state is never a default a reader
            # of the record has to infer.
            d["rows"] = [[_cell_to_wire(cell) for cell in row] for row in self.rows]
            d["header_row"] = self.header_row
        if self.kind is NewBlockKind.MERMAID and self.theme is not None:
            # only when explicitly chosen — an absent theme IS the default, and recording it
            # would make the wire form claim a choice the caller never made.
            d["theme"] = self.theme
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "NewBlock":
        return cls(
            kind=NewBlockKind(d["kind"]),
            text=d.get("text", ""),
            level=d.get("level"),
            language=d.get("language"),
            done=bool(d.get("done", False)),
            children=tuple(cls.from_dict(c) for c in d.get("children", ())),
            rows=tuple(tuple(_cell_from_wire(cell) for cell in row)
                       for row in d.get("rows", ())),
            header_row=d.get("header_row"),
            theme=d.get("theme"),
        )


#: The union an :class:`InsertRequest` accepts as one item of content — the tagless
#: legacy :class:`NewParagraph` or a kind-tagged :class:`NewBlock`.
NewContent = Union[NewParagraph, NewBlock]


def _content_from_dict(d: dict) -> NewContent:
    """Deserialize one insert-content item — **the one content registration point**.

    A :class:`NewBlock` tags itself with ``"kind"``; the pre-LD-134
    :class:`NewParagraph` is **tagless** (``{"text": ...}``, byte-unchanged), so a
    dict with no ``kind`` reads back as a ``NewParagraph`` and W3-era plan JSON still
    round-trips. This mirrors the tagless-``EditRequest`` and anchor-``kind``
    dispatchers, so every content kind is told apart in exactly one place — adding a
    kind never touches the op registry's insert deserializer.
    """
    if "kind" in d:
        return NewBlock.from_dict(d)
    return NewParagraph.from_dict(d)


@dataclass(frozen=True)
class InsertRequest:
    """A consumer's request to **insert** one or more text-bearing paragraphs relative
    to a reference block.

    * ``reference`` — an :class:`Anchor` (quote + breadcrumb) **or** an :class:`AnchorById`
      (a bare ``block_id``) designating the block the insertion is positioned
      relative to (resolved exactly-one-or-refuse like any other anchor). Narrative
      anchors only: you insert relative to a *block*, not a table cell.
      **The keyword differs by request type** — it is ``reference`` here, ``target`` on
      :class:`DeleteRequest`, ``anchor`` on :class:`EditRequest` and
      :class:`SubSpanEditRequest` — one anchor object under three names, because an insert
      is positioned *relative to* a block it does not touch while a delete names the block
      it removes. Passing the wrong one is a plain ``TypeError``.
    * ``position`` — an :class:`InsertPosition` (``BEFORE`` / ``AFTER`` / ``APPEND_INTO``).
    * ``content`` — a non-empty tuple of :class:`NewBlock` and/or :class:`NewParagraph`,
      the blocks to create: a heading, a paragraph, a nested bullet / ordered / todo list,
      a code block, a quote, a table (widened from paragraphs-only, and the table kind
      added the table; the legacy shape stays valid and mixing the two in one request is
      fine). Hostile creatable types are
      **structurally inexpressible** (see :class:`NewBlockKind`).

    Frozen and JSON-round-trippable. Serializes with an ``"op": "insert"`` discriminator so
    :func:`_request_from_dict` can tell it from an :class:`EditRequest` (tagless, unchanged)
    and a :class:`DeleteRequest`. This type defines the *request shape only* — no resolution
    and no write happen here — the resolver and the apply engine do that.
    """

    reference: NarrativeAnchor
    position: InsertPosition
    content: Tuple[NewContent, ...]

    def __post_init__(self):
        object.__setattr__(self, "content", tuple(self.content))
        if not self.content:
            raise ValueError(
                "InsertRequest needs at least one block of content "
                "(an insertion with nothing to create is meaningless)."
            )
        if len(self.content) > MAX_CHILDREN_PER_CALL:
            raise ValueError(
                f"{len(self.content)} top-level blocks exceeds the "
                f"{MAX_CHILDREN_PER_CALL}-per-call limit of the docx create-children "
                f"endpoint (one sibling group is one call) — split the authoring into "
                f"batches"
            )

    def to_dict(self) -> dict:
        return {
            "op": "insert",
            "reference": self.reference.to_dict(),
            "position": self.position.value,
            "content": [p.to_dict() for p in self.content],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InsertRequest":
        return cls(
            reference=_anchor_from_dict(d["reference"]),
            position=InsertPosition(d["position"]),
            content=tuple(_content_from_dict(p) for p in d["content"]),
        )


@dataclass(frozen=True)
class SubSpanEditRequest:
    """A consumer's request to edit a **quoted span WITHIN a paragraph**.

    Where an :class:`EditRequest` replaces the *whole* block, a sub-span edit changes only
    a contiguous **span** inside it and **preserves the surrounding run styles** — the
    apply engine **splits the matched run(s) at the span boundaries, mutates only the
    span, and leaves every surrounding run byte-identical** (the ``to_write_elements``
    element-level discipline; spike Test 4). Fields:

    * ``anchor`` — an :class:`Anchor` (quote + breadcrumb) **or** an :class:`AnchorById`
      (a bare ``block_id``) locating the **block**, resolved exactly-one-or-refuse by
      the resolver (like any narrative anchor). Narrative anchors only: a sub-span within a *table
      cell* is out of scope this tranche.
    * ``span`` — the **verbatim sub-string** within that block to replace. It must occur
      **exactly once** in the block's text (0 → not-found; >1 → not exactly one region →
      refuse) and, at write time, map to **exactly one uniformly-styled contiguous run
      region** (a span crossing runs of **differing** style, or overlapping a non-text
      inline, refuses with :meth:`Refusal.span_not_splittable`). The
      **exactly-one-or-refuse invariant is absolute** — when it can't hold, refuse, never
      guess a replacement style.
    * ``replacement`` — the new text for that span (may be empty to remove the span).

    Frozen and JSON-round-trippable; serializes with an ``"op": "subspan"`` discriminator so
    :func:`_request_from_dict` tells it from an :class:`EditRequest` (tagless, unchanged),
    an :class:`InsertRequest`, and a :class:`DeleteRequest`. This type defines the *request
    shape only* — no resolution and no write happen here; the resolver and the apply engine
    do that.
    """

    anchor: NarrativeAnchor
    span: str
    replacement: str

    def __post_init__(self):
        if not self.span:
            raise ValueError(
                "SubSpanEditRequest needs a non-empty span "
                "(an empty span is a substring of every block and locates nothing)."
            )

    def to_dict(self) -> dict:
        return {
            "op": "subspan",
            "anchor": self.anchor.to_dict(),
            "span": self.span,
            "replacement": self.replacement,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SubSpanEditRequest":
        return cls(
            anchor=_anchor_from_dict(d["anchor"]),
            span=d["span"],
            replacement=d["replacement"],
        )


@dataclass(frozen=True)
class DeleteRequest:
    """A consumer's request to **delete** the block designated by an anchor.

    * ``target`` — an :class:`Anchor` (quote + breadcrumb) **or** an :class:`AnchorById`
      (a bare ``block_id``) designating the block to remove (resolved
      exactly-one-or-refuse). Narrative anchors only. The by-id form answers
      the complaint that "deletes cannot target block ids" — and, unlike a quote,
      it can address a block whose text is not unique *and* a whole **container** (delete a
      table, or a list item with its children, by id).
      **The keyword differs by request type** — it is ``target`` here and ``reference`` on
      :class:`InsertRequest` (``anchor`` on :class:`EditRequest` /
      :class:`SubSpanEditRequest`): the same anchor object, named for the role it plays —
      a delete names the block it removes, an insert names the block it is positioned
      *relative to*. Passing the wrong one is a plain ``TypeError``.

    **Single block for phase-1 (a deliberate scope call).** A
    contiguous-range delete is deliberately **not expressible** in phase-1: a bare quote
    already resolves to *one* block, and expressing a range (a start anchor + an end
    anchor, or a count) would (a) multiply the exactly-one-or-refuse invariant into a
    range-resolution problem with its own ambiguity modes, and (b) has no demonstrated
    consumer demand. A consumer that wants to remove N adjacent blocks issues N
    :class:`DeleteRequest` s, each exactly-one-or-refuse. If range-delete is ever wanted it
    is a clean additive extension (a ``DeleteRangeRequest`` sibling, or an optional
    ``end`` anchor) — kept out until demand exists, per the roadmap's "only on demonstrated
    consumer demand" discipline.

    Frozen and JSON-round-trippable; serializes with an ``"op": "delete"`` discriminator.
    Deletion is **destructive** — the apply-log entry the engine produces for a delete carries the
    full removed-block payload (see :meth:`ApplyLogEntry.deleted`) so a consumer can
    reconstruct what was removed. This type defines the *request shape only*.
    """

    target: NarrativeAnchor

    def to_dict(self) -> dict:
        return {"op": "delete", "target": self.target.to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> "DeleteRequest":
        return cls(target=_anchor_from_dict(d["target"]))


@dataclass(frozen=True)
class GrowTableRequest:
    """A consumer's request to **append one row** to a table that already exists.

    * ``anchor`` — a :data:`TableAnchor`: the table's own :class:`AnchorById`, or a
      :class:`TableLocator` whose ``row_key`` identifies which table (the grow addresses the
      **table**, so only the parts of a locator that identify the table are consulted — the
      column-target is what the *cell* path needs). No quote anchor: a table carries no text of
      its own, so a quote cannot resolve to one.
    * ``row_index`` — where the row goes, and the only value that ships is
      :data:`APPEND_ROW_INDEX`. Anything else is refused typed
      (:data:`~larkdocio.write.model.RefusalReason.TABLE_GROW_UNSUPPORTED`) as **unmeasured,
      not impossible**: mid-table insertion has never been called from this tree and no
      measurement in it covers one. The parameter exists precisely so that asking gets an
      answer naming the remedy, instead of a ``TypeError`` on an unknown keyword.

    **Why ONE row per request, and no count.** A row count would need a bound, and this
    library states deliberately that there is **no row cap** — the row axis grew to 200 with no
    refusal at any row, so a cap would memorialise a limit that is not Lark's (see
    :data:`MAX_TABLE_COLUMNS`'s note). An unbounded count would put an unbounded throttled loop
    behind one plan entry. One row per request keeps every entry exactly one mutating call — so
    its apply-log ``atomic`` is true by derivation and can never claim a partial landing it did
    not have — and N rows are N entries the plan previews and the caller approves one by one.

    **What it does NOT do**, and each with its reason. It never *removes* a row or a column
    (not measured here in either direction). It never appends a **column**: appending a row
    leaves every pre-existing cell's row-major index exactly where it was, and appending a
    column does not — a caller's stored offset into the grid would move — and the ruling that
    authorised this op names rows. It never inserts mid-table. The machine-readable statement
    of all three is the docx-write surface's ``absences`` register, under
    ``no-table-grid-change-beyond-appending-a-row``.

    Frozen and JSON-round-trippable; serializes with an ``"op": "grow-table"`` discriminator.
    This type defines the *request shape only* — the resolver and apply engine do the work, and
    it runs inside the same plan gate, the same whole-document ``STALE_DOCUMENT``
    compare-and-swap and the same refusal set as every other change.
    """

    anchor: TableAnchor
    row_index: int = APPEND_ROW_INDEX

    def __post_init__(self):
        if isinstance(self.row_index, bool) or not isinstance(self.row_index, int):
            raise TypeError(
                f"GrowTableRequest.row_index must be an int (the shipped value is "
                f"{APPEND_ROW_INDEX}, which appends at the end); got "
                f"{type(self.row_index).__name__}"
            )

    def to_dict(self) -> dict:
        return {"op": "grow-table", "anchor": self.anchor.to_dict(),
                "row_index": self.row_index}

    @classmethod
    def from_dict(cls, d: dict) -> "GrowTableRequest":
        return cls(anchor=_anchor_from_dict(d["anchor"]),
                   row_index=d.get("row_index", APPEND_ROW_INDEX))


#: The file types Lark's comment-create endpoint accepts — **its own enum, quoted**. The
#: rejection body for anything else prints ``options: [doc,docx]`` verbatim in a
#: ``field_violations`` entry naming ``file_type``, so this tuple is a transcription of the
#: server's answer and not a policy this library invented. Anything outside it is refused
#: with that body (:data:`~larkdocio.write.comments.SHEETS_CREATE_REJECTED_EVIDENCE`) rather
#: than sent.
COMMENT_FILE_TYPES: Tuple[str, ...] = ("doc", "docx")


@dataclass(frozen=True)
class CreateCommentRequest:
    """A consumer's request to put ONE **whole-document** comment on the file.

    * ``text`` — the comment's content. A comment's content *is* its first reply, so this
      becomes the single reply of a new thread. Empty content is rejected at construction
      (the API answers ``1069302 "param error"`` for it, and a request that cannot succeed
      must not reach a plan).
    * ``file_type`` — ``"docx"`` (the default) or ``"doc"``. Those two are Lark's whole
      enum for this endpoint (:data:`COMMENT_FILE_TYPES`); anything else — a spreadsheet
      above all — is **refused** at plan time with the server's own rejection quoted.
    * ``anchor`` — :data:`~larkdocio.write.model.anchors.WHOLE_DOCUMENT`, and structurally
      nothing else. It is here so the plan entry and the apply-log carry a **truthful**
      target rather than a stand-in, and so ``capabilities()`` can project what this family
      points at.

    **The three fields below exist ONLY in order to be refused**, and that is the most
    important thing about this type. Lark's create route accepts an ``anchor``, a ``quote``
    and ``is_whole:false``, answers ``code 0``, and then **silently creates a plain
    whole-document comment** — a bogus block id and a quote that does not occur in the
    document are not errors either. A library that simply omitted these fields would leave
    a caller who wants an anchored comment with a ``TypeError``; a library that forwarded
    them would report an anchored comment that was never created. So they are expressible
    **and refused**, with the captured evidence and the working alternative in the refusal
    detail:

    * ``anchor_block_id`` — a passage anchor by block id (in any spelling, including the
      JSON-string form the probe tried);
    * ``quote`` — the passage text a comment should be attached to;
    * ``is_whole`` — ``False`` asks for a passage comment and is refused; ``True`` merely
      restates the only shape that exists and proceeds; ``None`` (the default) is the same.

    None of the three is ever put on the wire — not even the accepted ``is_whole=True``,
    because the endpoint's behaviour when it *is* sent is precisely what makes it untrustable
    (a test pins the absence of all three from every request body).

    Frozen and JSON-round-trippable; serializes with an ``"op": "comment-create"``
    discriminator. The comment lands as the **application's own bot identity** — see
    :data:`~larkdocio.write.comments.BOT_AUTHORSHIP_DISCLOSURE`, which the plan states out
    loud rather than leaving a consumer to discover.
    """

    text: str
    file_type: str = "docx"
    anchor: WholeDocument = WHOLE_DOCUMENT
    anchor_block_id: Optional[str] = None
    quote: Optional[str] = None
    is_whole: Optional[bool] = None

    def __post_init__(self):
        if not isinstance(self.text, str):
            raise TypeError(
                f"CreateCommentRequest.text must be a str (the comment's content), got "
                f"{type(self.text).__name__}"
            )
        if not self.text.strip():
            raise ValueError(
                "CreateCommentRequest needs non-empty text — Lark answers 1069302 "
                "\"param error\" for empty comment content, so a blank comment is a "
                "request that cannot succeed."
            )
        if not isinstance(self.anchor, WholeDocument):
            raise TypeError(
                "CreateCommentRequest.anchor is WHOLE_DOCUMENT and nothing else — Lark has "
                "no anchored-comment create. To ask for one anyway (and read the refusal "
                "with its evidence), pass anchor_block_id= / quote= / is_whole=False."
            )

    @property
    def anchoring_intent(self) -> Optional[str]:
        """The anchoring field this request supplied, or ``None`` for the shape that works.

        One accessor rather than three checks scattered through the resolver, so the plan-time
        refusal and the guide's account of it can never disagree about what counts as asking
        for an anchor. ``is_whole=True`` is deliberately **not** an intent — it restates the
        whole-document shape rather than departing from it.
        """
        if self.anchor_block_id is not None:
            return f"anchor_block_id={self.anchor_block_id!r}"
        if self.quote is not None:
            return f"quote={self.quote!r}"
        if self.is_whole is False:
            return "is_whole=False"
        return None

    def to_dict(self) -> dict:
        d: dict = {"op": "comment-create", "text": self.text,
                   "file_type": self.file_type, "anchor": self.anchor.to_dict()}
        # Trailing + conditional: a request with no anchoring intent — the only shape that
        # can proceed — serializes without the refusal-only keys.
        if self.anchor_block_id is not None:
            d["anchor_block_id"] = self.anchor_block_id
        if self.quote is not None:
            d["quote"] = self.quote
        if self.is_whole is not None:
            d["is_whole"] = self.is_whole
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CreateCommentRequest":
        return cls(
            text=d["text"],
            file_type=d.get("file_type", "docx"),
            anchor=WholeDocument.from_dict(d.get("anchor") or {}),
            anchor_block_id=d.get("anchor_block_id"),
            quote=d.get("quote"),
            is_whole=d.get("is_whole"),
        )


@dataclass(frozen=True)
class RemoveCommentRequest:
    """A consumer's request to **remove** one comment thread the application owns.

    * ``target`` — a :class:`~larkdocio.write.model.anchors.CommentThread` naming the
      thread by the API's own ``comment_id``. Supplying the bare id via ``comment_id=`` is
      accepted as a convenience and builds the anchor.
    * ``author_id`` — **the application's own bot ``open_id``**, i.e. whose thread this must
      be for the removal to proceed. It is required, and the library does not derive it,
      because it **cannot**: the directory endpoint answers ``41050 "no user authority"`` on
      these scopes and the comment payload carries no human-vs-application discriminator, so
      any value this library supplied would be a guess. It is not friction invented here
      either — a comment-create's apply-log entry hands back the very id its removal needs.

    **Removal is ownership-scoped, and whole-thread or nothing.** There is no
    delete-a-comment endpoint (that route answers a gateway-level, non-JSON 404); a comment's
    content *is* its replies, and deleting the last reply removes the comment with it. So
    removal means deleting **every** reply — which the API permits only for replies the
    caller wrote (a reply written by anyone else is HTTP 403 / ``1069303 "forbidden"``, an
    ownership refusal that is about *who is asking*, not about the file type). The engine
    therefore reads the live thread first and refuses the whole removal unless every reply is
    ``author_id``'s: a half-deleted thread misrepresents the conversation and cannot be
    undone, which is strictly worse than a refusal.

    Frozen and JSON-round-trippable; serializes with an ``"op": "comment-remove"``
    discriminator.
    """

    target: CommentThread
    author_id: str
    #: The file type the thread lives on — ``"docx"`` (the default) or ``"doc"``. Unlike a
    #: create, a removal is **not** enum-restricted by Lark: the reply endpoints accept a
    #: spreadsheet (its comment READ does), and ``1069303`` is an ownership refusal that is
    #: "about who the caller is, not about which file type it named" (the probe's own words,
    #: which is why its spreadsheet delete arm was not spent). It is carried so the call's
    #: query matches the file, not to widen anything.
    file_type: str = "docx"

    def __init__(self, *, author_id: str, target: Optional[CommentThread] = None,
                 comment_id: Optional[str] = None, file_type: str = "docx"):
        if (target is None) == (comment_id is None):
            raise ValueError(
                "RemoveCommentRequest needs exactly one of target=CommentThread(...) or "
                "comment_id='<the API's comment id>'."
            )
        if target is None:
            target = CommentThread(comment_id=comment_id)
        if not isinstance(author_id, str):
            raise TypeError(
                f"RemoveCommentRequest.author_id must be a str (your application's own bot "
                f"open_id), got {type(author_id).__name__}"
            )
        if not author_id.strip():
            raise ValueError(
                "RemoveCommentRequest needs a non-empty author_id — the application's own "
                "bot open_id, which a comment-create's apply-log entry reports. This "
                "library will not guess it: the directory endpoint answers 41050 for it, "
                "and removing a thread on an unverified ownership claim risks a "
                "half-deleted thread."
            )
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "author_id", author_id)
        object.__setattr__(self, "file_type", file_type)

    @property
    def comment_id(self) -> str:
        """The thread's id — read off the anchor, so there is one copy of it."""
        return self.target.comment_id

    def to_dict(self) -> dict:
        return {"op": "comment-remove", "target": self.target.to_dict(),
                "author_id": self.author_id, "file_type": self.file_type}

    @classmethod
    def from_dict(cls, d: dict) -> "RemoveCommentRequest":
        return cls(target=CommentThread.from_dict(d["target"]), author_id=d["author_id"],
                   file_type=d.get("file_type", "docx"))


def _request_from_dict(d: dict):
    """Deserialize whichever request kind a serialized form carries.

    :class:`InsertRequest` / :class:`DeleteRequest` / :class:`SubSpanEditRequest`, the two
    comment ops and :class:`GrowTableRequest` tag themselves (``"op": "insert"`` / ``"delete"``
    / ``"subspan"`` / ``"comment-create"`` / ``"comment-remove"`` / ``"grow-table"``); the
    W1/W2 :class:`EditRequest` is
    **tagless** (its serialization is unchanged, so W1/W2 JSON reads back byte-compatible),
    so a missing/other ``op`` reads back as an :class:`EditRequest`. This mirrors the anchor
    ``kind`` dispatcher (:func:`_anchor_from_dict`) so the whole chain round-trips every
    request kind through one dispatcher; the plan/apply engine (S2/S3) dispatches on the
    concrete type it gets back.
    """
    op = d.get("op")
    if op == "insert":
        return InsertRequest.from_dict(d)
    if op == "delete":
        return DeleteRequest.from_dict(d)
    if op == "subspan":
        return SubSpanEditRequest.from_dict(d)
    if op == "grow-table":
        return GrowTableRequest.from_dict(d)
    if op == "comment-create":
        return CreateCommentRequest.from_dict(d)
    if op == "comment-remove":
        return RemoveCommentRequest.from_dict(d)
    return EditRequest.from_dict(d)
