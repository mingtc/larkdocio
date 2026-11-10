"""larkdocio.sheets.requests._styles — CELL STYLE — fill / font / number-format / borders, plus the word-wrap refutation.

The package's largest family: :class:`CellStyle`'s validated payload, the border
vocabulary, the probed word-wrap NOT-writable record, and the one-range / N-range write
requests over the shared :class:`_StyleWrite` base.

Split out of the flat 2,462-line ``sheets/requests.py`` by LD-224, **verbatim** —
pre-split lines 1078–1651. The package's ``__init__`` re-exports every name defined here,
so ``from larkdocio.sheets.requests import <name>`` is unchanged.
"""
import re
from dataclasses import dataclass
from typing import Optional

from larkdocio.errors import LarkConfigError
from larkdocio.sheets.write_range import WriteRange, parse_write_range

from ._gates import WriteOpKind


# --------------------------------------------------------------------------- #
# CELL STYLE writes (LD-188) — fill / font / number-format over an A1 range.     #
#                                                                               #
# The endpoint was API-proven at LD-107 and exercised nightly by the S5 fidelity #
# gate, but lived ONLY in tests/sheets_write_harness.py: the library could READ  #
# style (the L2 export leg) and not write it. This family is that promotion —    #
# no new gate wiring, because WriteOpKind.STYLE / NUMBER_FORMAT were reserved    #
# for it in STYLE_LEG_OP_KINDS from the start.                                   #
# --------------------------------------------------------------------------- #

#: The v2 style endpoint's font-size range, **characterized live** (LD-188,
#: ``tests/captures/sheets-style-write-probe/captures/01-style-write-characterization.json``) rather than
#: taken from the coverage audit's bare "font size clamps 9-36" — which does not say whether
#: out-of-range is *refused* or *silently clamped*. It is a **REFUSAL**: ``"8pt/1.5"`` and
#: ``"37pt/1.5"`` both answered :data:`FONT_SIZE_REFUSAL_CODE` while ``"9pt/1.5"`` and
#: ``"36pt/1.5"`` landed as asked (the export's ``xl/styles.xml`` shows ``sz="9"`` / ``sz="36"``,
#: and the two refused arms left **no** style behind — so there is no clamp to characterize).
MIN_FONT_SIZE = 9
MAX_FONT_SIZE = 36

#: Lark's code for an out-of-range (or wrongly-shaped) ``fontSize``.
FONT_SIZE_REFUSAL_CODE = 90204

#: Lark's **verbatim** answer, quoted in the construction refusal so the caller reads the real
#: body instead of a paraphrase. Note what it does NOT say: the same body comes back for a
#: **bare int** ``fontSize`` (probed: ``{"fontSize": 10}`` → this exact message), so the message
#: blames the range for what is really a *shape* error. That is precisely why the caller-facing
#: form here is an ``int`` and the wire string is built in ONE place.
FONT_SIZE_REFUSAL_BODY = "invalid fontSize, fontSize must between 9 and 36"

#: The wire form of a font size — ``"<size>pt/<line-spacing>"`` (probed: ``"10pt/1.5"`` → code
#: ``0``; a bare int → ``90204``). The line spacing is **not** exposed as a caller knob: it is a
#: separate, named intent, and inventing a second meaning for ``font_size`` would be exactly the
#: guess this family avoids.
FONT_SIZE_LINE_SPACING = "1.5"

#: The colour form every capture uses — ``#RRGGBB``.
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# --------------------------------------------------------------------------- #
# CELL BORDERS (LD-189) — the same payload, characterized before it was used.  #
#                                                                             #
# `borderType` / `borderColor` are fields of the style dict LD-188 already     #
# writes, so they ride that family: no new request type, no new endpoint, no   #
# new WriteOpKind. Everything below is a live finding, not documentation read: #
# tests/captures/sheets-border-wrap-probe/captures/01-border-wrap-characterization.json   #
# (the field survey) and .../02-border-semantics.json (the four semantics a    #
# SHIPPED knob has to state correctly).                                       #
# --------------------------------------------------------------------------- #

#: The eight ``borderType`` values the endpoint accepts — **exactly** the set the probe drove
#: to ``code 0`` *and* read back out of the export's ``xl/styles.xml``; nothing here is taken
#: from a doc page. Four are per-edge (``LEFT`` / ``RIGHT`` / ``TOP`` / ``BOTTOM``, each landing
#: precisely one edge), ``FULL_BORDER`` draws all four on every cell, ``OUTER_BORDER`` draws the
#: *range's* perimeter (a corner cell gets only its two outside edges), ``INNER_BORDER`` draws
#: only the grid lines *between* cells, and :data:`BORDER_CLEAR` is the clear.
#:
#: **Case-sensitive**: ``"full_border"`` answered :data:`BORDER_REFUSAL_CODE`
#: ``invalid borderType`` and landed nothing, so it is refused here rather than up-cased —
#: silently repairing a caller's value would hide that the endpoint is strict.
BORDER_TYPES = frozenset({
    "FULL_BORDER", "OUTER_BORDER", "INNER_BORDER", "NO_BORDER",
    "LEFT_BORDER", "RIGHT_BORDER", "TOP_BORDER", "BOTTOM_BORDER",
})

#: The value that CLEARS a border. Probed on both a full and a **partial** border (a
#: left-edge-only cell), and over a **subset** of a bordered range: it clears exactly the cells
#: the range names and leaves their neighbours' borders intact. The empty string is **not** a
#: clear — ``borderType: ""`` answered ``invalid borderType`` and left the existing border in
#: place — which is why there is one named clear value and no second spelling of it.
BORDER_CLEAR = "NO_BORDER"

#: Lark's code for a rejected border field. The same generic ``90204`` the font size uses, so
#: the ``msg`` is again what names the cause.
BORDER_REFUSAL_CODE = 90204

#: Lark's **verbatim** answer to a ``borderType`` it does not accept.
BORDER_TYPE_REFUSAL_BODY = "invalid borderType"

#: Lark's **verbatim** answer to a malformed ``borderColor`` (probed with ``"red"``).
BORDER_COLOR_REFUSAL_BODY = "invalid borderColor"

#: **Borders ADD; they do not replace.** Two per-edge writes UNION (``LEFT_BORDER`` then
#: ``TOP_BORDER`` → left *and* top), and a later font-only write on a bordered cell keeps the
#: border. So a caller building an edge set incrementally gets what they asked for, and
#: :data:`BORDER_CLEAR` is the only way back.
BORDERS_ARE_ADDITIVE = True

# --------------------------------------------------------------------------- #
# WORD-WRAP (LD-189) — REFUTED. The one authored statement of the limit.       #
# --------------------------------------------------------------------------- #

#: Every wrap field name the probe tried, in the exact shape it was sent. Recorded so the
#: documented limit can neither overstate nor understate the search that produced it — a test
#: pins this list against the capture itself.
WORD_WRAP_PROBED_FIELDS = (
    {"wrap": True},
    {"wrapText": True},
    {"wrapStrategy": "WRAP"},
    {"textWrap": True},
    {"autoWrap": True},
    {"font": {"wrap": True}},
    {"wrap": 1},
    {"wrapStrategy": "CLIP"},
    {"hAlign": 0, "wrap": True},
)

#: **The limit, stated once, loudly** — quoted verbatim by ``GUIDE.md`` and, in the source repository
#: rather than in the wheel, by ``SHEETS.md``, so the three cannot drift. There is no error
#: body to quote here, and that is precisely the hazard:
#: the endpoint answers **success** to a field it has never heard of, so a ``code 0`` is not
#: evidence of anything. The control arm is what makes this a finding instead of a guess.
WORD_WRAP_NOT_WRITABLE = (
    "WORD WRAP IS NOT A WRITABLE CELL-STYLE FIELD, and this endpoint will tell you otherwise. "
    "Nine candidate field names were probed live — wrap, wrapText, wrapStrategy ('WRAP' and "
    "'CLIP'), textWrap, autoWrap, font.wrap, a bare int wrap, and wrap alongside a real "
    "alignment field — and every one answered code 0 'success' with updatedCells: 1 AND a "
    "revision bump, while the exported cell came back completely unstyled. That reply proves "
    "nothing, which is the point: the same probe sent a deliberately nonsense field name with "
    "no real field beside it and got the identical code 0 'success', updatedCells: 1, revision "
    "bumped, nothing landed. This endpoint SILENTLY IGNORES fields it does not know. The "
    "distinguishing arm removes the last doubt — {\"hAlign\": 0, \"wrap\": true} in ONE request "
    "landed the hAlign (the export shows horizontal=\"left\") and not the wrap — so the export "
    "does report alignment attributes, and wrapText is absent because nothing set it. So "
    "larkdocio ships NO wrap knob rather than one that reports success and does nothing; a "
    "wrap must be set by hand in the Lark UI. Evidence: "
    "tests/captures/sheets-border-wrap-probe/captures/01-border-wrap-characterization.json "
    "in the source repository. "
    "Cell BORDERS, probed in the same run, are the opposite verdict and ARE writable."
)


class StyleError(LarkConfigError, ValueError):
    """A cell-style write is not writable **as given**.

    Raised at **construction**, so a style Lark would reject cannot be built and costs zero API
    calls. Each message names the fault, the consequence, the repair and a valid-form example
    (the :class:`DimensionPropertyError` house standard), and quotes the **probed** Lark answer
    it pre-empts where one exists (:data:`FONT_SIZE_REFUSAL_BODY`).

    **Deliberately a subclass of BOTH** :class:`~larkdocio.errors.LarkConfigError` and
    :class:`ValueError`, exactly as :class:`DimensionPropertyError` /
    :class:`DimensionSpanError` are.
    """


def _require_hex_color(value, *, field, refusal_body=None) -> None:
    """Every colour field takes the one form the captures use. ``refusal_body`` quotes Lark's
    own verbatim answer where a probe established it for that specific field (LD-189's
    ``borderColor``), so the message pre-empts the real body rather than paraphrasing it."""
    if isinstance(value, str) and _HEX_COLOR_RE.match(value):
        return
    quoted = "" if refusal_body is None else (
        f" Lark answers '{BORDER_REFUSAL_CODE} {refusal_body}' to a malformed one (probed with "
        f"'red')."
    )
    raise StyleError(
        f"CellStyle: `{field}` must be a #RRGGBB hex colour string, got {value!r}. Every "
        f"captured style write uses that form (e.g. the spike's backColor='#FFFF00'), and a "
        f"three-digit, missing-hash or named colour is refused here rather than sent — a "
        f"rejected colour would fail the WHOLE style write, including the parts that were "
        f"fine.{quoted} Write CellStyle({field}='#FFFF00')."
    )


@dataclass(frozen=True)
class CellStyle:
    """The typed cell style a style write carries — fill, font, border and number format.

    ``bold`` / ``italic`` / ``font_size`` are the font; ``back_color`` is the cell **fill**
    (``backColor``) and ``fore_color`` the text colour (``foreColor``), both ``#RRGGBB``;
    ``formatter`` is the **number format** pattern (``"0.00%"``). At least one must be given —
    a style that asks for nothing is refused rather than sent.

    **The size is an int here and a string on the wire.** Lark's ``font.fontSize`` is
    ``"<size>pt/<line-spacing>"``; a bare int is refused with a message that blames the range
    (probed). :meth:`wire` is the ONLY place the wire form is produced, so the wrong shape is
    not expressible, and the 9..36 range is refused at construction because Lark **refuses**
    rather than clamps it (probed both ends).

    **Borders are here; word-wrap is not, and never will be by guess.** ``border_type``
    takes one of :data:`BORDER_TYPES` and ``border_color`` its ``#RRGGBB`` colour — both
    characterized live before a line of this was written, down to the per-edge geometry and the
    fact that borders **add** rather than replace (:data:`BORDERS_ARE_ADDITIVE`), with
    :data:`BORDER_CLEAR` the only way back. A ``border_color`` with no ``border_type`` is refused
    at construction because Lark answers **success** and lands nothing.
    **Word-wrap is refuted** — see :data:`WORD_WRAP_NOT_WRITABLE` for the evidence; there is no
    wrap field on this class, deliberately.
    """

    bold: Optional[bool] = None
    italic: Optional[bool] = None
    font_size: Optional[int] = None
    back_color: Optional[str] = None
    fore_color: Optional[str] = None
    formatter: Optional[str] = None
    border_type: Optional[str] = None
    border_color: Optional[str] = None

    def __post_init__(self):
        self.wire()          # validate at construction: an unwritable style cannot be built

    def wire(self) -> dict:
        """The validated ``style`` wire dict — the ONE place the payload is built."""
        for name, value in (("bold", self.bold), ("italic", self.italic)):
            if value is None or isinstance(value, bool):
                continue
            raise StyleError(
                f"CellStyle: `{name}` must be a bool, got {value!r}. A truthy string like "
                f"'false' would set {name} while reading as its opposite, so it is refused "
                f"rather than coerced. Write CellStyle({name}=True)."
            )
        if self.font_size is not None:
            size = self.font_size
            if isinstance(size, bool) or not isinstance(size, int):
                raise StyleError(
                    f"CellStyle: `font_size` must be an int point size between "
                    f"{MIN_FONT_SIZE} and {MAX_FONT_SIZE}, got {size!r}. The wire form is the "
                    f"string '<size>pt/{FONT_SIZE_LINE_SPACING}' and it is built here, once, "
                    f"from your int — passing the string (or a float) yourself is refused so "
                    f"there is exactly one definition of that shape. Write "
                    f"CellStyle(font_size=12)."
                )
            if not (MIN_FONT_SIZE <= size <= MAX_FONT_SIZE):
                raise StyleError(
                    f"CellStyle: font_size={size} is outside the {MIN_FONT_SIZE}..."
                    f"{MAX_FONT_SIZE} range this endpoint accepts, and Lark REFUSES it rather "
                    f"than clamping — it answers this exact body "
                    f"'{FONT_SIZE_REFUSAL_CODE} {FONT_SIZE_REFUSAL_BODY}' (probed live at both "
                    f"ends: 8 and 37 refused, 9 and 36 landed as asked), which would fail the "
                    f"whole style write including the fill and number format riding with it. "
                    f"Pass a size in range — font_size={MIN_FONT_SIZE} is the smallest and "
                    f"font_size={MAX_FONT_SIZE} the largest — or leave `font_size` unset to "
                    f"keep the cell's current size."
                )
        if self.back_color is not None:
            _require_hex_color(self.back_color, field="back_color")
        if self.fore_color is not None:
            _require_hex_color(self.fore_color, field="fore_color")
        if self.formatter is not None:
            if not isinstance(self.formatter, str) or not self.formatter.strip():
                raise StyleError(
                    f"CellStyle: `formatter` must be a non-empty number-format pattern string, "
                    f"got {self.formatter!r}. Write CellStyle(formatter='0.00%') — the pattern "
                    f"the spike proved lands as numFmt '0.00%' in the exported styles."
                )
        if self.border_type is not None:
            if self.border_type not in BORDER_TYPES:
                raise StyleError(
                    f"CellStyle: border_type={self.border_type!r} is not one of the "
                    f"{len(BORDER_TYPES)} values this endpoint accepts "
                    f"({', '.join(sorted(BORDER_TYPES))}) — Lark answers this exact body "
                    f"'{BORDER_REFUSAL_CODE} {BORDER_TYPE_REFUSAL_BODY}' and lands NOTHING, "
                    f"which would fail the whole style write including the fill and font riding "
                    f"with it. The value is CASE-SENSITIVE ('full_border' was probed and "
                    f"refused), and the empty string is not a clear — pass "
                    f"border_type='{BORDER_CLEAR}' to clear a border, or leave `border_type` "
                    f"unset to leave the cell's current border alone. Write "
                    f"CellStyle(border_type='FULL_BORDER')."
                )
        if self.border_color is not None:
            if self.border_type is None:
                raise StyleError(
                    f"CellStyle: `border_color` needs a `border_type` beside it, and this style "
                    f"has none. A borderColor sent ALONE is the worst kind of no-op: Lark "
                    f"answers code 0 'success' with updatedCells: 1 and bumps the revision, and "
                    f"the cell comes back with no border at all (probed live). So it is refused "
                    f"here rather than sent, because a write that reports success and does "
                    f"nothing is indistinguishable from one that worked. Write "
                    f"CellStyle(border_type='FULL_BORDER', border_color={self.border_color!r})."
                )
            _require_hex_color(self.border_color, field="border_color",
                              refusal_body=BORDER_COLOR_REFUSAL_BODY)
        font = {}
        if self.bold is not None:
            font["bold"] = self.bold
        if self.italic is not None:
            font["italic"] = self.italic
        if self.font_size is not None:
            font["fontSize"] = f"{self.font_size}pt/{FONT_SIZE_LINE_SPACING}"
        style = {}
        if font:
            style["font"] = font
        if self.back_color is not None:
            style["backColor"] = self.back_color
        if self.fore_color is not None:
            style["foreColor"] = self.fore_color
        if self.formatter is not None:
            style["formatter"] = self.formatter
        if self.border_type is not None:
            style["borderType"] = self.border_type
        if self.border_color is not None:
            style["borderColor"] = self.border_color
        if not style:
            raise StyleError(
                "CellStyle: no style to set — a style write must carry at least one of "
                "`bold` / `italic` / `font_size` / `back_color` / `fore_color` / `formatter` / "
                "`border_type`, and this one carries none, so it names a range and asks for "
                "nothing. Write CellStyle(bold=True, back_color='#FFFF00', formatter='0.00%')."
            )
        return style

    @property
    def has_border(self) -> bool:
        """Whether this style sets a border — ``True`` exactly when ``border_type`` is set.

        A **convenience predicate offered to a caller**, not a step in any write. In
        particular it is **not** the input to the ``style-border-not-verifiable`` preview note:
        that note is computed from the serialized request instead
        (:func:`~larkdocio.sheets.ops.style_border_not_verifiable_note` looks for a
        ``borderType`` key in each span's own style), which is what keeps it correct for a span
        assembled without a :class:`CellStyle`. So reading this property changes nothing about
        what is written or previewed, and a style write behaves identically whether or not you
        ever ask.
        """
        return self.border_type is not None

    @property
    def op_kinds(self) -> tuple:
        """What this style TOUCHES, in the reserved vocabulary: the visual attributes are
        :data:`WriteOpKind.STYLE`, ``formatter`` is :data:`WriteOpKind.NUMBER_FORMAT`, and a
        style carrying both reports both. Every member is in :data:`STYLE_LEG_OP_KINDS`, so
        either way the export-based style leg is required — which is the whole reason those two
        kinds were reserved before any style write existed."""
        kinds = []
        if any(v is not None for v in (self.bold, self.italic, self.font_size,
                                       self.back_color, self.fore_color,
                                       self.border_type, self.border_color)):
            kinds.append(WriteOpKind.STYLE)
        if self.formatter is not None:
            kinds.append(WriteOpKind.NUMBER_FORMAT)
        return tuple(kinds)

    def describe(self) -> str:
        """The English restatement of the style (what a plan entry's ``semantic`` carries)."""
        parts = []
        if self.bold is not None:
            parts.append("bold" if self.bold else "not bold")
        if self.italic is not None:
            parts.append("italic" if self.italic else "not italic")
        if self.font_size is not None:
            parts.append(f"font size {self.font_size}pt")
        if self.back_color is not None:
            parts.append(f"fill {self.back_color}")
        if self.fore_color is not None:
            parts.append(f"text colour {self.fore_color}")
        if self.formatter is not None:
            parts.append(f"number format {self.formatter!r}")
        if self.border_type == BORDER_CLEAR:
            parts.append(f"border cleared ({BORDER_CLEAR})")
        elif self.border_type is not None:
            border = f"border {self.border_type}"
            if self.border_color is not None:
                border += f" in {self.border_color}"
            parts.append(border)
        return ", ".join(parts)


def _normalized_style_range(text, *, cls_name: str) -> str:
    """One style target → its **``Start:End``** A1 form.

    Both style endpoints reject a bare single cell — ``90202 wrong range=<sheet_id>!B2`` on
    ``PUT …/style`` (captured in the write spike **and** re-probed since) **and**, contrary to
    this project's own coverage note that the ``ranges`` array is ``90202``-immune, on
    ``styles_batch_update`` too (probed: ``{"ranges": ["<sheet_id>!C1"]}`` →
    ``90202 wrong range=<sheet_id>!C1``). So the range is
    normalized here as well as at the client's own chokepoint: a caller reading the plan sees
    the range that will actually be sent.
    """
    if not isinstance(text, str) or not text.strip():
        raise StyleError(
            f"{cls_name}: a style target must be an A1 range string, got {text!r}. Write "
            f"{cls_name}('<sheet_id>!A1:B2', CellStyle(bold=True))."
        )
    return parse_write_range(text).a1()


class _StyleWrite:
    """Mixin marking a request as a **cell-style** write (LD-188).

    Its own family and its own preview / apply legs, but **no new op-kind**: it classifies as
    the :data:`WriteOpKind.STYLE` / :data:`WriteOpKind.NUMBER_FORMAT` kinds the engine reserved
    for it, both already members of :data:`STYLE_LEG_OP_KINDS` — so the ``--verify-style``
    auto-on trigger and :func:`certify_gate_legs`' refusal to certify a style write on the cheap
    values leg alone are **pre-existing wiring this family proves fires**, not wiring it adds.
    ``is_structural`` is ``False``: a style moves no row, changes no value and reshapes no merge.
    """

    write_kind = "style"
    is_structural = False
    is_rich = False

    @property
    def op_kinds(self) -> tuple:
        kinds = []
        for style in self.styles():
            for kind in style.op_kinds:
                if kind not in kinds:
                    kinds.append(kind)
        return tuple(kinds)


@dataclass(frozen=True)
class StyleSpan:
    """One element of a batch style write — N ``ranges`` sharing ONE :class:`CellStyle`.

    The endpoint's own shape (``data: [{ranges: […], style: {…}}]``), typed. Both forms are
    probed accepted: several spans in one call, and one span carrying several ranges.
    """

    ranges: tuple
    style: CellStyle

    def __post_init__(self):
        ranges = tuple(self.ranges) if not isinstance(self.ranges, str) else (self.ranges,)
        if not ranges:
            raise StyleError(
                "StyleSpan: no range to style — a span must name at least one A1 range. "
                "Write StyleSpan(['<sheet_id>!A1:B2'], CellStyle(bold=True))."
            )
        if not isinstance(self.style, CellStyle):
            raise StyleError(
                f"StyleSpan: `style` must be a CellStyle, got {self.style!r}. The typed style "
                f"is what validates the payload before any call — a raw dict would post an "
                f"unchecked body. Write StyleSpan([...], CellStyle(bold=True))."
            )
        object.__setattr__(self, "ranges", tuple(
            _normalized_style_range(r, cls_name="StyleSpan") for r in ranges))

    def wire(self) -> dict:
        return {"ranges": list(self.ranges), "style": self.style.wire()}


@dataclass(frozen=True)
class StyleWriteRequest(_StyleWrite):
    """Set ONE :class:`CellStyle` on ONE A1 range (``PUT …/style``, ``appendStyle``).

    ``target`` is an A1 range, normalized to ``Start:End`` on construction (the ``90202``
    guard — a bare cell is refused by this endpoint, captured in the write spike and re-probed
    since). ``style`` is the typed :class:`CellStyle`, validated at ITS construction, so an
    unwritable style costs zero API calls.

    **What it does NOT do.** It reads nothing back: cell style is readable **only** through the
    xlsx export (the same position the dimension family is in), so there is no cheap
    ``before`` to compare and no precondition to enforce. The plan says so, and says what
    verifying it would cost — see :func:`~larkdocio.sheets.ops.style_export_cost_note`.

    **A style lands on exactly the cells the range names — a merge does not spread it** (probed:
    styling a three-cell merge's anchor alone answered ``updatedCells: 1`` and left the covered
    cells with no style), so a plan whose target names only PART of a merged region carries the
    ``style-partial-merge`` disclosure: the region ends up with mixed stored style, which shows
    the moment the merge is dissolved.
    """

    target: str
    style: CellStyle

    def __post_init__(self):
        if not isinstance(self.style, CellStyle):
            raise StyleError(
                f"StyleWriteRequest: `style` must be a CellStyle, got {self.style!r} — the "
                f"typed style is what refuses an unwritable payload before any call. Write "
                f"StyleWriteRequest('<sheet_id>!A1:B2', CellStyle(bold=True))."
            )
        object.__setattr__(self, "target", _normalized_style_range(
            self.target, cls_name="StyleWriteRequest"))

    def styles(self) -> tuple:
        return (self.style,)

    @property
    def a1_range(self) -> str:
        """The ``Start:End`` range this write puts on the wire."""
        return self.target

    def write_range(self) -> WriteRange:
        """The parsed target (the merge-intersection question's coordinate space)."""
        return parse_write_range(self.target)

    def descriptor(self) -> dict:
        return {
            "op": "style",
            "batch": False,
            "sheet_id": self.write_range().sheet_id,
            "ranges": [self.target],
            "spans": [{"ranges": [self.target], "style": self.style.wire()}],
            "style": self.style.wire(),
            "semantic": f"set {self.style.describe()} on {self.target}",
        }

    def style_preview(self) -> dict:
        """The previewed change — what the write sets, and what it leaves alone."""
        return _style_preview(self.descriptor())


@dataclass(frozen=True)
class BatchStyleWriteRequest(_StyleWrite):
    """Set N styles over N ranges in **ONE** call (``PUT …/styles_batch_update``).

    ``spans`` is a sequence of :class:`StyleSpan`. One plan entry, one API call, however many
    ranges — which is the reason this form exists beside :class:`StyleWriteRequest`: styling
    twelve ranges through the single-range op would spend twelve throttled writes and twelve
    revision compare-and-swaps.

    The ``ranges`` array is **not** immune to the bare-cell ``90202`` trap — this project's own
    coverage notes said it was, and a live probe says otherwise — so every range here is
    normalized to ``Start:End`` too.
    """

    spans: tuple

    def __post_init__(self):
        spans = tuple(self.spans or ())
        if not spans:
            raise StyleError(
                "BatchStyleWriteRequest: no range to style — a batch style write must carry at "
                "least one StyleSpan, and an empty batch would spend a call to do nothing. "
                "Write BatchStyleWriteRequest([StyleSpan(['<sheet_id>!A1:B2'], "
                "CellStyle(bold=True))]) — or, for one style over N ranges, "
                "BatchStyleWriteRequest.one_style(['<sheet_id>!A1:B2', '<sheet_id>!D1:D9'], "
                "CellStyle(bold=True))."
            )
        for span in spans:
            if not isinstance(span, StyleSpan):
                raise StyleError(
                    f"BatchStyleWriteRequest: every element must be a StyleSpan, got "
                    f"{span!r}. Write StyleSpan(['<sheet_id>!A1:B2'], CellStyle(bold=True))."
                )
        object.__setattr__(self, "spans", spans)

    @classmethod
    def one_style(cls, ranges, style: CellStyle) -> "BatchStyleWriteRequest":
        """ONE style over N ranges — the common case, in one call."""
        return cls([StyleSpan(ranges, style)])

    def styles(self) -> tuple:
        return tuple(span.style for span in self.spans)

    def wire_data(self) -> list:
        """The validated ``data`` array — the ONE place the batch payload is built."""
        return [span.wire() for span in self.spans]

    @property
    def ranges(self) -> tuple:
        return tuple(r for span in self.spans for r in span.ranges)

    def write_ranges(self) -> tuple:
        return tuple(parse_write_range(r) for r in self.ranges)

    def descriptor(self) -> dict:
        sheet_ids = []
        for wr in self.write_ranges():
            if wr.sheet_id is not None and wr.sheet_id not in sheet_ids:
                sheet_ids.append(wr.sheet_id)
        return {
            "op": "style",
            "batch": True,
            "sheet_id": sheet_ids[0] if len(sheet_ids) == 1 else None,
            "sheet_ids": sheet_ids,
            "ranges": list(self.ranges),
            "spans": self.wire_data(),
            "semantic": "; ".join(
                f"set {span.style.describe()} on {', '.join(span.ranges)}"
                for span in self.spans) + " (ONE styles_batch_update call)",
        }

    def style_preview(self) -> dict:
        return _style_preview(self.descriptor())


def _style_preview(desc: dict) -> dict:
    """The ``after`` payload for a style entry — the previewed change plus the explicit
    statement of what a style write leaves alone (no value moves, no row shifts, no merge
    changes shape), which is why it rides the export leg and not the merge or geometry ones."""
    return {
        "kind": "style",
        "batch": desc["batch"],
        "ranges": list(desc["ranges"]),
        "spans": desc["spans"],
        "semantic": desc["semantic"],
        "changes_values": False,
        "changes_geometry": False,
        "changes_merges": False,
    }
