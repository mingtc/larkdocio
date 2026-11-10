"""larkdocio.sheets.tab_link — mint the one click-proven spreadsheet deep link.

``tab_url`` builds ``<tenant-host>/sheets/<spreadsheet_token>?sheet=<sheet_id>`` — the
grammar confirmed by click to navigate to the correct tab. It is a **pure, offline**
function: it makes zero API calls.

**The tenant host is an INPUT, never derived and never invented.** This is the first URL
this library mints, and it inherits no host convention: every user-facing URL the library
reports elsewhere is a string the *server* handed back. The one host the library holds by
itself is the **API** domain (``feishu.cn`` | ``larksuite.com``) — which is **not** the
tenant host in a working link (a real link lives on a tenant subdomain such as
``your-domain.larksuite.com``, which ``larksuite.com`` cannot produce). So the host must
come from the caller: ``tab_url`` takes the **sheet's own URL** — the natural thing a caller
already holds — and reads the tenant host and the spreadsheet token straight off it, so a
working tab link is minted without the library ever choosing a host. A URL with no host (or
one that is not a ``/sheets/<token>`` URL) is a **refusal**, not a default.

Only tab-level links are mintable; a cell/range link is not — see
:data:`larkdocio.common.url.SHEETS_CELL_LINK_UI_ONLY`, quoted in :func:`tab_url`'s own
docstring, because the next question a caller asks is "can I point at a cell?".
"""
import urllib.parse

from larkdocio.common.url import SHEETS_CELL_LINK_UI_ONLY


def tab_url(sheet_url: str, sheet_id: str) -> str:
    """Mint the click-proven spreadsheet **tab** link, from the sheet's own URL and a tab id.

    ``sheet_url`` is the spreadsheet's own URL — the thing a caller already holds — and it
    carries the two inputs this function needs: the **tenant host** (never derived from an
    API domain, never invented) and the **spreadsheet token**. Both are used **verbatim**.
    ``sheet_id`` is the tab, an id every Sheets read already returns. The result is
    ``https://<tenant-host>/sheets/<spreadsheet_token>?sheet=<sheet_id>``.

    A missing/hostless URL, a non-``https`` URL, a URL that is not a ``/sheets/<token>``
    link, or an empty ``sheet_id`` is a **refusal** (``ValueError``) — never a default. No
    API call is made and no host is ever derived from the API domain.

    What this URL does: it **opens that tab** (click-proven). What it deliberately does NOT
    do — because the next question is always "can I point at a cell?":

        <<CELL_LINK_WARNING>>
    """
    if not sheet_id:
        raise ValueError("tab_url refuses an empty sheet_id — a tab link needs a tab id")
    if not sheet_url or not isinstance(sheet_url, str):
        raise ValueError("tab_url refuses a missing sheet_url — the tenant host is an input")

    parts = urllib.parse.urlsplit(sheet_url)
    if parts.scheme != "https" or not parts.netloc:
        raise ValueError(
            "tab_url needs the sheet's own https URL (carrying the tenant host); "
            f"got {sheet_url!r}"
        )
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) != 2 or segments[0] != "sheets":
        raise ValueError(
            f"tab_url needs a /sheets/<token> URL to read the token and host from; got {sheet_url!r}"
        )
    spreadsheet_token = segments[1]
    return f"https://{parts.netloc}/sheets/{spreadsheet_token}?sheet={sheet_id}"


# The cell-link warning is authored ONCE in larkdocio.common.url and quoted here verbatim
# (a docstring must be a literal, so the quotation is spliced in after the def rather than
# built inline). The next question after "how do I link a tab?" is always "…and a cell?".
tab_url.__doc__ = tab_url.__doc__.replace("<<CELL_LINK_WARNING>>", SHEETS_CELL_LINK_UI_ONLY)
