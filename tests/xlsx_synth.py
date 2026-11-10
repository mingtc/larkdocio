"""Deterministic, stdlib-only xlsx synthesizer for the LD-114 export-reader tests.

The LD-114 export reader parses a real Lark xlsx export with ``zipfile`` +
``xml.etree`` only (D2 — no ``openpyxl``/``lxml``/new dep). To exercise it offline
we need sample workbooks, but the kit forbids committing binary blobs, so this
helper **synthesizes minimal, valid xlsx bytes in-test from committed text** — the
XML parts are built from readable string templates and zipped deterministically
(``zipfile``, fixed member order, no timestamps that vary the bytes). No
``openpyxl``: the fixtures must not smuggle in the very dependency the reader
refuses.

The parts modelled are exactly the ones the reader reads (LD-107 Q2 /
``captures/02b-export-fidelity.json``): ``xl/styles.xml`` (numFmts / fonts with
``<b/>``/``<i/>`` / fills), ``xl/worksheets/sheetN.xml`` (per-cell ``s=`` style
index, ``<v>``/inline ``<is>``, ``<mergeCell>`` refs), ``xl/sharedStrings.xml``,
and the ``xl/workbook.xml`` (+ rels) sheet map so a multi-sheet workbook resolves
each sheet's name → the right ``sheetN.xml``.

Everything is a plain function returning ``str`` (an XML part) or ``bytes`` (the
zipped workbook), so a test composes exactly the shape it needs and can also build
deliberately-malformed workbooks (omit ``styles.xml``, a dangling ``s=`` index, a
non-zip blob) for the robustness cases.
"""
import io
import re
import zipfile

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

_XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def zip_xlsx(parts: dict) -> bytes:
    """Zip ``{arcname: str|bytes}`` into deterministic xlsx bytes (member order =
    dict order; str parts are UTF-8 encoded). The primitive the malformed-workbook
    tests reach for directly (omit a part, inject a bad member)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in parts.items():
            if isinstance(content, str):
                content = content.encode("utf-8")
            z.writestr(name, content)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Individual XML parts                                                          #
# --------------------------------------------------------------------------- #

def _font_xml(f: dict) -> str:
    inner = ""
    if f.get("bold"):
        inner += "<b val=\"true\"/>"
    if f.get("italic"):
        inner += "<i val=\"true\"/>"
    inner += '<sz val="12"/><name val="Calibri"/>'
    return f"<font>{inner}</font>"


def _fill_xml(f: dict) -> str:
    pattern = f.get("pattern", "none")
    fg = f.get("fg_rgb")
    fg_x = f'<fgColor rgb="{fg}"/>' if fg else "<fgColor/>"
    return f'<fill><patternFill patternType="{pattern}">{fg_x}<bgColor/></patternFill></fill>'


def _xf_xml(x: dict) -> str:
    return (
        f'<xf numFmtId="{x.get("numFmtId", 0)}" fontId="{x.get("fontId", 0)}" '
        f'fillId="{x.get("fillId", 0)}" borderId="0" xfId="0"/>'
    )


def styles_xml(*, num_fmts=(), fonts=None, fills=None, cell_xfs=None) -> str:
    """Build an ``xl/styles.xml``.

    ``num_fmts``  — iterable of ``(numFmtId:int, formatCode:str)`` (custom formats,
                    Lark writes id ≥ 164).
    ``fonts``     — list of ``{"bold":bool, "italic":bool}`` (index 0 = default).
    ``fills``     — list of ``{"pattern":str, "fg_rgb":str|None}`` (0/1 reserved in
                    real xlsx: ``none`` + ``gray125``).
    ``cell_xfs``  — list of ``{"numFmtId","fontId","fillId"}`` — the ``s=`` index table.
    """
    if fonts is None:
        fonts = [{}]
    if fills is None:
        fills = [{"pattern": "none"}, {"pattern": "gray125"}]
    if cell_xfs is None:
        cell_xfs = [{"numFmtId": 0, "fontId": 0, "fillId": 0}]
    nf_inner = "".join(
        f'<numFmt numFmtId="{i}" formatCode="{c}"/>' for i, c in num_fmts
    )
    nf_block = f'<numFmts count="{len(list(num_fmts))}">{nf_inner}</numFmts>' if nf_inner else ""
    return (
        f"{_XML_DECL}<styleSheet xmlns=\"{MAIN_NS}\">"
        f"{nf_block}"
        f'<fonts count="{len(fonts)}">{"".join(_font_xml(f) for f in fonts)}</fonts>'
        f'<fills count="{len(fills)}">{"".join(_fill_xml(f) for f in fills)}</fills>'
        f'<borders count="1"><border/></borders>'
        f'<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        f'<cellXfs count="{len(cell_xfs)}">{"".join(_xf_xml(x) for x in cell_xfs)}</cellXfs>'
        f"</styleSheet>"
    )


def _run_xml(text: str, style=None) -> str:
    """One rich-text run: ``<r><rPr><b/><i/></rPr><t>text</t></r>``.

    Run emphasis is a property of the RUN, never of the cell's ``s=`` format — which is
    the whole point of having this shape available offline.
    """
    style = style or {}
    props = ""
    if style.get("bold"):
        props += "<b/>"
    if style.get("italic"):
        props += "<i/>"
    pr = f"<rPr>{props}</rPr>" if props else ""
    return f"<r>{pr}<t>{text}</t></r>"


_CELL_ROW_RE = re.compile(r"[A-Z]+(\d+)")


def _sheet_format_pr_xml(default_row_height=None, default_col_width=None) -> str:
    """``<sheetFormatPr defaultColWidth="13" defaultRowHeight="20">`` — the element the
    LD-185 dimension read compares a row/column's own size against. Attribute names and the
    ``13``/``20`` values are the live export's, captured verbatim in
    ``tests/captures/sheets-dimension-probe/captures/03-raw-xlsx-dimension-XML.json``."""
    if default_row_height is None and default_col_width is None:
        return ""
    attrs = ""
    if default_col_width is not None:
        attrs += f' defaultColWidth="{default_col_width}"'
    if default_row_height is not None:
        attrs += f' defaultRowHeight="{default_row_height}"'
    return f"<sheetFormatPr{attrs}></sheetFormatPr>"


def _cols_xml(cols=()) -> str:
    """``<cols><col collapsed="false" customWidth="true" hidden="false" max="2" min="2"
    style="0" width="25">`` — the LD-185 column-dimension shape, in the live export's own
    attribute order (capture ``03``). A list may deliberately carry the **same** column twice
    (once ``hidden="false"``, once ``hidden="true"``), because the real export does: that is
    the duplication the reader's last-wins rule exists for."""
    if not cols:
        return ""
    parts = []
    for c in cols:
        attrs = f' collapsed="{c.get("collapsed", "false")}"'
        if c.get("customWidth") is not None:
            attrs += f' customWidth="{c["customWidth"]}"'
        if c.get("hidden") is not None:
            attrs += f' hidden="{c["hidden"]}"'
        attrs += f' max="{c.get("max", c["min"])}" min="{c["min"]}" style="0"'
        if c.get("width") is not None:
            attrs += f' width="{c["width"]}"'
        parts.append(f"<col{attrs}></col>")
    return f'<cols>{"".join(parts)}</cols>'


def _row_attrs(rn: int, rows) -> str:
    """The LD-185 row-dimension attributes on a ``<row>`` — ``customHeight`` / ``hidden`` /
    ``ht``, in the live export's own order (``<row customHeight="true" hidden="true" ht="20"
    r="3">``, capture ``03``)."""
    spec = (rows or {}).get(rn) or {}
    attrs = ""
    if spec.get("customHeight") is not None:
        attrs += f' customHeight="{spec["customHeight"]}"'
    if spec.get("hidden") is not None:
        attrs += f' hidden="{spec["hidden"]}"'
    if spec.get("ht") is not None:
        attrs += f' ht="{spec["ht"]}"'
    return attrs


def worksheet_xml(cells, merges=(), *, rows=None, cols=(), default_row_height=None,
                  default_col_width=None) -> str:
    """Build an ``xl/worksheets/sheetN.xml`` from ``cells`` + optional merge refs.

    ``cells`` is a list of ``(ref, attrs)``; ``attrs`` keys: ``s`` (style index),
    ``t`` (cell type — ``s`` shared / ``inlineStr`` / ``str`` / ``b`` / omitted for
    numeric), ``v`` (the ``<v>`` payload), ``inline`` (the inline-string text when
    ``t == "inlineStr"``), ``rich`` (an inline string built from **runs** — see below).
    ``merges`` is a list of A1 ranges (``"A1:C1"``).

    ``rich`` is a list of ``(text, {"bold":bool, "italic":bool})`` runs emitted as
    ``<is><r><rPr><b/></rPr><t>…</t></r>…</is>``. It is the shape that puts emphasis
    **inside the cell's text** rather than in the cell's **format**, which is the
    distinction the fidelity-scope tests turn on: run emphasis lives in the runs and the
    cell's ``s=`` format stays un-styled."""
    by_row = {}
    for ref, attrs in cells:
        rn = int(_CELL_ROW_RE.match(ref).group(1))
        by_row.setdefault(rn, []).append((ref, attrs))
    for rn in (rows or {}):
        by_row.setdefault(rn, [])
    row_parts = []
    for rn in sorted(by_row):
        row_parts.append(f'<row{_row_attrs(rn, rows)} r="{rn}">')
        for ref, a in by_row[rn]:
            attr_s = f' r="{ref}"'
            if "s" in a:
                attr_s += f' s="{a["s"]}"'
            if "t" in a:
                attr_s += f' t="{a["t"]}"'
            if a.get("t") == "inlineStr" and a.get("rich"):
                runs = "".join(_run_xml(text, style) for text, style in a["rich"])
                row_parts.append(f'<c{attr_s}><is>{runs}</is></c>')
            elif a.get("t") == "inlineStr":
                row_parts.append(f'<c{attr_s}><is><t>{a.get("inline", "")}</t></is></c>')
            elif "v" in a:
                row_parts.append(f'<c{attr_s}><v>{a["v"]}</v></c>')
            else:
                row_parts.append(f'<c{attr_s}/>')
        row_parts.append("</row>")
    merge_block = ""
    if merges:
        m = "".join(f'<mergeCell ref="{r}"/>' for r in merges)
        merge_block = f'<mergeCells count="{len(merges)}">{m}</mergeCells>'
    return (
        f"{_XML_DECL}<worksheet xmlns=\"{MAIN_NS}\">"
        f"{_sheet_format_pr_xml(default_row_height, default_col_width)}"
        f"{_cols_xml(cols)}"
        f"<sheetData>{''.join(row_parts)}</sheetData>{merge_block}</worksheet>"
    )


def shared_strings_xml(strings) -> str:
    sis = "".join(f"<si><t>{s}</t></si>" for s in strings)
    return (
        f'{_XML_DECL}<sst xmlns="{MAIN_NS}" count="{len(strings)}" '
        f'uniqueCount="{len(strings)}">{sis}</sst>'
    )


def workbook_xml(sheet_names) -> str:
    sheets = "".join(
        f'<sheet name="{n}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
        for i, n in enumerate(sheet_names)
    )
    return (
        f'{_XML_DECL}<workbook xmlns="{MAIN_NS}" xmlns:r="{REL_NS}">'
        f"<sheets>{sheets}</sheets></workbook>"
    )


def workbook_rels_xml(sheet_count) -> str:
    rels = "".join(
        f'<Relationship Id="rId{i + 1}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{i + 1}.xml"/>'
        for i in range(sheet_count)
    )
    return f'{_XML_DECL}<Relationships xmlns="{PKG_REL_NS}">{rels}</Relationships>'


def _content_types_xml() -> str:
    # Minimal; the reader discovers parts by path and ignores this, but real
    # workbooks carry it, so include a valid trivial one.
    return (
        f'{_XML_DECL}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        f'<Default Extension="xml" ContentType="application/xml"/>'
        f'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        f"</Types>"
    )


# --------------------------------------------------------------------------- #
# High-level builder                                                            #
# --------------------------------------------------------------------------- #

def build_workbook(sheets, *, shared_strings=None, styles=None,
                   include_styles=True, include_workbook=True) -> bytes:
    """Assemble a full, valid xlsx from ``sheets`` (a list of
    ``{"name", "cells", "merges"}`` dicts) plus optional shared strings + styles.

    ``styles`` is a raw ``xl/styles.xml`` string (build it with :func:`styles_xml`);
    ``None`` supplies a trivial default. ``include_styles=False`` omits
    ``xl/styles.xml`` entirely (the missing-styles robustness case).
    ``include_workbook=False`` omits ``xl/workbook.xml`` + rels (the reader then
    falls back to discovering ``sheetN.xml`` by order)."""
    parts = {"[Content_Types].xml": _content_types_xml()}
    if include_workbook:
        parts["xl/workbook.xml"] = workbook_xml([s["name"] for s in sheets])
        parts["xl/_rels/workbook.xml.rels"] = workbook_rels_xml(len(sheets))
    for i, s in enumerate(sheets):
        parts[f"xl/worksheets/sheet{i + 1}.xml"] = worksheet_xml(
            s.get("cells", []), s.get("merges", ()),
            rows=s.get("rows"), cols=s.get("cols", ()),
            default_row_height=s.get("default_row_height"),
            default_col_width=s.get("default_col_width"),
        )
    if include_styles:
        parts["xl/styles.xml"] = styles if styles is not None else styles_xml()
    if shared_strings is not None:
        parts["xl/sharedStrings.xml"] = shared_strings_xml(shared_strings)
    return zip_xlsx(parts)


# --------------------------------------------------------------------------- #
# The reference fidelity workbook (reproduces captures/02b-export-fidelity.json) #
# --------------------------------------------------------------------------- #

def fidelity_workbook() -> bytes:
    """The LD-107 Q2 fidelity sample as valid xlsx bytes: one sheet, cell A1
    carries value ``0.1234`` with **bold + fill ``FFFFFF00`` + numFmt ``0.00%``**
    (numFmtId 164 custom), exactly as ``captures/02b-export-fidelity.json`` recorded
    it (``<c r="A1" s="1"><v>0.1234</v></c>`` + that ``xl/styles.xml``)."""
    styles = styles_xml(
        num_fmts=[(164, "0.00%")],
        fonts=[{}, {"bold": True}],
        fills=[{"pattern": "none"}, {"pattern": "gray125"}, {"pattern": "solid", "fg_rgb": "FFFFFF00"}],
        cell_xfs=[
            {"numFmtId": 0, "fontId": 0, "fillId": 0},
            {"numFmtId": 164, "fontId": 1, "fillId": 2},
        ],
    )
    return build_workbook(
        [{"name": "Sheet1", "cells": [("A1", {"s": 1, "v": "0.1234"})]}],
        styles=styles,
    )
