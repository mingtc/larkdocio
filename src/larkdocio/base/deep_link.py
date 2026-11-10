"""larkdocio.base.deep_link — mint the click-measured Base table / view / record links.

``table_url`` and ``view_url`` build ``<tenant-host>/base/<app_token>?table=<table_id>``
and ``…&view=<view_id>[&record=<record_id>]`` — the grammar measured by click on
2026-08-17 to navigate to the named table and view, and to open the named record's card.
Both are **pure, offline** functions: they make zero API calls, exactly like their siblings
:func:`larkdocio.sheets.tab_link.tab_url` and :func:`larkdocio.common.doc_link.docx_block_url`.

**The tenant host is an INPUT, never derived and never invented.** The one host this library
holds by itself is the **API** domain (``feishu.cn`` | ``larksuite.com``), which is *not* the
tenant host a working link lives on — a real link sits on a tenant subdomain such as
``your-domain.larksuite.com``, which ``larksuite.com`` cannot produce. So the host comes from
the caller: both functions take the **Base's own URL** — the thing a caller already holds — and
read the tenant host and the ``app_token`` straight off it, verbatim. A URL with no host, one
that is not ``https``, or one that is not a ``/base/<token>`` URL is a **refusal**, not a
default; and a bare ``app_token`` is refused too, because a token carries no host and this
module will not choose one. That is also why the Base's own URL is asked for rather than
composed from :func:`larkdocio.common.url.validate_download_url`'s ``domain``, which is the API
domain by contract.

**A record is mintable here and is still not the best address for a record.** The
``record=`` parameter was clicked and the card opened, so it ships — but
:func:`larkdocio.base.permalink.record_permalink` fetches an address Lark itself minted, and
that one was measured byte-identical across a week. The constructed parameter is the answer for
the ids you already hold; the fetched permalink is the durable one. Both functions say so in
their own docstrings, because the caller meets the choice here.

**These builders resolve and validate nothing.** They compose an address out of what the caller
passes; an id that does not exist yields a link that does not open. Checking that a table, view
or record exists is a read, and this module makes no call.
"""
from typing import Optional

from larkdocio.common.url import BASE_DEEP_LINK_CLICK_MEASUREMENT, host_and_token

# The host/token split is `larkdocio.common.url.host_and_token` and is deliberately NOT
# re-implemented here: URL parsing belongs to the module that owns it, and this package is
# held free of raw-HTTP constructs by a guard in the source repository (`tests/test_base_client.py`)
# — a floor to respect, not
# an obstacle to route around with a hand-rolled two-line split.


def _checked_id(value, caller: str, what: str) -> str:
    if not value or not isinstance(value, str):
        raise ValueError(
            f"{caller} refuses an empty {what} — a link with a blank parameter is not a "
            "narrower link, it is a broken one"
        )
    return value


def table_url(base_url: str, table_id: str) -> str:
    """Mint the click-measured Base **table** link, from the Base's own URL and a table id.

    ``base_url`` is the Base's own URL — the thing a caller already holds — and it carries the
    two inputs this function will not invent: the **tenant host** (never derived from an API
    domain) and the **app token**. Both are used **verbatim**, and any query or fragment
    already on the URL is dropped. ``table_id`` is a table id every Base read already returns
    (``read_base(...).tables[i].table_id``). The result is
    ``https://<tenant-host>/base/<app_token>?table=<table_id>``.

    A missing/hostless URL, a non-``https`` URL, a URL that is not a ``/base/<token>`` link, a
    bare ``app_token``, or an empty ``table_id`` is a **refusal** (``ValueError``) — never a
    default. No API call is made, no credential is read, and nothing is validated: an id that
    does not exist yields a link that does not open.

    What this URL does, and exactly how far that is known:

        <<BASE_DEEP_LINK_MEASUREMENT>>
    """
    table_id = _checked_id(table_id, "table_url", "table_id")
    host, app_token = host_and_token(base_url, "base", "table_url")
    return f"https://{host}/base/{app_token}?table={table_id}"


def view_url(
    base_url: str,
    table_id: str,
    view_id: str,
    *,
    record: Optional[str] = None,
) -> str:
    """Mint the click-measured Base **view** link — and, with ``record=``, the record card.

    Same shape and same rules as :func:`table_url`: ``base_url`` is the Base's own URL and
    supplies the **tenant host** and the **app token**, both verbatim, with any existing query
    or fragment dropped. ``table_id`` and ``view_id`` are ids a Base read already returns
    (``list_views`` carries the view ids). The result is
    ``https://<tenant-host>/base/<app_token>?table=<table_id>&view=<view_id>``, plus
    ``&record=<record_id>`` when ``record`` is given.

    A missing/hostless URL, a non-``https`` URL, a URL that is not a ``/base/<token>`` link, a
    bare ``app_token``, an empty ``table_id`` or ``view_id``, or an **explicitly empty**
    ``record`` is a **refusal** (``ValueError``) — never a default. Omitting ``record``
    entirely is not a refusal; it is the view link. No API call is made and nothing is
    resolved or validated.

    **For a record, reach for :func:`larkdocio.base.permalink.record_permalink` first.** The
    ``record=`` parameter below is measured to open the card, and it is still the second-best
    address: ``record_permalink`` returns an address **minted by Lark** rather than composed
    here, measured **byte-identical across a week**, and it is not a grammar this library
    assembled. Use ``record=`` when the ids are what you have and a call is what you do not
    want to spend.

    What this URL does, and exactly how far that is known:

        <<BASE_DEEP_LINK_MEASUREMENT>>
    """
    table_id = _checked_id(table_id, "view_url", "table_id")
    view_id = _checked_id(view_id, "view_url", "view_id")
    host, app_token = host_and_token(base_url, "base", "view_url")
    link = f"https://{host}/base/{app_token}?table={table_id}&view={view_id}"
    if record is None:
        return link
    record = _checked_id(record, "view_url", "record")
    return f"{link}&record={record}"


# The measurement is authored ONCE in larkdocio.common.url and quoted here verbatim (a
# docstring must be a literal, so the quotation is spliced in after each def). Both functions
# carry it because a caller meets the question at whichever one he calls, and averaging the
# two labels — or citing the paragraph from only one — is how the edge of the evidence gets
# lost.
for _minter in (table_url, view_url):
    _minter.__doc__ = (_minter.__doc__ or "").replace(
        "<<BASE_DEEP_LINK_MEASUREMENT>>", BASE_DEEP_LINK_CLICK_MEASUREMENT
    )
del _minter


__all__ = [
    "BASE_DEEP_LINK_CLICK_MEASUREMENT",
    "table_url",
    "view_url",
]
