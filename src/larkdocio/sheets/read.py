"""larkdocio.sheets.read — the whole-workbook walk's **front door** (LD-405).

Every other read surface in this library has a **URL-first one-call**: hand it the thing a
human copied out of their browser and get the read back. ``larkdocio.base`` has
:func:`~larkdocio.base.read.read_base` / :func:`~larkdocio.base.read.read_base_markdown`;
``larkdocio.drive`` has :func:`~larkdocio.drive.read.read_folder`. The **spreadsheet walk had
none** — its only entry point was the method
:meth:`~larkdocio.sheets.client.SheetsReadClient.read_spreadsheet`, so a caller had to know to
build the client themselves and to hand it a *token* rather than the URL they were holding.

So the natural thing — probing ``from larkdocio.sheets import walk`` — hit
a **module**, and led to a hand-built ``SpreadsheetRead(client, token)``. Both halves of that are fixed
— this module is the door, and :mod:`larkdocio.sheets.walk` now refuses wrong construction at
the construction site.

Two entry points, the ``read_base`` pairing exactly:

* :func:`read_spreadsheet` returns the **structured** :class:`~larkdocio.sheets.walk.SpreadsheetRead`
  — every enumerated tab, its outcome, and the values of the ones that read;
* :func:`read_spreadsheet_markdown` returns the **Markdown**, for the reading form.

**The URL is parsed by the shared validator, not by a second parser.**
:func:`~larkdocio.common.url.validate_download_url` is the one that LD-396 made
full-token-or-refuse and LD-397 made refuse **before any credential or packet**; both
properties are inherited here rather than re-implemented. **No new endpoint and no new scope**
— this composes the client's own reads and nothing else.
"""
import re
from typing import Optional, Tuple

from larkdocio.common.url import URL_TYPE_SURFACES, validate_download_url
from larkdocio.errors import LarkConfigError
from larkdocio.sheets.table import _DEFAULT_HEADING_LEVEL, render_spreadsheet
from larkdocio.sheets.walk import SpreadsheetRead

#: The character set a Lark token is drawn from — the same one the URL validator's own pattern
#: accepts, so "a bare token" means exactly "what a URL could have carried". Held identical to
#: :data:`larkdocio.base.read._TOKEN` deliberately: a bare token is accepted here **only
#: because ``read_base``'s own rule accepts one**, never on a third rule of this surface's own.
_TOKEN = re.compile(r"^[A-Za-z0-9]+$")

#: Which surface reads the types that are NOT a spreadsheet, so a wrong-verb refusal routes
#: the caller instead of merely refusing them (the ``read_folder`` precedent).
_NON_SHEETS_READERS = {
    "docx": "the document download (larkdocio.download / larkdocio.read)",
    "wiki": "the document download (larkdocio.download / larkdocio.read)",
    "docs": "the document download (larkdocio.download / larkdocio.read)",
    "base": "the Base surface (larkdocio.base.read_base)",
    "drive": "the Drive surface (larkdocio.drive.read_folder)",
}


def _non_sheets_refusal(url_type: str, raw: str) -> str:
    """The wrong-verb refusal, stated for free from the URL string alone (LD-397)."""
    reader = _NON_SHEETS_READERS.get(url_type, "another surface")
    return (
        f"that is a {url_type} url, not a SHEETS url: {raw!r}. This verb walks a "
        f"SPREADSHEET's tabs; that url is read by {reader}. The url validator recognised it "
        "and handed back its type and token, so nothing was asked of Lark and no credential "
        "was used."
    )


def resolve_spreadsheet(spreadsheet: str) -> Tuple[Optional[str], str]:
    """A spreadsheet URL **or** a bare ``spreadsheet_token`` → ``(api_domain_or_None, token)``.

    :func:`~larkdocio.base.read.resolve_base` one surface over, with ``sheets`` in place of
    ``base`` — same rule, same shapes, same refusals, so a caller who learned one form has
    learned both. A URL is parsed by the shared
    :func:`~larkdocio.common.url.validate_download_url` (a mangled token region raises its
    ``ValueError`` — full token or refuse); a recognised URL naming **another**
    surface is refused **by name** here rather than sent to Lark to fail vaguer. A bare token
    carries no domain, so ``None`` is returned and the caller's default stands.

    Every refusal this function can make is made from the **string alone** — before any
    credential is resolved and before any packet is sent.
    """
    if not isinstance(spreadsheet, str) or not spreadsheet.strip():
        raise LarkConfigError(
            "Cannot read a spreadsheet: pass a Sheets URL "
            "(https://<host>/sheets/<spreadsheet_token>) or a bare spreadsheet_token")
    candidate = spreadsheet.strip()
    if candidate.lower().startswith(("http://", "https://")):
        domain, url_type, token = validate_download_url(candidate)
        if url_type != URL_TYPE_SURFACES["sheets"]:
            raise LarkConfigError(_non_sheets_refusal(url_type, candidate))
        return domain, token
    if not _TOKEN.match(candidate):
        raise LarkConfigError(
            f"Not a spreadsheet_token: {candidate!r}. Pass a Sheets URL "
            "(https://<host>/sheets/<spreadsheet_token>) or the bare spreadsheet_token.")
    return None, candidate


def read_spreadsheet(
    spreadsheet: str,
    *,
    client=None,
    domain: str = "larksuite.com",
    tabs=None,
    value_render_option=None,
    date_time_render_option=None,
    user_id_type=None,
) -> SpreadsheetRead:
    """Read **every tab** of a workbook from its URL, and return the structured walk.

    ``spreadsheet`` is **either a Sheets URL or a bare ``spreadsheet_token``**
    (:func:`resolve_spreadsheet`); a URL also supplies the API domain, which then overrides
    ``domain``. ``client`` is injectable — the default is a
    :class:`~larkdocio.sheets.client.SheetsReadClient` built from the environment's READ
    credentials. This is the URL-first twin of :func:`~larkdocio.base.read.read_base`.

    **It composes, it does not re-decide.** The walk is
    :meth:`~larkdocio.sheets.client.SheetsReadClient.read_spreadsheet` unchanged — which tabs
    skip, what a skip discloses, the ``accounted()`` invariant, the all-skipped
    :class:`~larkdocio.errors.LarkSpreadsheetUnreadableError` and the throttle/denial boundary
    are that method's contract and are not touched here. ``tabs``, ``value_render_option``,
    ``date_time_render_option`` and ``user_id_type`` are passed **straight through, unchanged
    in name and meaning** — a read flag is one grammar across every read verb.

    What comes back is a :class:`~larkdocio.sheets.walk.SpreadsheetRead`: ``pairs`` for
    :func:`~larkdocio.sheets.table.render_spreadsheet`, ``skips`` carrying Lark's own verbatim
    ``code``/``msg`` per refused tab, and ``skipped_any`` — the one flag to branch on.

    Read-only, and paced: every call passes the client's shared limiter.
    """
    url_domain, spreadsheet_token = resolve_spreadsheet(spreadsheet)
    if client is None:
        from larkdocio.sheets.client import SheetsReadClient

        client = SheetsReadClient.from_read_credentials(url_domain or domain)

    return client.read_spreadsheet(
        spreadsheet_token,
        tabs=tabs,
        value_render_option=value_render_option,
        date_time_render_option=date_time_render_option,
        user_id_type=user_id_type,
    )


def read_spreadsheet_markdown(
    spreadsheet: str,
    *,
    client=None,
    domain: str = "larksuite.com",
    tabs=None,
    value_render_option=None,
    date_time_render_option=None,
    user_id_type=None,
    heading_level: int = _DEFAULT_HEADING_LEVEL,
    mention_names=None,
) -> str:
    """Read a whole workbook and return **Markdown** — one heading + one GFM table per tab.

    ``spreadsheet`` is **either a Sheets URL or a bare token**, exactly as for
    :func:`read_spreadsheet`; this is that function plus
    ``render_spreadsheet(wb.pairs, skips=wb.skips)``, and nothing else. Use
    :func:`read_spreadsheet` when you want the data rather than the reading form — the
    Markdown can always be produced from it later without a second network read.

    **A partial read stays loud in the flat string**, which is why this twin maps cleanly at
    all: ``render_spreadsheet`` opens with a disclosure naming each missing tab and quoting
    Lark's own code and message, so a workbook that could not be read whole cannot reach you
    disguised as a complete one. With no skips the Markdown is byte-identical to what the
    two-step form always produced.

    **``fidelity`` is deliberately NOT here.** The L2 style/number-format read is a *second*
    client and a second credentialed leg (its own scope requirement is on this surface's rows
    in the permission registry) that this walk does not make;
    accepting the argument would imply this one call performs the export. Take
    :func:`read_spreadsheet`, run
    :func:`~larkdocio.sheets.export_reader.exported_by_sheet_id`, and call
    ``render_spreadsheet(..., fidelity=…)`` yourself — the recipe the guide already carries.
    """
    walked = read_spreadsheet(
        spreadsheet,
        client=client,
        domain=domain,
        tabs=tabs,
        value_render_option=value_render_option,
        date_time_render_option=date_time_render_option,
        user_id_type=user_id_type,
    )
    return render_spreadsheet(
        walked.pairs,
        skips=walked.skips,
        heading_level=heading_level,
        mention_names=mention_names,
    )
