"""larkdocio.sheets.export_reader — the stdlib-only xlsx-export reader.

Head of the L2 read-fidelity chain. The **L2 crux**, confirmed by a live probe: a cell's **style**
(bold / italic / fill) and its **number-format pattern** are **NOT readable** through
the values API, ``metainfo``, or any v3 surface — the **only** full-fidelity style/
format read is the drive ``export_tasks`` → xlsx path. This module builds that leg into
``src/``:

1. **Export task lifecycle** — ``POST /drive/v1/export_tasks {file_extension:"xlsx",
   token, type:"sheet"}`` → poll ``GET /drive/v1/export_tasks/{ticket}?token=`` until
   ``job_status == 0`` → download ``GET /drive/v1/export_tasks/file/{file_token}/download``.
   Failures map to the typed taxonomy (:class:`~larkdocio.errors.LarkAPIError` /
   :class:`~larkdocio.errors.LarkRateLimitError`); the poll loop is **bounded** (never
   infinite) and **gentle** (≥0.5s between polls, and every HTTP call routes a
   :class:`~larkdocio.common.transport.RateLimiter`).

2. **Stdlib-only parse (ABSOLUTE)** — the downloaded workbook is parsed with
   **``zipfile`` + ``xml.etree.ElementTree`` only** (no ``openpyxl`` / ``lxml`` /
   ``pandas`` / any new dependency). It reads ``xl/styles.xml`` (numFmts, fonts incl
   ``<b/>``/``<i/>``, fills), ``xl/worksheets/sheetN.xml`` (per-cell ``s=`` style index,
   ``<v>``/inline ``<is>``, ``<mergeCell>`` refs), ``xl/sharedStrings.xml``, and the
   ``xl/workbook.xml`` (+ rels) sheet map, resolving each cell → its value + resolved
   style (bold / italic / fill / numFmt pattern). Malformed workbooks never crash —
   a corrupt zip / malformed XML raise the typed :class:`XlsxParseError`; a missing
   ``styles.xml`` / dangling ``s=`` index / unknown numFmt id degrade gracefully to the
   default style with the value intact.

**Credential duty — cred-agnostic core, least-privilege construction.** The core
takes a **``token_provider``** (a zero-arg callable → a tenant bearer token), so it
hard-binds **neither** the READ nor the WRITE app. The two classmethods pin the
split:

* :meth:`SheetsExportReader.from_write_credentials` — the **write-gate** fidelity leg:
  resolves the WRITE pair via
  :func:`~larkdocio.common.auth.get_write_credentials` (no read/legacy fallback).
* :meth:`SheetsExportReader.from_read_credentials` — the **read-side** fidelity leg
  (the opt-in fidelity read): resolves the READ pair via
  :func:`~larkdocio.common.auth.get_read_credentials`. The scope requirement is OWNED by
  :mod:`larkdocio.permissions` (this leg's rows are on the ``sheets-read`` surface); the
  READ-app ``drive:export``
  scope is **PROVEN** (probed 2026-07-27: ``POST export_tasks`` on the
  scratch sheet → ``code 0``, poll ``job_status:0``, ``file_token`` present), so the
  read-side export runs **least-privilege on READ creds** — a read never consults write
  creds (credential doctrine). **Scope is never self-escalated beyond what a probe proved.**

**Scope.** This returns parsed **style / value / merge facts**
(:class:`ExportedCell` / :class:`ExportedSheet` / :class:`ParsedWorkbook`) — the typed
cell model, the two-leg differ and the MD fidelity gains each have
their own module. Location: flat in ``src/larkdocio/sheets/`` alongside the L1 surface,
matching the ``write_client`` / ``write_range`` naming.
"""
import io
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field

from larkdocio.common.auth import (
    WRITE_ENV,
    apply_ipv4_pin,
    get_read_credentials,
    get_write_credentials,
    resolved_read_env,
)
from larkdocio.common.transport import (
    RateLimiter,
    RawHttpClient,
    api_base,
    fetch_tenant_access_token,
    raise_for_lark_code,
)
from larkdocio.errors import LarkAPIError, LarkConfigError, LarkDocIOError

# --------------------------------------------------------------------------- #
# Constants                                                                     #
# --------------------------------------------------------------------------- #

#: The drive export-task base path.
EXPORT_TASKS_PATH = "/open-apis/drive/v1/export_tasks"

#: A worksheet part path (used only for the no-sheet-map discovery fallback).
_WS_ARC_RE = re.compile(r"xl/worksheets/sheet\d+\.xml")

#: Gentle poll floor (spike Q5 posture): the poll loop never polls faster than this.
MIN_POLL_INTERVAL = 0.5
DEFAULT_POLL_INTERVAL = 0.5

#: Bounded poll ceiling — the loop raises rather than spinning forever. 60 polls ×
#: 0.5s ≈ 30s, comfortably above a normal single-sheet export.
DEFAULT_MAX_POLLS = 60

#: Client-side cap for the export HTTP calls — gentle, well under Lark's ceilings.
DEFAULT_MAX_CALLS_PER_SEC = 5

#: ``job_status`` values that mean "still running" (keep polling): 1 initializing,
#: 2 processing, 3 finalizing. ``0`` is done; anything else non-zero is a failure.
EXPORT_PENDING_STATUSES = frozenset({1, 2, 3})

#: A small subset of the ECMA-376 built-in number formats (numFmtId → pattern) so a
#: cell using a standard format id — not a custom ``<numFmt>`` — still resolves its
#: pattern. Lark writes CUSTOM ids (≥164) for the formats it applies, so this is a
#: robustness backstop, not the main path. General (0) → no pattern (``None``).
BUILTIN_NUM_FMTS = {
    1: "0",
    2: "0.00",
    3: "#,##0",
    4: "#,##0.00",
    9: "0%",
    10: "0.00%",
    11: "0.00E+00",
    14: "mm-dd-yy",
    22: "m/d/yy h:mm",
    49: "@",
}


# --------------------------------------------------------------------------- #
# Typed parse errors                                                            #
# --------------------------------------------------------------------------- #

class XlsxParseError(LarkDocIOError):
    """A downloaded workbook could not be parsed (corrupt zip / malformed XML).

    Under :class:`~larkdocio.errors.LarkDocIOError` so ``except LarkDocIOError``
    catches it alongside the API/config family. Raised only for genuinely
    unparseable input — recoverable oddities (missing ``styles.xml``, a dangling
    ``s=`` index, an unknown numFmt id) degrade gracefully instead of raising."""


# --------------------------------------------------------------------------- #
# Parsed result model (LD-114 returns facts; the typed cell model is S2)        #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ExportedCell:
    """One parsed cell: its A1 ``ref``, its ``value``, and its resolved style
    (``bold`` / ``italic`` / ``fill_rgb`` ARGB / ``num_fmt`` pattern)."""

    ref: str
    value: object
    bold: bool = False
    italic: bool = False
    fill_rgb: str | None = None
    num_fmt: str | None = None


@dataclass(frozen=True)
class ExportedDimension:
    """One row's or column's **dimension property** — its ``size``, whether that size is a
    custom one, and whether it is ``hidden``.

    **The export is the only read that can see this.** ``metainfo`` reports sheet-level
    ``frozen*`` / ``rowCount`` / ``columnCount`` and the v3 tab query reports
    ``grid_properties`` plus the **tab's** own ``hidden`` flag; neither carries a row height, a
    column width, or a row/column hidden state (probed live against a throwaway spreadsheet,
    after eleven dimension writes). So this is the verification leg of the gated dimension-property write
    (:class:`~larkdocio.sheets.requests.SetRowProperties` /
    :class:`~larkdocio.sheets.requests.SetColProperties`), exactly as the export is the only
    leg that can see style.

    ``size`` is reported **as the xlsx carries it** — a row's ``ht`` in points, a column's
    ``width`` in character units — deliberately **not** converted to the pixels the write takes.
    The observed relation is not 1:1 (a 60 px row came back ``ht="44"``, a 200 px column
    ``width="25"``), and inventing a conversion factor to make a round-trip assertion look tidy
    would be exactly the guess this issue exists to avoid. Compare it against the sheet's
    ``default_row_height`` / ``default_col_width``, or against a before-snapshot.

    ``custom_size`` is the raw ``customHeight`` / ``customWidth`` flag and is **not** a reliable
    "someone set a size" signal on its own: hiding a row emits ``customHeight="true"`` with the
    tab's *default* ``ht`` (observed live). Read ``hidden`` for visibility and ``size`` for size.
    """

    index: int
    size: str | None = None
    custom_size: bool = False
    hidden: bool = False


@dataclass
class ExportedSheet:
    """One worksheet: its ``name``, its ``cells`` (``ref`` → :class:`ExportedCell`),
    its ``merges`` (A1 range strings, e.g. ``"A1:C1"``), and its
    **dimension properties**: ``row_dimensions`` / ``col_dimensions`` (1-indexed index →
    :class:`ExportedDimension`, present only for a row/column that carries one) plus the
    sheet's ``default_row_height`` / ``default_col_width`` to compare them against."""

    name: str
    cells: dict = field(default_factory=dict)
    merges: tuple = ()
    row_dimensions: dict = field(default_factory=dict)
    col_dimensions: dict = field(default_factory=dict)
    default_row_height: str | None = None
    default_col_width: str | None = None

    def cell(self, ref: str):
        """The :class:`ExportedCell` at ``ref`` (e.g. ``"A1"``), or ``None``."""
        return self.cells.get(ref)

    def row_dimension(self, row: int):
        """The :class:`ExportedDimension` for **1-indexed** ``row``, or ``None`` when that row
        carries no dimension property at all (the overwhelmingly common case — an untouched
        row is emitted as a bare ``<row r="7">``)."""
        return self.row_dimensions.get(row)

    def col_dimension(self, col: int):
        """The :class:`ExportedDimension` for **1-indexed** ``col`` (``1`` = ``A``), or
        ``None``."""
        return self.col_dimensions.get(col)


@dataclass
class ParsedWorkbook:
    """A parsed xlsx: its ``sheets`` in workbook order."""

    sheets: tuple = ()

    @property
    def first_sheet(self) -> ExportedSheet:
        return self.sheets[0]

    def sheet(self, name: str):
        """The sheet named ``name``, or ``None``."""
        for s in self.sheets:
            if s.name == name:
                return s
        return None


def _tab_identity(tab) -> tuple:
    """``(sheet_id, title)`` from a tab, whichever shape it comes in.

    ``SheetsReadClient.query_sheets`` hands back :class:`~larkdocio.sheets.models.SheetTab`
    objects and ``SheetsWriteClient.query_tabs`` hands back plain dicts; a join that spoke
    only one of them would recreate the very title-vs-id confusion it exists to remove.
    """
    if isinstance(tab, dict):
        sheet_id, title = tab.get("sheet_id"), tab.get("title")
    else:
        sheet_id, title = getattr(tab, "sheet_id", None), getattr(tab, "title", None)
    if not sheet_id:
        raise ValueError(
            f"cannot join this tab to an exported worksheet: it carries no sheet_id ({tab!r}). "
            f"Pass the tabs a client returned — query_sheets(...) (SheetTab objects) or "
            f"query_tabs(...) (dicts) — not a hand-built list."
        )
    return sheet_id, title


def exported_by_sheet_id(tabs, workbook) -> dict:
    """``{sheet_id: ExportedSheet}`` — the map the values→Markdown renderer's ``fidelity=``
    argument takes, joined from a **title-keyed** export to **id-keyed** tabs.

    An xlsx export names each worksheet after the tab's **title**, while every range, every
    read and the renderer's own per-tab lookup are keyed on the tab's opaque ``sheet_id`` —
    so reading a whole spreadsheet at style fidelity needs this one join. It is shipped
    rather than left to the caller because the two rules that make it correct are invisible
    from either side:

    * **A tab whose worksheet is absent is omitted**, so that tab renders **values-only**.
      Never an exception, and never another sheet's styles — the failure mode is silent,
      wrong emphasis on real cells.
    * **The sole-sheet fallback needs one tab AND one worksheet.** A single-tab spreadsheet
      whose worksheet came back under a different name still joins (the behaviour the
      shipped embedded-sheet fidelity leg already has); with two tabs and one worksheet the
      answer is genuinely unknown, so nothing is joined rather than guessed.

    ``workbook`` may be ``None`` (a failed or skipped export) — the result is then an empty
    map, i.e. a values-only render. Two tabs sharing a title both legitimately match the one
    worksheet, and both are reported.
    """
    if workbook is None:
        return {}
    sheets = tuple(getattr(workbook, "sheets", ()) or ())
    tabs = list(tabs or ())
    out = {}
    for tab in tabs:
        sheet_id, title = _tab_identity(tab)
        exported = workbook.sheet(title) if title else None
        if exported is None and len(sheets) == 1 and len(tabs) == 1:
            exported = sheets[0]
        if exported is not None:
            out[sheet_id] = exported
    return out


# --------------------------------------------------------------------------- #
# XML helpers — local-name matching (namespace-agnostic, stdlib only)           #
# --------------------------------------------------------------------------- #

def _ln(tag: str) -> str:
    """The local name of a (possibly namespaced) tag/attr key: ``{ns}b`` → ``b``."""
    return tag.rsplit("}", 1)[-1]


def _children(elem, name):
    return [c for c in elem if _ln(c.tag) == name]


def _child(elem, name):
    for c in elem:
        if _ln(c.tag) == name:
            return c
    return None


def _attr(elem, name):
    """An attribute value by local name (matches ``r:id`` → ``id``, etc.)."""
    for k, v in elem.attrib.items():
        if _ln(k) == name:
            return v
    return None


def _int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_attr(elem) -> bool:
    """Truthiness of a ``<b/>`` / ``<i/>`` toggle: present-with-no-``val`` is True;
    ``val`` is truthy for ``1``/``true``/``on``/``yes``."""
    if elem is None:
        return False
    v = _attr(elem, "val")
    if v is None:
        return True
    return str(v).strip().lower() in ("1", "true", "on", "yes")


def _collect_text(elem) -> str:
    """Concatenate every ``<t>`` text under ``elem`` (handles ``<is><t>`` and rich
    ``<is><r><t>`` / ``<si><r><t>`` shapes)."""
    return "".join(t.text for t in elem.iter() if _ln(t.tag) == "t" and t.text)


# --------------------------------------------------------------------------- #
# Style tables (xl/styles.xml)                                                  #
# --------------------------------------------------------------------------- #

@dataclass
class _StyleTables:
    num_fmts: dict = field(default_factory=dict)   # numFmtId -> formatCode
    fonts: list = field(default_factory=list)      # [{"bold","italic"}]
    fills: list = field(default_factory=list)      # [{"fg_rgb"}]
    cell_xfs: list = field(default_factory=list)   # [{"numFmtId","fontId","fillId"}]


def _parse_styles(root) -> _StyleTables:
    tables = _StyleTables()
    nfs = _child(root, "numFmts")
    if nfs is not None:
        for nf in _children(nfs, "numFmt"):
            fid = _int(_attr(nf, "numFmtId"))
            code = _attr(nf, "formatCode")
            if fid is not None:
                tables.num_fmts[fid] = code
    fonts_el = _child(root, "fonts")
    if fonts_el is not None:
        for f in _children(fonts_el, "font"):
            tables.fonts.append({
                "bold": _bool_attr(_child(f, "b")),
                "italic": _bool_attr(_child(f, "i")),
            })
    fills_el = _child(root, "fills")
    if fills_el is not None:
        for f in _children(fills_el, "fill"):
            pf = _child(f, "patternFill")
            rgb = None
            if pf is not None:
                fg = _child(pf, "fgColor")
                if fg is not None:
                    rgb = _attr(fg, "rgb")
            tables.fills.append({"fg_rgb": rgb})
    xfs_el = _child(root, "cellXfs")
    if xfs_el is not None:
        for xf in _children(xfs_el, "xf"):
            tables.cell_xfs.append({
                "numFmtId": _int(_attr(xf, "numFmtId")),
                "fontId": _int(_attr(xf, "fontId")),
                "fillId": _int(_attr(xf, "fillId")),
            })
    return tables


def _resolve_style(tables: _StyleTables, s_index):
    """Resolve a cell's ``s=`` index to ``(bold, italic, fill_rgb, num_fmt)``.

    Every lookup is bounds-checked: a missing/dangling index, a missing styles.xml
    (empty tables), or an unknown numFmt id all degrade to the default (no style) —
    never an ``IndexError`` / ``KeyError``."""
    idx = 0 if s_index is None else s_index
    if idx < 0 or idx >= len(tables.cell_xfs):
        return False, False, None, None
    xf = tables.cell_xfs[idx]

    font_id = xf.get("fontId") or 0
    font = tables.fonts[font_id] if 0 <= font_id < len(tables.fonts) else {}
    bold = bool(font.get("bold"))
    italic = bool(font.get("italic"))

    fill_id = xf.get("fillId") or 0
    fill = tables.fills[fill_id] if 0 <= fill_id < len(tables.fills) else {}
    fill_rgb = fill.get("fg_rgb")

    num_fmt_id = xf.get("numFmtId") or 0
    num_fmt = tables.num_fmts.get(num_fmt_id)
    if num_fmt is None:
        num_fmt = BUILTIN_NUM_FMTS.get(num_fmt_id)
    return bold, italic, fill_rgb, num_fmt


# --------------------------------------------------------------------------- #
# Worksheet + value parsing                                                     #
# --------------------------------------------------------------------------- #

def _cell_value(c, shared_strings):
    """The typed value of a ``<c>`` element (never raises — falls back to the raw
    string on an unparseable numeric)."""
    t = _attr(c, "t")
    if t == "inlineStr":
        is_el = _child(c, "is")
        return _collect_text(is_el) if is_el is not None else None
    v_el = _child(c, "v")
    if v_el is None or v_el.text is None:
        return None
    raw = v_el.text
    if t == "s":
        idx = _int(raw)
        if idx is not None and 0 <= idx < len(shared_strings):
            return shared_strings[idx]
        return None
    if t == "str":
        return raw
    if t == "b":
        return raw.strip() not in ("0", "false", "False", "")
    if t == "e":
        return raw
    return _num(raw)


def _num(raw):
    raw = raw.strip()
    try:
        if any(ch in raw for ch in ".eE"):
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _xlsx_flag(value) -> bool:
    """An xlsx boolean attribute: ``"1"`` / ``"true"`` / ``"on"`` are true, everything else
    (including the explicit ``"false"`` Lark's export writes) is false."""
    return str(value).strip().lower() in ("1", "true", "on", "yes")


def _row_dimension(row):
    """The :class:`ExportedDimension` a ``<row>`` element carries, or ``None`` when it carries
    none (a bare ``<row r="7">`` — what an untouched row is emitted as)."""
    index = _int(_attr(row, "r"))
    if index is None:
        return None
    ht = _attr(row, "ht")
    custom = _attr(row, "customHeight")
    hidden = _attr(row, "hidden")
    if ht is None and custom is None and hidden is None:
        return None
    return ExportedDimension(index=index, size=ht, custom_size=_xlsx_flag(custom),
                             hidden=_xlsx_flag(hidden))


def _read_col_dimensions(root) -> dict:
    """``{1-indexed column: ExportedDimension}`` from ``<cols><col min max …>``.

    **A later entry for the same column WINS**, which is not a stylistic choice: Lark's export
    emits a hidden column **twice** — once ``hidden="false"``, then ``hidden="true"``
    (captured verbatim, in the source repository, in
    ``tests/captures/sheets-dimension-probe/captures/03-raw-xlsx-dimension-XML.json``).
    Taking the first would report a hidden column as visible, which is the exact class of
    silent-fidelity error this op's disclosure exists to prevent.
    """
    out = {}
    cols = _child(root, "cols")
    if cols is None:
        return out
    for col in _children(cols, "col"):
        lo, hi = _int(_attr(col, "min")), _int(_attr(col, "max"))
        if lo is None:
            continue
        hi = lo if hi is None else hi
        width = _attr(col, "width")
        custom = _attr(col, "customWidth")
        hidden = _attr(col, "hidden")
        for index in range(lo, hi + 1):
            out[index] = ExportedDimension(
                index=index, size=width, custom_size=_xlsx_flag(custom),
                hidden=_xlsx_flag(hidden))
    return out


def _read_worksheet(root, shared_strings, tables):
    cells = {}
    row_dimensions = {}
    sheet_data = _child(root, "sheetData")
    if sheet_data is not None:
        for row in _children(sheet_data, "row"):
            dimension = _row_dimension(row)
            if dimension is not None:
                row_dimensions[dimension.index] = dimension
            for c in _children(row, "c"):
                ref = _attr(c, "r")
                if ref is None:
                    continue
                bold, italic, fill_rgb, num_fmt = _resolve_style(
                    tables, _int(_attr(c, "s"))
                )
                cells[ref] = ExportedCell(
                    ref=ref,
                    value=_cell_value(c, shared_strings),
                    bold=bold,
                    italic=italic,
                    fill_rgb=fill_rgb,
                    num_fmt=num_fmt,
                )
    merges = []
    mc = _child(root, "mergeCells")
    if mc is not None:
        for m in _children(mc, "mergeCell"):
            ref = _attr(m, "ref")
            if ref:
                merges.append(ref)
    fmt = _child(root, "sheetFormatPr")
    dimensions = {
        "row_dimensions": row_dimensions,
        "col_dimensions": _read_col_dimensions(root),
        "default_row_height": _attr(fmt, "defaultRowHeight") if fmt is not None else None,
        "default_col_width": _attr(fmt, "defaultColWidth") if fmt is not None else None,
    }
    return cells, tuple(merges), dimensions


# --------------------------------------------------------------------------- #
# Workbook assembly (sheet map, shared strings, styles)                         #
# --------------------------------------------------------------------------- #

def _parse_xml(zf, arc):
    try:
        return ET.fromstring(zf.read(arc))
    except ET.ParseError as e:
        raise XlsxParseError(f"malformed XML in {arc}: {e}") from e


def _read_shared_strings(zf, names):
    if "xl/sharedStrings.xml" not in names:
        return []
    root = _parse_xml(zf, "xl/sharedStrings.xml")
    return [_collect_text(si) for si in _children(root, "si")]


def _read_styles(zf, names):
    if "xl/styles.xml" not in names:
        return _StyleTables()
    return _parse_styles(_parse_xml(zf, "xl/styles.xml"))


def _read_workbook_rels(zf, names):
    arc = "xl/_rels/workbook.xml.rels"
    rels = {}
    if arc not in names:
        return rels
    root = _parse_xml(zf, arc)
    for r in _children(root, "Relationship"):
        rid = _attr(r, "Id")
        target = _attr(r, "Target") or ""
        if target and not target.startswith("/") and not target.startswith("xl/"):
            target = "xl/" + target.lstrip("./")
        rels[rid] = target
    return rels


def _resolve_sheets(zf, names):
    """The ordered ``[(sheet_name, worksheet_arcname)]`` — from the workbook.xml
    sheet map (+ rels) when present, else by discovering ``sheetN.xml`` in order."""
    if "xl/workbook.xml" in names:
        wb = _parse_xml(zf, "xl/workbook.xml")
        sheets_el = _child(wb, "sheets")
        rels = _read_workbook_rels(zf, names)
        entries = []
        if sheets_el is not None:
            for i, sh in enumerate(_children(sheets_el, "sheet")):
                name = _attr(sh, "name") or f"Sheet{i + 1}"
                arc = rels.get(_attr(sh, "id"))
                if not arc or arc not in names:
                    arc = f"xl/worksheets/sheet{i + 1}.xml"
                entries.append((name, arc))
        if entries:
            return entries
    discovered = sorted(n for n in names if _WS_ARC_RE.fullmatch(n))
    return [(f"Sheet{i + 1}", arc) for i, arc in enumerate(discovered)]


def parse_xlsx(data: bytes) -> ParsedWorkbook:
    """Parse xlsx bytes → :class:`ParsedWorkbook` with ``zipfile`` + ``xml.etree`` only.

    Raises :class:`XlsxParseError` on a non-zip / corrupt-zip / malformed-XML input;
    recoverable oddities (missing styles, dangling ``s=``, unknown numFmt) degrade to
    the default style with the value intact (never a crash)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise XlsxParseError(f"export download is not a valid xlsx zip: {e}") from e
    with zf:
        names = set(zf.namelist())
        shared = _read_shared_strings(zf, names)
        tables = _read_styles(zf, names)
        sheets = []
        for name, arc in _resolve_sheets(zf, names):
            if arc not in names:
                sheets.append(ExportedSheet(name=name))
                continue
            cells, merges, dimensions = _read_worksheet(_parse_xml(zf, arc), shared, tables)
            sheets.append(ExportedSheet(name=name, cells=cells, merges=merges, **dimensions))
    return ParsedWorkbook(sheets=tuple(sheets))


# --------------------------------------------------------------------------- #
# Credential-bound token providers (D1 least-privilege construction)            #
# --------------------------------------------------------------------------- #

def _credential_token_provider(app_id, app_secret, domain, token_fetcher=None):
    """A lazily-caching token provider bound to one credential pair. The core stays
    cred-agnostic; this is how the two classmethods pin the D1 read/write split.

    ``token_fetcher`` is resolved to the module-level
    :func:`~larkdocio.common.transport.fetch_tenant_access_token` at **call** time
    (not bound at definition) so the real fetch is a stable monkeypatch point."""
    box = {"token": None}

    def provider():
        if box["token"] is None:
            fetcher = token_fetcher or fetch_tenant_access_token
            box["token"] = fetcher(app_id, app_secret, domain)
        return box["token"]

    return provider


# --------------------------------------------------------------------------- #
# The export reader                                                             #
# --------------------------------------------------------------------------- #

class SheetsExportReader(RawHttpClient):
    """Throttled, typed, **cred-agnostic** xlsx-export reader.

    The core takes a ``token_provider`` (a zero-arg callable → a bearer token), so it
    binds neither app; :meth:`from_write_credentials` / :meth:`from_read_credentials`
    pin the least-privilege split. ``urlopen`` / ``rate_limiter`` / ``sleep_fn`` are
    injectable so the lifecycle, throttling, and poll-pacing are unit-testable offline
    (``tests/test_sheets_export_reader.py``)."""

    def __init__(
        self,
        token_provider,
        domain="larksuite.com",
        *,
        urlopen=urllib.request.urlopen,
        rate_limiter=None,
        sleep_fn=time.sleep,
        poll_interval=DEFAULT_POLL_INTERVAL,
        max_polls=DEFAULT_MAX_POLLS,
        timeout=60,
        credential_env=(),
    ):
        #: The env-var names of the pair this reader's token_provider resolves. Empty when a
        #: caller supplies a bare provider: this class is deliberately credential-agnostic, so
        #: it does not guess which app a provider speaks for — the factories below know, and a
        #: denial attributed to the wrong pair would send someone to edit the wrong variable.
        self._credential_env = tuple(credential_env)
        if poll_interval < MIN_POLL_INTERVAL:
            raise LarkConfigError(
                f"export poll interval must be >= {MIN_POLL_INTERVAL}s (be gentle); "
                f"got {poll_interval}."
            )
        self._token_provider = token_provider
        self._domain = domain
        self._base = api_base(domain)
        self._urlopen = urlopen
        self._sleep = sleep_fn
        self._limiter = rate_limiter or RateLimiter(
            DEFAULT_MAX_CALLS_PER_SEC, sleep_fn=sleep_fn
        )
        self._poll_interval = poll_interval
        self._max_polls = max_polls
        self._timeout = timeout
        self._token = None

    def _credential_pair(self):
        """Whatever pair the caller declared for this reader's ``token_provider`` — the same
        answer its scope denials carry, and ``()`` for a bare provider (LD-672). This class
        stays credential-agnostic on purpose: guessing which app a provider speaks for is how
        a refusal names the wrong variable."""
        return self._credential_env

    # -- construction (D1 least-privilege) ------------------------------- #

    @classmethod
    def from_write_credentials(cls, domain="larksuite.com", **kwargs):
        """Build the **write-gate** fidelity-leg reader on the WRITE app.

        Resolves the WRITE pair via
        :func:`~larkdocio.common.auth.get_write_credentials` (no read/legacy
        fallback → :class:`~larkdocio.errors.LarkConfigError`); applies the shared
        IPv4 pin. The write-gate differ exports baseline + post-write under this
        app."""
        app_id, app_secret = get_write_credentials()
        apply_ipv4_pin()
        kwargs.setdefault("credential_env", WRITE_ENV)
        return cls(_credential_token_provider(app_id, app_secret, domain), domain, **kwargs)

    @classmethod
    def from_read_credentials(cls, domain="larksuite.com", **kwargs):
        """Build the **read-side** fidelity-leg reader on the READ app.

        Resolves the READ pair via
        :func:`~larkdocio.common.auth.get_read_credentials` (``LARK_READ_APP_*`` →
        legacy). The READ-app ``drive:export`` scope is **PROVEN** (probed
        2026-07-27), so the opt-in fidelity read runs least-privilege here —
        never the write app. Missing read creds are a loud
        :class:`~larkdocio.errors.LarkConfigError`."""
        app_id, app_secret = get_read_credentials()
        if not app_id or not app_secret:
            raise LarkConfigError(
                "Sheets export reader: no READ credentials resolved. Set "
                "LARK_READ_APP_ID/LARK_READ_APP_SECRET (or the legacy "
                "LARK_APP_ID/LARK_APP_SECRET)."
            )
        apply_ipv4_pin()
        kwargs.setdefault("credential_env", resolved_read_env())
        return cls(_credential_token_provider(app_id, app_secret, domain), domain, **kwargs)

    # -- auth + transport hooks (over common.transport.RawHttpClient) ----- #

    def _fetch_token(self):
        """B4 — the export reader resolves its bearer via a **zero-arg**
        ``token_provider`` (no inline creds, no ``urlopen`` threaded), unlike the
        credentialed clients; the base :meth:`_bearer` caches the result."""
        return self._token_provider()

    def _before_send(self):
        """Throttle placement — the export reader paces **inside** the send (every
        export/poll/download call routes a :class:`RateLimiter`), acquiring here
        after the request is built and just before ``urlopen`` (its historical
        build → acquire → send order)."""
        self._limiter.acquire()

    def _on_success(self, raw: bytes) -> bytes:
        """B3 — the export reader returns the response **bytes** verbatim (the xlsx
        download / poll body); it never ``json.loads`` at the transport layer (the
        JSON callers parse in :meth:`_request_json`)."""
        return raw

    def _on_http_error(self, e, method, path):
        """B1 — the export reader **RAISES** on any ``HTTPError`` (returning raw
        bytes, it has no dict to hand a code-typing wrapper): a Lark-JSON error body
        is typed via :func:`raise_for_lark_code`, a non-JSON body raises a bare typed
        :class:`LarkAPIError`. This is the deliberate opposite of the three JSON
        clients' return-a-dict posture."""
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            raise LarkAPIError(f"{method} {path} failed: HTTP {e.code}")
        raise_for_lark_code(payload, context=f"export {method} {path}",
                            credential_env=self._credential_env)
        raise LarkAPIError(f"{method} {path} failed: HTTP {e.code}")

    def _request_bytes(self, method, path, *, body=None, params=None) -> bytes:
        """One throttled raw HTTP call → the response body bytes, over the shared
        core. The throttle (:meth:`_before_send`), raw-bytes return (B3,
        :meth:`_on_success`) and raise-on-``HTTPError`` posture (B1,
        :meth:`_on_http_error`) are the export reader's hook overrides above; a
        genuine transport (``URLError``) failure raises the typed
        :class:`LarkAPIError` from the base skeleton."""
        return self._send(method, path, body=body, params=params)

    def _request_json(self, method, path, *, body=None, params=None) -> dict:
        """A throttled call whose response is Lark JSON — typed on a non-zero code."""
        raw = self._request_bytes(method, path, body=body, params=params)
        resp = json.loads(raw)
        return raise_for_lark_code(resp, context=f"export {method} {path}",
                                   credential_env=self._credential_env)

    # -- export lifecycle (AC1) ------------------------------------------ #

    def create_export_task(self, spreadsheet_token) -> str:
        """``POST /drive/v1/export_tasks`` → the export ``ticket``."""
        resp = self._request_json(
            "POST",
            EXPORT_TASKS_PATH,
            body={"file_extension": "xlsx", "token": spreadsheet_token, "type": "sheet"},
        )
        ticket = (resp.get("data") or {}).get("ticket")
        if not ticket:
            raise LarkAPIError(f"export create returned no ticket: {resp!r}")
        return ticket

    def poll_export_task(self, ticket, spreadsheet_token) -> dict:
        """Poll ``GET /drive/v1/export_tasks/{ticket}?token=`` until ``job_status == 0``.

        Returns the completed ``result`` dict (carrying ``file_token``). Sleeps
        ``poll_interval`` (≥0.5s) between polls and is **bounded** by ``max_polls`` —
        an always-pending job raises :class:`LarkAPIError` rather than looping forever.
        A non-zero, non-pending ``job_status`` is an export failure → typed error."""
        for _attempt in range(self._max_polls):
            resp = self._request_json(
                "GET",
                f"{EXPORT_TASKS_PATH}/{ticket}",
                params={"token": spreadsheet_token},
            )
            result = (resp.get("data") or {}).get("result") or {}
            status = result.get("job_status")
            if status in (0, "0"):
                return result
            if _int(status) not in EXPORT_PENDING_STATUSES:
                raise LarkAPIError(
                    f"export task {ticket} failed: job_status={status}, "
                    f"msg={result.get('job_error_msg')!r}"
                )
            self._sleep(self._poll_interval)
        raise LarkAPIError(
            f"export task {ticket} did not reach job_status=0 within "
            f"{self._max_polls} polls"
        )

    def download_export(self, file_token) -> bytes:
        """``GET /drive/v1/export_tasks/file/{file_token}/download`` → the xlsx bytes."""
        return self._request_bytes(
            "GET", f"{EXPORT_TASKS_PATH}/file/{file_token}/download"
        )

    def export_xlsx(self, spreadsheet_token) -> bytes:
        """The full lifecycle: create → poll → download → the raw xlsx bytes."""
        ticket = self.create_export_task(spreadsheet_token)
        result = self.poll_export_task(ticket, spreadsheet_token)
        file_token = result.get("file_token")
        if not file_token:
            raise LarkAPIError(
                f"export task {ticket} completed but returned no file_token: {result!r}"
            )
        return self.download_export(file_token)

    def read_workbook(self, spreadsheet_token) -> ParsedWorkbook:
        """Export the spreadsheet and parse it → :class:`ParsedWorkbook` (the read-side
        entry point: :meth:`export_xlsx` + :func:`parse_xlsx`)."""
        return parse_xlsx(self.export_xlsx(spreadsheet_token))
