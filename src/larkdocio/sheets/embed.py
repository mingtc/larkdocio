"""larkdocio.sheets.embed — the opt-in embedded-sheet deep-read bridge (LD-105).

The docx reader surfaces an **embedded sheet** (block type 30) as a compound token
``<spreadsheet_token>_<sheet_id>`` (see :func:`larkdocio.blocks.embedded.handle_sheet`).
This module is the **glue** the LD-100 opener spike (Q6) proved: split that token on
its **last** ``_`` and feed the two halves through the SAME standalone Sheets path
the reader already ships (S1 client → S2 trim → S3 render → S4 table assembly), but
render **only the referenced ``sheet_id`` tab** (D3) — the docx author embedded one
specific sheet, so deep-read surfaces exactly that one, never its siblings.

Two disciplines, both load-bearing:

* **Opt-in only (D2).** This bridge runs solely when a consumer opts in
  (``Parser(deep_read_sheets=True, sheets_client=...)``); the default reader path
  never imports or calls it, so default docx Markdown is byte-identical (D8) and
  makes zero Sheets API calls.
* **Graceful — never raises (D2 rationale, AC4).** A malformed/absent token, an
  unresolvable ``sheet_id``, a missing scope, or any API error returns ``None`` so
  the handler falls back to the traceable placeholder. **A docx download must NEVER
  fail because an embedded sheet could not be deep-read.**

The bridge does not fetch spreadsheet metadata (title) — an embedded sheet carries
no standalone title (spike Q6), so :func:`~larkdocio.sheets.table.render_tab`
synthesizes the tab heading from the ``sheet_id``. Only two reads happen: one
tab-query (for the tab's grid extent + ``merges``) and one bounded values read of
the referenced tab (via :meth:`~larkdocio.sheets.client.SheetsReadClient.read_used_range`).
"""
from typing import Optional, Tuple

from larkdocio.sheets.table import FidelityUnavailable, render_tab

#: Why the fidelity leg came back empty — rendered into the fill disclosure's
#: "could not be read" note so an unread style layer never looks like an absent one.
_EXPORT_FAILED = "the xlsx export could not be read"
_NO_MATCHING_WORKSHEET = "the export carries no worksheet matching this tab"


def split_compound_token(compound_token) -> Optional[Tuple[str, str]]:
    """Split a docx type-30 compound token into ``(spreadsheet_token, sheet_id)``.

    The token is ``<spreadsheet_token>_<sheet_id>`` and is split on its **last**
    ``_`` (spike Q6): the ``spreadsheet_token`` may itself contain ``_``, so only
    the final underscore separates the referenced ``sheet_id``. Returns ``None`` for
    a malformed token — no ``_`` at all, or an empty half — so the caller degrades
    to the placeholder rather than issuing a doomed fetch. Never raises.

    **This is NOT the sheets-URL parse** and must not be merged with it. Its input is a
    compound token a docx type-30 block carries, never a url; the url parse is
    :func:`larkdocio.common.url.validate_download_url`, which recognises a ``/sheets/`` url
    and hands back its api domain, its type and its token. The two read as "the token
    parsers" from a distance and solve unrelated problems — consolidating them would break
    both, exactly as it would for a pair of near-identically named text helpers elsewhere in
    this library.
    """
    if not compound_token or "_" not in compound_token:
        return None
    spreadsheet_token, sheet_id = compound_token.rsplit("_", 1)
    if not spreadsheet_token or not sheet_id:
        return None
    return spreadsheet_token, sheet_id


def deep_read_embedded_sheet(
    client,
    compound_token,
    *,
    renderer=None,
    mention_names=None,
    fidelity_read=False,
    export_reader=None,
) -> Optional[str]:
    """Deep-read the ONE referenced tab of an embedded-sheet compound token.

    Splits ``compound_token`` (:func:`split_compound_token`), tab-queries the
    underlying spreadsheet, locates **only** the referenced ``sheet_id`` tab,
    reads its used range, and renders it to a titled GFM table
    (:func:`~larkdocio.sheets.table.render_tab`). Returns that table's Markdown
    **with a single trailing newline** (block-separation parity with the type-30
    placeholder), or ``None`` to degrade to the placeholder.

    ``renderer`` threads the docx reader's configured
    :class:`~larkdocio.model.MarkdownRenderer` (so a styled cell honors
    ``use_html_tags`` exactly as the surrounding docx does); ``mention_names`` is the
    optional ``{user_id: display_name}`` resolution map (absent ⇒ the graceful @mention
    degrade — a read never fails on an unresolvable mention).

    **Opt-in whole-cell (format-level) style fidelity.** When ``fidelity_read`` is set
    **and** an ``export_reader`` (a
    :class:`~larkdocio.sheets.export_reader.SheetsExportReader`, built from **READ**
    creds) is supplied, the referenced tab's **whole-cell (format-level)** bold/italic —
    the emphasis set on the CELL, which the values API does not carry — is read from the
    xlsx export and rendered as MD emphasis. **Run-level** emphasis (bold/italic on a text
    run inside a cell) travels in the values API's own ``segmentStyle`` and is already
    rendered without this leg, so an embedded sheet styled that way renders identically
    either way — expected, not a failed read. With the
    flag off (the default) or no reader, **no export is issued** and the render is the
    values-only deep read (byte-identical to the default). An export failure degrades to
    values-only — it never fails the deep-read (the export is fidelity gravy, not the
    table).

    **Never raises**: a malformed token, an unresolvable ``sheet_id``, a
    missing scope, or any API error is caught and returned as ``None``.
    """
    try:
        parts = split_compound_token(compound_token)
        if parts is None:
            return None
        spreadsheet_token, sheet_id = parts

        tabs = client.query_sheets(spreadsheet_token)
        tab = next((t for t in tabs if t.sheet_id == sheet_id), None)
        if tab is None:
            return None  # the embedded sheet_id is not a tab of this spreadsheet

        used_range = client.read_used_range(spreadsheet_token, tab)
        fidelity = None
        if fidelity_read and export_reader is not None:
            fidelity = _read_cell_fidelity(export_reader, spreadsheet_token, tab)
        table_md = render_tab(
            tab, used_range, mention_names=mention_names, renderer=renderer,
            fidelity=fidelity,
        )
        # Trailing newline so the page serializer's child separator yields a blank
        # line after the table — parity with the placeholder marker's own '\n'.
        return table_md + "\n"
    except Exception:
        # ANY deep-read failure degrades to the placeholder (D2 rationale): a docx
        # download must never fail because an embedded sheet could not be read.
        return None


def _read_cell_fidelity(export_reader, spreadsheet_token, tab):
    """Export + parse the workbook and locate the referenced tab's
    :class:`~larkdocio.sheets.export_reader.ExportedSheet` (the cell-emphasis source).

    Matches the export's worksheet by the tab **title** (the xlsx sheet name), falling
    back to the sole sheet when the workbook carries exactly one. **Graceful:** any
    export/parse failure — or a name mismatch — degrades to a values-only render; the
    fidelity read never fails the whole deep-read (D5a).

    What it returns on that degrade is a :class:`~larkdocio.sheets.table.FidelityUnavailable`
    sentinel, **not** ``None``. It adds no emphasis either way, so the table is the same
    values-only table it has always been; the difference is that the render now **says** the
    style layer could not be read, instead of leaving an unread fill layer looking exactly
    like an absent one."""
    try:
        workbook = export_reader.read_workbook(spreadsheet_token)
    except Exception:
        return FidelityUnavailable(_EXPORT_FAILED)
    if workbook is None:
        return FidelityUnavailable(_EXPORT_FAILED)
    exported = workbook.sheet(tab.title)
    if exported is None and len(workbook.sheets) == 1:
        exported = workbook.first_sheet
    if exported is None:
        return FidelityUnavailable(_NO_MATCHING_WORKSHEET)
    return exported
