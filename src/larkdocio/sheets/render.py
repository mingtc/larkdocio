"""larkdocio.sheets.render — value→Markdown cell rendering (LD-103).

Renders one Sheets cell — as read from the client's **FormattedValue** values pass
(D1) — to Markdown, covering the LD-100 spike's full type matrix. The mapping is
built against the **native column D + hand-adds (B20–B24)** (spike Q1) — the
fidelity authority; the pasted column B is a drift reference.

Reuse, don't fork (D6). The docx reader's inline-Markdown serializer
(:class:`larkdocio.model.MarkdownRenderer`) composes bold/italic/strike/underline
and links, so a styled sheet run and a styled docx run emit **byte-identical**
Markdown — and **color is dropped** for free (the serializer captures-then-ignores
color; L2). @mention rendering mirrors the docx ``resolve_mentions`` graceful
degrade: an external ``mention_names`` map wins when it resolves an id, otherwise
we fall back to the payload's own display name / text / id — a read must **never**
fail on an unresolvable mention (D6; the map is empty until the console
availability-range fix lands).

The wire shapes (spike Q1 + a 2026-07-26 rev-36 re-capture):

* ``None`` → ``""`` (an empty / merge-covered / unselected-dropdown cell).
* ``bool`` → ``☑`` / ``☐`` — a Lark boolean cell displays as a checkbox; a
  values-only read cannot distinguish a checkbox from a plain boolean (both are
  JSON ``bool``), so both render as the box glyph. (The spike's "checkbox = int
  0/1" was the *placeholder* integer, still un-replaced at rev 36; rendering plain
  ints as boxes would corrupt genuine integer cells, so the glyph keys off
  ``bool``.)
* ``int`` / ``float`` → its plain ``str`` (``42``, ``3.14159``, ``-273.15``).
* ``str`` → the display string, routed through the shared serializer for
  bare-URL linkify parity (``"$1,234.56"``, ``"12.34%"``, ``"7/26/2026"``, a
  single/​multi dropdown's selected option text).
* ``list`` → a rich cell's segment array: styled runs (``{type:"text",
  segmentStyle}``) → MD inline; a hyperlink (``{type:"url",link,text}``) →
  ``[text](link)``; an embedded mention → its resolved/degraded text.
* ``dict`` → a single rich value: a ``{type:"mention"}`` (``mentionType`` 0 =
  @user → ``@name``; 22 = doc-link → ``[text](link)``), a ``{type:"url"}``, a
  ``{type:"multipleValue"}`` multi-select (its options joined by ``", "``), or an
  ``{type:"embed-image"}`` **in-cell image** → ``![{text}]({fileToken})``, the
  **docx image dialect** (LD-446 — see :func:`_embed_image_to_str`).

**A clean read is NOT evidence that a tab holds no pictures (LD-446 / measured LD-435).**
There are two kinds of picture on a Sheet and this module can see only one of them. An
**in-cell** image *is* a cell value and renders above. A **FLOAT** image — a picture
anchored *over* a range — is **not a cell value at all**, so a values read cannot see it
**in any form, under any option**; it lives behind the tab's own
``float_images/query`` route, which **no shipped READ op in this library calls** — the
only shipped caller is the float-image WRITE route's own verdict read
(:meth:`larkdocio.sheets.write_client.SheetsWriteClient.query_float_images`, LD-448), so the
read surface's gap is unchanged. That is an absence of a leg, not a bug in a leg — but it means
an empty-looking tab may still carry pictures a viewer sees. (Measured on one tenant, one
day, one 88-byte PNG, one workbook, ``tenant_access_token``.)

Scope (LD-103): renders a **single cell**. Table assembly + the merge join (S4)
and the pipe/newline normalisation that keeps a Markdown table valid are LD-104 —
so a newline in a cell is preserved here, not turned into ``<br>``.
"""
from larkdocio.common import unescape_url
from larkdocio.model import (
    ImageNode,
    MarkdownRenderer,
    MentionDoc,
    StyledText,
    Text,
)

#: The default (Markdown-marker) serializer — stateless/config-only, so one shared
#: instance is reused across cells. S4/S5 may pass their own configured renderer
#: (e.g. ``use_html_tags``) via ``render_cell(..., renderer=...)``.
_DEFAULT_RENDERER = MarkdownRenderer()

#: Checkbox glyphs (AC5). Checked = U+2611 BALLOT BOX WITH CHECK, unchecked =
#: U+2610 BALLOT BOX.
_CHECKED = "☑"
_UNCHECKED = "☐"

#: Join for a multi-select dropdown's selected options (AC5; LD-117 D5b — the ONE
#: separator both wire forms unify to).
_MULTI_JOIN = ", "


def _normalize_multiselect_string(s: str) -> str:
    """Normalize a multi-select cell's comma-joined READ form to an ordered
    ``", "``-joined label set (``"Red,Green"`` → ``"Red, Green"``; sheet order
    preserved), unifying it with the ``multipleValue`` write-object form (LD-117 D5b).

    A multi-select reads back as a bare comma-joined string under **every** render
    mode (write Q3 / ``03b-dropdown.json`` — ``"Red,Green"``), indistinguishable at
    the value layer from any other comma-bearing display string, **including a
    currency / thousands-grouped / decimal number** (``"$1,234.56"``, ``"1,234"``,
    ``"3,14"``). The distinguishing rule: a comma flanked by a digit on **both**
    sides marks a numeric grouping, so such a string is a formatted number — **not**
    a label set — and is returned byte-identical (commas are forbidden **inside**
    option labels on the write side, so a genuine label set never carries a
    digit-flanked comma). Only a non-numeric comma-joined string is split on ``,``
    (each label stripped) and re-joined with ``", "``.
    """
    if "," not in s:
        return s
    for i, ch in enumerate(s):
        if ch == "," and 0 < i < len(s) - 1 and s[i - 1].isdigit() and s[i + 1].isdigit():
            return s  # numeric grouping / decimal — not a multi-select label set
    return _MULTI_JOIN.join(part.strip() for part in s.split(","))


def render_cell(value, *, mention_names=None, renderer=None) -> str:
    """Render one Sheets cell value to Markdown.

    :param value: the raw cell as the client's ``FormattedValue`` read returned it
        — a scalar, a display string, ``None``, a rich segment ``list``, or a rich
        ``dict`` (mention / url / multi-select).
    :param mention_names: optional ``{user_id: display_name}`` resolution map
        (parity with the docx ``resolve_mentions`` API path). Empty/absent → the
        graceful-degrade path (payload name → text → id); a read never fails on an
        unresolvable mention.
    :param renderer: optional shared :class:`~larkdocio.model.MarkdownRenderer`
        (threads config like ``use_html_tags`` from the table/embed layers); defaults to the
        module's Markdown-marker instance.
    :returns: the cell's Markdown (``""`` for a ``None`` / empty cell). Never
        raises on cell content.
    """
    r = renderer or _DEFAULT_RENDERER
    if value is None:
        return ""
    # bool BEFORE int/float — ``isinstance(True, int)`` is True in Python.
    if isinstance(value, bool):
        return _CHECKED if value else _UNCHECKED
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # LD-117 D5b: a multi-select reads back as a comma-joined string; normalize
        # it to an ordered ", "-joined set (currency/number groupings preserved by
        # the digit-flank guard), then route through the shared serializer for
        # bare-URL linkify parity.
        return r.render_inline([Text(_normalize_multiselect_string(value))])
    if isinstance(value, list):
        return "".join(_segment_to_str(seg, mention_names, r) for seg in value)
    if isinstance(value, dict):
        # A single rich value (mention / url / multi-select / styled text) is one
        # segment — the same dispatch a segment inside a rich list gets.
        return _segment_to_str(value, mention_names, r)
    # Belt-and-braces: an unexpected type degrades to str, never raises.
    return str(value)


def apply_cell_emphasis(text, *, bold=False, italic=False, renderer=None) -> str:
    """Wrap an already-rendered cell's text in **whole-cell (format-level)** MD emphasis.

    **Two different kinds of bold, and this is only the second one.** Emphasis on a text
    **run** *inside* a cell is carried by the values API's own ``segmentStyle`` and is
    already rendered by :func:`render_cell` — nothing here is involved. Emphasis applied to
    the **cell itself** (its format) is what the values API does not carry: it lives only in
    the xlsx export, so it is applied **only** on the opt-in fidelity-read path, from the
    export-derived ``bold`` / ``italic`` the caller supplies for the cell.

    The consequence worth stating, because it looks like a malfunction and is not: on a
    sheet whose emphasis is **run-level**, this adds **nothing** — the emphasis was already
    there — so a fidelity render that is byte-identical to the values-only render is the
    **correct** outcome, not a missed read. And the wrap only ever **adds**: it is layered
    **over** the values render, never instead of it, so run-level emphasis can never be
    dropped by turning the leg on.

    When neither ``bold`` nor ``italic`` is set the ``text`` is returned
    **byte-identical** (the flag-OFF invariant at cell scope). Otherwise the emphasis is
    composed by the **shared** serializer
    (:meth:`~larkdocio.model.MarkdownRenderer.render_inline`, bold-outer order,
    ``use_html_tags`` honored) — a fork would drift from the docx styled-run output.

    ``text`` is **already-rendered** Markdown (the cell may itself carry inline
    markup — a hyperlink, a styled run, a ``", "``-joined multi-select set), so the
    wrap runs with ``linkify=False`` **and** ``verbatim=True``: it never
    re-linkifies and never re-escapes the inner markup (without the
    verbatim flag the plain-text escaper would backslash a nested run's own
    ``**`` markers), and an empty cell (no core) drops its markers.
    """
    if not (bold or italic):
        return text
    r = renderer or _DEFAULT_RENDERER
    return r.render_inline(
        [StyledText(content=text, bold=bold, italic=italic)],
        linkify=False,
        verbatim=True,
    )


def _segment_to_str(seg, mention_names, r: MarkdownRenderer) -> str:
    """Render one rich-cell segment (a bare string or a typed ``dict``)."""
    if seg is None:
        return ""
    if isinstance(seg, str):
        return r.render_inline([Text(seg)])
    if isinstance(seg, dict):
        seg_type = seg.get("type")
        if seg_type == "mention":
            return _mention_to_str(seg, mention_names, r)
        if seg_type == "url":
            return _url_to_str(seg, r)
        if seg_type == "multipleValue":
            return _multi_to_str(seg, mention_names, r)
        if seg_type == "text":
            return r.render_inline([_styled_from_segment(seg)])
        if seg_type == "embed-image":
            # BEFORE the catch-all: an in-cell image's `text` is "" (measured, LD-435
            # capture `203-`), so the fallback below rendered a picture as a blank cell.
            return _embed_image_to_str(seg, r)
        # Unknown segment type — surface its text, never raise.
        return r.render_inline([Text(str(seg.get("text", "") or ""))])
    # Any other scalar inside a segment list.
    return str(seg)


def _styled_from_segment(seg: dict) -> StyledText:
    """Map a ``{type:"text", segmentStyle}`` run to a :class:`StyledText`.

    Color / font-size are **dropped** (L2): the shared serializer already ignores
    ``text_color`` / ``background_color``, so they change no output.
    """
    style = seg.get("segmentStyle") or {}
    return StyledText(
        content=seg.get("text", "") or "",
        bold=bool(style.get("bold")),
        italic=bool(style.get("italic")),
        strikethrough=bool(style.get("strikeThrough")),
        underline=bool(style.get("underline")),
    )


def _embed_image_to_str(seg: dict, r: MarkdownRenderer) -> str:
    """An **in-cell image** (``{type:"embed-image", fileToken, width, height, text, link}``)
    → the reader's **own** image dialect, ``![{text}]({fileToken})`` (LD-446).

    **Reuse, don't fork (D6) — and here that is the whole point.** The string is produced
    by the same :class:`~larkdocio.model.MarkdownRenderer` rendering a docx
    :class:`~larkdocio.model.ImageNode`, so a docx image and a sheet image read **alike**
    and a consumer's existing image handling works unchanged. A third, sheets-only
    spelling would be a defect, not a variation; a tokenless value therefore also inherits
    the docx ``[Image: missing token]`` visible marker rather than being dropped.

    **The one deviation, stated:** the docx block form ends in a newline, which a table
    cell cannot carry (the S4 assembly turns ``\\n`` into ``<br>`` and would emit a
    spurious break), so the trailing newline is stripped. Nothing else is adjusted — the
    token character set is alphanumeric and the alt text goes through the assembly's own
    pipe escape, so no sheets-specific escape is needed.

    **The link is not emitted.** The value's ``link`` is an internal-api host URL with no
    signature parameter and **unmeasured** resolvability; the **measured** retrieval path
    is the drive media download route ``drive/v1/medias/{fileToken}/download``. So the
    token is what ships,
    and this function fetches nothing — no endpoint is reached by a read.
    """
    token = seg.get("fileToken") or None
    caption = seg.get("text", "") or ""
    return r.render(ImageNode(token=token, caption=caption)).rstrip("\n")


def _url_to_str(seg: dict, r: MarkdownRenderer) -> str:
    """A hyperlink segment (``{type:"url", link, text}``) → ``[text](link)``."""
    text = seg.get("text") or ""
    link = seg.get("link")
    if not link:
        return r.render_inline([Text(text)])
    return r.render_inline([StyledText(content=text, link_url=unescape_url(link))])


def _mention_to_str(obj: dict, mention_names, r: MarkdownRenderer) -> str:
    """Render a ``{type:"mention"}`` cell with graceful degrade (D6).

    ``mentionType`` 22 = a doc-link → ``[text](link)`` (parity with the docx
    ``MentionDoc``). Otherwise a @user mention → the **resolved** display name
    (external map wins), degrading to the payload's own name → text → id. Never
    raises.
    """
    if obj.get("mentionType") == 22:
        text = obj.get("text") or obj.get("token") or ""
        link = obj.get("link")
        if link:
            return r.render_inline([MentionDoc(text, unescape_url(link))])
        return text
    # @user (mentionType 0 or unspecified). Handle BOTH id fields — the live
    # capture uses `userID`, the older committed capture used `token`.
    uid = obj.get("userID") or obj.get("token")
    name = None
    if mention_names and uid:
        name = mention_names.get(uid)
    name = name or obj.get("name") or obj.get("en_name")
    if name:
        return f"@{name}"
    text = obj.get("text")
    if text:
        return text  # already carries the leading "@"
    if uid:
        return f"@{uid}"
    return ""


def _multi_to_str(obj: dict, mention_names, r: MarkdownRenderer) -> str:
    """A multi-select ``{type:"multipleValue"}`` → its options joined by ``", "``.

    Defensive: the options list may carry bare strings or segment dicts. An
    absent/empty list degrades to the object's own ``text`` (or ``""``).
    """
    values = obj.get("values")
    if not isinstance(values, list):
        values = obj.get("value") if isinstance(obj.get("value"), list) else []
    parts = [_segment_to_str(v, mention_names, r) for v in values]
    parts = [p for p in parts if p != ""]
    if parts:
        return _MULTI_JOIN.join(parts)
    return obj.get("text") or ""
