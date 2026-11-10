"""larkdocio.sheets.cell_model — the typed cell model (LD-115).

The **additive** (D3) parallel surface the write-gate fidelity differ (S3) and the
consented MD fidelity gains (S4) consume — richer than L1's per-cell string render.
A :class:`TypedCell` carries:

* **value** — the raw values-API ``UnformattedValue`` **and** the display
  ``FormattedValue`` as a **dual** (e.g. raw ``0.1234`` / display ``"12.34%"``);
* **``segmentStyle`` runs** + **hyperlink / mention / multi-select structure** —
  a rich cell's segment array parsed into typed segments (:class:`TextRun` /
  :class:`Hyperlink` / :class:`UserMention` / :class:`DocMention` /
  :class:`MultiSelect`), mirroring the ``render_cell`` dispatch **without** forking
  its rendering;
* the export-only **fidelity** (:class:`CellFidelity`) — the number-format
  **pattern** + **whole-cell (format-level)** **bold / italic / fill** — populated from the
  LD-114 xlsx-export reader (S1) when an export is available, ``None`` when it is not
  (a values-only read degrades gracefully, never raises). Run-level emphasis is **not**
  here: it lives in the segments above, from the values API;
* **merge membership** (:class:`MergeMembership`) — whether the cell is a merge
  **anchor**, a **covered** cell, or **not merged**, with the region.

**Additive — the L1 MD path is untouched (D3).** This module imports **nothing**
from :mod:`larkdocio.sheets.render` / :mod:`larkdocio.sheets.table`, and neither of
them imports this — the typed model is a parallel surface, so the shipped
``render_cell`` / table-assembly Markdown is **byte-identical** with the model
present (a source-import guard + goldens zero-drift prove it). MD render changes
come only from the S4 gains, never from the model itself.

**Fidelity captured, color dropped (D5d).** The model **captures** what the render
path drops — a run's ``foreColor`` / ``fontSize`` and a cell's fill ARGB live in the
typed model (for the differ) but have no portable Markdown form, so they stay absent
from the rendered MD (parity with the docx color-drop).

**Serializable.** Every field round-trips through JSON via :meth:`TypedCell.to_dict`
/ :meth:`TypedCell.from_dict` (the raw/display values are already JSON-native; the
segments, fidelity, and merge use a discriminated encoding), so a consumer can
persist or transport a parsed cell losslessly.

Offline. Built from the values API (L1) + optionally enriched by the S1 export
parse — enrichment is **optional** (the model works values-only).
"""
from dataclasses import dataclass, field

from larkdocio.sheets.extent import column_number_to_a1
from larkdocio.sheets.models import Merge

# Merge-membership role vocabulary (a small, explicit set — the posture of the living
# matrix in the source repository, SHEETS.md).
MERGE_NONE = "none"
MERGE_ANCHOR = "anchor"
MERGE_COVERED = "covered"


# --------------------------------------------------------------------------- #
# Segment style (a styled run's segmentStyle) — captures color/size (dropped    #
# at render, D5d), so the differ can see them.                                  #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SegmentStyle:
    """One run's ``segmentStyle``. ``fore_color`` / ``font_size`` are **captured**
    (the model is the differ's source of truth) but have no Markdown form — the
    shared serializer drops them at render (L2 color-drop, D5d)."""

    bold: bool = False
    italic: bool = False
    strikethrough: bool = False
    underline: bool = False
    fore_color: str | None = None
    font_size: int | None = None

    @classmethod
    def from_wire(cls, style: dict | None) -> "SegmentStyle":
        style = style or {}
        return cls(
            bold=bool(style.get("bold")),
            italic=bool(style.get("italic")),
            strikethrough=bool(style.get("strikeThrough")),
            underline=bool(style.get("underline")),
            fore_color=style.get("foreColor"),
            font_size=style.get("fontSize"),
        )

    def to_dict(self) -> dict:
        return {
            "bold": self.bold,
            "italic": self.italic,
            "strikethrough": self.strikethrough,
            "underline": self.underline,
            "fore_color": self.fore_color,
            "font_size": self.font_size,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SegmentStyle":
        d = d or {}
        return cls(
            bold=bool(d.get("bold")),
            italic=bool(d.get("italic")),
            strikethrough=bool(d.get("strikethrough")),
            underline=bool(d.get("underline")),
            fore_color=d.get("fore_color"),
            font_size=d.get("font_size"),
        )


# --------------------------------------------------------------------------- #
# Typed segments — the rich-cell structure (a discriminated set)                #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class TextRun:
    """A ``{type:"text", segmentStyle, text}`` styled run."""

    kind = "text"
    text: str = ""
    style: SegmentStyle = SegmentStyle()

    def to_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text, "style": self.style.to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> "TextRun":
        return cls(text=d.get("text", "") or "", style=SegmentStyle.from_dict(d.get("style")))


@dataclass(frozen=True)
class Hyperlink:
    """A ``{type:"url", link, text}`` hyperlink segment. ``link`` is the **raw wire**
    form (structure, not render — the render path does its own unescape)."""

    kind = "url"
    text: str = ""
    link: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text, "link": self.link}

    @classmethod
    def from_dict(cls, d: dict) -> "Hyperlink":
        return cls(text=d.get("text", "") or "", link=d.get("link", "") or "")


@dataclass(frozen=True)
class UserMention:
    """A ``{type:"mention", mentionType:0}`` @user mention. ``user_id`` reads both
    the live ``userID`` and the older ``token`` id field."""

    kind = "mention_user"
    text: str = ""
    user_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text, "user_id": self.user_id, "name": self.name}

    @classmethod
    def from_dict(cls, d: dict) -> "UserMention":
        return cls(text=d.get("text", "") or "", user_id=d.get("user_id"), name=d.get("name"))


@dataclass(frozen=True)
class DocMention:
    """A ``{type:"mention", mentionType:22}`` doc-link mention. ``link`` is the raw
    wire form."""

    kind = "mention_doc"
    text: str = ""
    link: str | None = None

    def to_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text, "link": self.link}

    @classmethod
    def from_dict(cls, d: dict) -> "DocMention":
        return cls(text=d.get("text", "") or "", link=d.get("link"))


@dataclass(frozen=True)
class MultiSelect:
    """A multi-select cell as an **ordered label set** — the model normalizes BOTH
    wire forms (the ``{type:"multipleValue", values:[…]}`` write object and the
    comma-joined read string ``"Red,Green"``) to the **same** ``options`` tuple
    (the load-bearing read/write asymmetry — SHEETS.md, in the source repository, not in the
    wheel). Commas are forbidden inside labels, so a split on ``,`` is unambiguous; each label is stripped so the read
    ``"Red,Green"`` and the write-normalized ``"Red, Green"`` unify."""

    kind = "multi_select"
    options: tuple = ()

    @classmethod
    def from_wire(cls, value) -> "MultiSelect":
        if isinstance(value, dict):
            values = value.get("values")
            if not isinstance(values, list):
                values = value.get("value") if isinstance(value.get("value"), list) else []
            opts = [_option_label(v) for v in values]
        elif isinstance(value, str):
            opts = [p.strip() for p in value.split(",")] if value else []
        elif isinstance(value, (list, tuple)):
            opts = [_option_label(v) for v in value]
        else:
            opts = []
        return cls(options=tuple(o for o in opts if o != ""))

    def to_dict(self) -> dict:
        return {"kind": self.kind, "options": list(self.options)}

    @classmethod
    def from_dict(cls, d: dict) -> "MultiSelect":
        return cls(options=tuple(d.get("options") or ()))


@dataclass(frozen=True)
class EmbedImage:
    """An **in-cell image** — the cell's value *is* a picture (LD-446; measured LD-435 arm B).

    Wire shape, measured (capture ``203-`` of the LD-435 sheets-media spike, in the source
    repository)::

        {"type": "embed-image", "fileToken": "Exampl…", "width": 24, "height": 24,
         "text": "", "link": "internal-api-space-sg.larksuite.com/space/api/box/…"}

    Before this member existed the value fell through to *"unknown segment dict — surface
    its text"* below, and an ``embed-image``'s ``text`` is the **empty string**, so a
    picture became a blank cell with no disclosure. That fallback is **unchanged** — it is
    still what a genuinely unknown type gets; what was missing was this branch.

    ``file_token`` is the **measured** handle: the bytes come back byte-identical from
    the drive media download route
    ``drive/v1/medias/{file_token}/download`` (capture ``302-``, in the dev
    repo). **The read never fetches
    them** — the token is surfaced, not resolved, and this module reaches no
    endpoint at all.

    ``link`` is captured as raw structure and is **UNMEASURED**: an *internal-api* host URL
    carrying ``height``/``width``/``policy``/``mount_point``/``mount_node_token`` and **no
    signature parameter**, whose resolvability — for a browser, for a collaborator, or at
    all — was never established. It is therefore **never emitted into the Markdown as a
    working URL**; the render path emits the token in the reader's own image dialect. It
    lives here so a differ or a caller can see exactly what Lark said.

    ``width`` / ``height`` are the cell-image geometry. Like the docx :class:`ImageNode`'s
    geometry they have no portable Markdown form, so they are **captured here and dropped
    at render** (the D5d posture).

    **Scope of the evidence:** one tenant, one day, ``tenant_access_token``, one 88-byte
    PNG, one workbook. A ``user_access_token``, media kinds other than PNG, and multi-cell
    / merged-cell ranges are **unmeasured, not refuted**.
    """

    kind = "embed_image"
    file_token: str = ""
    width: int | None = None
    height: int | None = None
    text: str = ""
    link: str | None = None

    @classmethod
    def from_wire(cls, seg: dict) -> "EmbedImage":
        return cls(
            file_token=str(seg.get("fileToken") or ""),
            width=seg.get("width"),
            height=seg.get("height"),
            text=seg.get("text", "") or "",
            link=seg.get("link"),
        )

    def to_dict(self) -> dict:
        return {"kind": self.kind, "file_token": self.file_token,
                "width": self.width, "height": self.height,
                "text": self.text, "link": self.link}

    @classmethod
    def from_dict(cls, d: dict) -> "EmbedImage":
        return cls(file_token=d.get("file_token", "") or "",
                   width=d.get("width"), height=d.get("height"),
                   text=d.get("text", "") or "", link=d.get("link"))


def _option_label(v) -> str:
    """One multi-select option → its label string (bare string or a ``{text}`` /
    ``{type:"text", text}`` segment dict)."""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return str(v.get("text", "") or "").strip()
    return str(v).strip()


#: kind → the segment class that decodes it (JSON round-trip dispatch).
_SEGMENT_CLASSES = {
    TextRun.kind: TextRun,
    Hyperlink.kind: Hyperlink,
    UserMention.kind: UserMention,
    DocMention.kind: DocMention,
    MultiSelect.kind: MultiSelect,
    EmbedImage.kind: EmbedImage,
}


def _segment_from_dict(d: dict):
    """Decode one serialized segment by its ``kind`` discriminator."""
    return _SEGMENT_CLASSES[d["kind"]].from_dict(d)


# --------------------------------------------------------------------------- #
# Rich-cell parse — mirror render_cell's dispatch, produce typed structure      #
# (no rendering; the render path is untouched — additive, D3)                   #
# --------------------------------------------------------------------------- #

def _segment_from_wire(seg):
    """One wire segment → a typed segment (or ``None`` for a non-segment scalar).

    Mirrors :func:`larkdocio.sheets.render._segment_to_str` dispatch, but yields
    typed structure instead of Markdown."""
    if seg is None:
        return None
    if isinstance(seg, str):
        return TextRun(text=seg, style=SegmentStyle())
    if isinstance(seg, dict):
        seg_type = seg.get("type")
        if seg_type == "text":
            return TextRun(text=seg.get("text", "") or "",
                           style=SegmentStyle.from_wire(seg.get("segmentStyle")))
        if seg_type == "url":
            return Hyperlink(text=seg.get("text", "") or "", link=seg.get("link") or "")
        if seg_type == "mention":
            if seg.get("mentionType") == 22:
                return DocMention(text=seg.get("text", "") or "", link=seg.get("link"))
            return UserMention(
                text=seg.get("text", "") or "",
                user_id=seg.get("userID") or seg.get("token"),
                name=seg.get("name") or seg.get("en_name"),
            )
        if seg_type == "multipleValue":
            return MultiSelect.from_wire(seg)
        if seg_type == "embed-image":
            # BEFORE the catch-all: an in-cell image's `text` is "" (measured, LD-435
            # capture `203-`), so the fallback below turned a picture into a blank cell.
            return EmbedImage.from_wire(seg)
        # Unknown segment dict — surface its text as a plain run (never raise).
        return TextRun(text=str(seg.get("text", "") or ""), style=SegmentStyle())
    # Any other scalar inside a list is not a rich segment.
    return None


def parse_segments(value) -> tuple:
    """Parse a cell value into its typed segment structure.

    A rich **list** cell (styled runs / a hyperlink) → a tuple of typed segments;
    a rich **dict** cell (mention / url / multi-select) → a one-element tuple; a
    scalar / display string / ``None`` → an empty tuple (its value lives in
    ``raw`` / ``display``, not in a segment). Never raises."""
    if isinstance(value, list):
        return tuple(s for s in (_segment_from_wire(x) for x in value) if s is not None)
    if isinstance(value, dict):
        seg = _segment_from_wire(value)
        return (seg,) if seg is not None else ()
    return ()


# --------------------------------------------------------------------------- #
# Export-only fidelity (from the S1 xlsx-export reader) — None when no export    #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class CellFidelity:
    """The export-only, **whole-cell (format-level)** fidelity: the number-format
    **pattern** + **bold / italic / fill** from ``xl/styles.xml``.

    "Whole-cell" is the precise scope, and it matters: these are the styles applied to the
    **cell** — which the values API does not carry — **not** the emphasis on a text **run**
    inside the cell, which travels in the values API's own ``segmentStyle`` and is already
    available without any export. A run-styled cell therefore reports ``bold=False`` here,
    correctly: its bold is not a property of the cell.

    Present **only** when an export is available; a :class:`TypedCell` built without
    an export carries ``fidelity=None`` (never these fields half-set). ``fill_rgb`` is
    an ARGB string captured for the differ — it is **dropped at render**."""

    num_fmt: str | None = None
    bold: bool = False
    italic: bool = False
    fill_rgb: str | None = None

    @classmethod
    def from_exported_cell(cls, ec) -> "CellFidelity":
        """Build from an S1 :class:`~larkdocio.sheets.export_reader.ExportedCell`
        (duck-typed: ``num_fmt`` / ``bold`` / ``italic`` / ``fill_rgb``)."""
        return cls(
            num_fmt=ec.num_fmt,
            bold=bool(ec.bold),
            italic=bool(ec.italic),
            fill_rgb=ec.fill_rgb,
        )

    def to_dict(self) -> dict:
        return {"num_fmt": self.num_fmt, "bold": self.bold,
                "italic": self.italic, "fill_rgb": self.fill_rgb}

    @classmethod
    def from_dict(cls, d: dict) -> "CellFidelity":
        return cls(num_fmt=d.get("num_fmt"), bold=bool(d.get("bold")),
                   italic=bool(d.get("italic")), fill_rgb=d.get("fill_rgb"))


# --------------------------------------------------------------------------- #
# Merge membership                                                              #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class MergeMembership:
    """A cell's role in a merged region: ``anchor`` (the top-left, keeps its value),
    ``covered`` (blanked in the MD merge join), or ``none`` (not merged). ``region``
    is the :class:`~larkdocio.sheets.models.Merge` (0-indexed, END-inclusive) or
    ``None`` when the cell is not merged."""

    role: str = MERGE_NONE
    region: Merge | None = None

    @property
    def is_anchor(self) -> bool:
        return self.role == MERGE_ANCHOR

    @property
    def is_covered(self) -> bool:
        return self.role == MERGE_COVERED

    @property
    def is_merged(self) -> bool:
        return self.role != MERGE_NONE

    def to_dict(self) -> dict:
        return {"role": self.role, "region": _merge_to_dict(self.region)}

    @classmethod
    def from_dict(cls, d: dict) -> "MergeMembership":
        d = d or {}
        return cls(role=d.get("role", MERGE_NONE), region=_merge_from_dict(d.get("region")))


def _merge_to_dict(m: Merge | None):
    if m is None:
        return None
    return {"start_row": m.start_row, "end_row": m.end_row,
            "start_col": m.start_col, "end_col": m.end_col}


def _merge_from_dict(d):
    if not d:
        return None
    return Merge(start_row=d["start_row"], end_row=d["end_row"],
                 start_col=d["start_col"], end_col=d["end_col"])


def merge_membership_at(row: int, col: int, merges) -> MergeMembership:
    """The :class:`MergeMembership` of the 0-indexed ``(row, col)`` cell against a
    tab's ``merges`` (0-indexed, END-inclusive — spike Q3). The top-left of a region
    is the ``anchor``; every other cell inside it is ``covered``; a cell in no region
    is ``none``. Consistent with :func:`larkdocio.sheets.table.merge_covered_cells`."""
    for m in merges or ():
        if m.start_row <= row <= m.end_row and m.start_col <= col <= m.end_col:
            if row == m.start_row and col == m.start_col:
                return MergeMembership(role=MERGE_ANCHOR, region=m)
            return MergeMembership(role=MERGE_COVERED, region=m)
    return MergeMembership(role=MERGE_NONE, region=None)


# --------------------------------------------------------------------------- #
# The typed cell                                                                #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class TypedCell:
    """One spreadsheet cell as a typed, serializable model (additive to L1, D3).

    ``raw`` is the values-API ``UnformattedValue``; ``display`` the ``FormattedValue``
    — the **dual**. ``segments`` is the rich-cell structure (empty for a scalar).
    ``fidelity`` is the export-only style/numFmt (``None`` when no export was joined).
    ``merge`` is the merge membership (defaults to not-merged)."""

    raw: object = None
    display: object = None
    segments: tuple = ()
    fidelity: CellFidelity | None = None
    merge: MergeMembership = field(default_factory=MergeMembership)

    # -- None-safe fidelity accessors (never raise on a no-export cell) ------ #

    @property
    def num_fmt(self) -> str | None:
        return self.fidelity.num_fmt if self.fidelity is not None else None

    @property
    def is_bold(self) -> bool | None:
        return self.fidelity.bold if self.fidelity is not None else None

    @property
    def is_italic(self) -> bool | None:
        return self.fidelity.italic if self.fidelity is not None else None

    @property
    def fill_rgb(self) -> str | None:
        return self.fidelity.fill_rgb if self.fidelity is not None else None

    # -- construction -------------------------------------------------------- #

    @classmethod
    def from_values(cls, *, raw=None, display=None, exported_cell=None, merge=None) -> "TypedCell":
        """Build from a values-API cell (raw + display) and, optionally, an S1
        ``ExportedCell`` (the export-fidelity join) + a merge membership.

        Enrichment is optional: with ``exported_cell=None`` the model is values-only
        and ``fidelity`` is ``None`` (graceful — never raises). Segments are parsed
        from the display value (falling back to raw)."""
        source = display if display is not None else raw
        segments = parse_segments(source)
        fidelity = (
            CellFidelity.from_exported_cell(exported_cell)
            if exported_cell is not None else None
        )
        return cls(
            raw=raw,
            display=display,
            segments=segments,
            fidelity=fidelity,
            merge=merge or MergeMembership(),
        )

    @classmethod
    def at_position(cls, row, col, *, raw=None, display=None,
                    merges=(), exported_sheet=None) -> "TypedCell":
        """Build the cell at 0-indexed ``(row, col)``: merge membership from
        ``merges``, and the export fidelity looked up by A1 ``ref`` in
        ``exported_sheet`` (an S1 ``ExportedSheet``; ``None`` → no export, graceful)."""
        merge = merge_membership_at(row, col, merges)
        exported_cell = None
        if exported_sheet is not None:
            ref = f"{column_number_to_a1(col + 1)}{row + 1}"
            exported_cell = exported_sheet.cell(ref)
        return cls.from_values(raw=raw, display=display,
                               exported_cell=exported_cell, merge=merge)

    # -- serialization (JSON round-trippable) -------------------------------- #

    def to_dict(self) -> dict:
        """A JSON-native dict (``raw`` / ``display`` are already JSON values; the
        segments / fidelity / merge use a discriminated encoding)."""
        return {
            "raw": self.raw,
            "display": self.display,
            "segments": [s.to_dict() for s in self.segments],
            "fidelity": self.fidelity.to_dict() if self.fidelity is not None else None,
            "merge": self.merge.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TypedCell":
        return cls(
            raw=d.get("raw"),
            display=d.get("display"),
            segments=tuple(_segment_from_dict(s) for s in (d.get("segments") or [])),
            fidelity=(CellFidelity.from_dict(d["fidelity"])
                      if d.get("fidelity") is not None else None),
            merge=MergeMembership.from_dict(d.get("merge") or {}),
        )
