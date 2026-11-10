"""larkdocio.common.doc_link — mint the docx deep links, each labelled with its own evidence.

``docx_block_url`` builds ``<tenant-host>/docx/<doc_token>#<block_id>`` — the **bare
fragment** grammar, the one confirmed by click to anchor on the target block. It is a
**pure, offline** function: it makes zero API calls, exactly like its Sheets twin
:func:`larkdocio.sheets.tab_link.tab_url`.

**The tenant host is an INPUT, never derived and never invented.** The only host this
library holds by itself is the **API** domain (``feishu.cn`` | ``larksuite.com``), which is
not the tenant host a working link lives on (a real link sits on a tenant subdomain such as
``your-domain.larksuite.com``, which ``larksuite.com`` cannot produce). So the host comes
from the caller: ``docx_block_url`` takes the **document's own URL** — the thing a caller
already holds — and reads the tenant host and the doc token straight off it. A URL with no
host, one that is not ``https``, or one that is not a ``/docx/<token>`` URL is a
**refusal**, not a default.

**Two grammars, two different truths, and they must not be blurred.** The bare fragment
this function mints is measured and mintable
(:data:`larkdocio.common.url.DOCX_BLOCK_ANCHOR_MEASUREMENT`); the ``#share-<token>``
section link a person copies out of the web client is neither mintable nor fetchable
(:data:`larkdocio.common.url.DOCX_SECTION_ANCHOR_UI_ONLY`). Both paragraphs are quoted
verbatim in :func:`docx_block_url`'s own docstring, because the caller meets both questions
here — and the near-miss spelling of the second is the hazard, so passing a ``share-``
prefixed id is refused loudly rather than turned into a link that lies about deleted
content.

``docx_edition_url`` mints the third grammar, ``…/docx/<doc_token>?edition_id=<version
token>``, under the same fencing — and with its own evidence label, said out loud
(:data:`larkdocio.common.url.DOCX_EDITION_LINK_CLICK_MEASUREMENT`): its path half is Lark's
own reported URL and its token is Lark's own, and the query grammar was **clicked on
2026-08-11 in the Lark WEB client, on one tenant**, where it opened the named version — with
every unclicked axis (mobile, the desktop app, wiki-wrapped, another tenant) still named
unmeasured. Three links, three different strengths of claim, each carrying its own; the
labels are never averaged.
"""
import urllib.parse

from larkdocio.common.url import (
    DOCX_BLOCK_ANCHOR_MEASUREMENT,
    DOCX_EDITION_LINK_CLICK_MEASUREMENT,
    DOCX_SECTION_ANCHOR_UI_ONLY,
)


def docx_block_url(doc_url: str, block_id: str) -> str:
    """Mint the click-proven docx **block** link, from the document's own URL and a block id.

    ``doc_url`` is the document's own URL — the thing a caller already holds — and it
    carries the two inputs this function needs: the **tenant host** (never derived from an
    API domain, never invented) and the **doc token**. Both are used **verbatim**, and any
    query or fragment already on it is dropped. ``block_id`` is a block identifier every
    docx read already returns (``emit_block_ids`` / ``project_block_ids`` put them in reach
    of a Markdown consumer). The result is
    ``https://<tenant-host>/docx/<doc_token>#<block_id>``.

    A missing/hostless URL, a non-``https`` URL, a URL that is not a ``/docx/<token>`` link,
    a wiki-wrapped URL (an **unmeasured** grammar — refused rather than guessed), an empty
    ``block_id``, or a ``share-`` prefixed id (the hazard below) is a **refusal**
    (``ValueError``) — never a default. No API call is made.

    What this URL does, and exactly how far that is known:

        <<BLOCK_ANCHOR_MEASUREMENT>>

    What it deliberately does NOT do — the other fragment grammar, which looks similar and
    is not the same claim at all:

        <<SECTION_ANCHOR_WARNING>>
    """
    if not block_id or not isinstance(block_id, str):
        raise ValueError(
            "docx_block_url refuses an empty block_id — a block link needs a block id"
        )
    if block_id.startswith("share-"):
        raise ValueError(
            "docx_block_url refuses a `share-` prefixed id: that spelling is the hazard, "
            "not the link. A `…#share-<block_id>` URL navigates nowhere and shows a toast "
            'reading "The selection content has been deleted" about content that is '
            "perfectly intact. Pass the bare block id; a real share token cannot be minted "
            "at all."
        )
    if not doc_url or not isinstance(doc_url, str):
        raise ValueError(
            "docx_block_url refuses a missing doc_url — the tenant host is an input"
        )

    parts = urllib.parse.urlsplit(doc_url)
    if parts.scheme != "https" or not parts.netloc:
        raise ValueError(
            "docx_block_url needs the document's own https URL (carrying the tenant host); "
            f"got {doc_url!r}"
        )
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) == 2 and segments[0] == "wiki":
        raise ValueError(
            "docx_block_url refuses a wiki-wrapped URL: the wiki grammar is UNMEASURED — "
            "never clicked, so neither refuted nor supported — and this function does not "
            f"guess at an untested grammar; got {doc_url!r}"
        )
    if len(segments) != 2 or segments[0] != "docx":
        raise ValueError(
            "docx_block_url needs a /docx/<token> URL to read the token and host from; "
            f"got {doc_url!r}"
        )
    doc_token = segments[1]
    return f"https://{parts.netloc}/docx/{doc_token}#{block_id}"


def docx_edition_url(doc_url: str, version_token: str) -> str:
    """Mint the docx **named-edition** link, from the document's own URL and a version token.

    Same shape and same rules as :func:`docx_block_url`: ``doc_url`` is the document's own
    URL and carries the two things this function will not invent — the **tenant host** (never
    derived from an API domain) and the **doc token** — both used **verbatim**. The result is
    ``https://<tenant-host>/docx/<doc_token>?edition_id=<version_token>``. ``version_token``
    is a version's token as the Drive versions family returns it (``Version.token``).

    **Any query or fragment already on ``doc_url`` is dropped.** This function then adds a
    query of its own, so a ``?from=space`` on the input does **not** survive into the result
    and must not be assumed to — the link is rebuilt from the host and the token alone.

    A missing/empty/non-string ``doc_url``, a non-``https`` URL, a hostless URL, a URL that is
    not a ``/docx/<token>`` link, a wiki-wrapped URL (an **unmeasured** grammar — refused
    rather than guessed), or an empty/non-string ``version_token`` is a **refusal**
    (``ValueError``), raised from the string alone before anything else. No API call is made,
    and no credential is read.

    What this URL is, and exactly how far that is known — read this before you put one in a
    ledger:

        <<EDITION_LINK_DISCLOSURE>>
    """
    if not version_token or not isinstance(version_token, str):
        raise ValueError(
            "docx_edition_url refuses an empty version_token — pass a version's token as "
            "the versions family returns it (`Version.token`)"
        )
    if not doc_url or not isinstance(doc_url, str):
        raise ValueError(
            "docx_edition_url refuses a missing doc_url — the tenant host is an input; pass "
            "the document's own https URL"
        )

    parts = urllib.parse.urlsplit(doc_url)
    if parts.scheme != "https" or not parts.netloc:
        raise ValueError(
            "docx_edition_url needs the document's own https URL (carrying the tenant "
            f"host); got {doc_url!r}"
        )
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) == 2 and segments[0] == "wiki":
        raise ValueError(
            "docx_edition_url refuses a wiki-wrapped URL: the wiki grammar is UNMEASURED — "
            "never clicked, so neither refuted nor supported — and this function does not "
            "guess at an untested grammar. Pass the document's own /docx/<token> URL; got "
            f"{doc_url!r}"
        )
    if len(segments) != 2 or segments[0] != "docx":
        raise ValueError(
            "docx_edition_url needs a /docx/<token> URL to read the token and host from; "
            f"got {doc_url!r}"
        )
    doc_token = segments[1]
    return f"https://{parts.netloc}/docx/{doc_token}?edition_id={version_token}"


# Both paragraphs are authored ONCE in larkdocio.common.url and quoted here verbatim (a
# docstring must be a literal, so the quotation is spliced in after the def rather than
# built inline). The caller meets both questions at this function: "what does the link I
# just minted do?" and "…and the other fragment I have seen in the wild?".
docx_block_url.__doc__ = (
    (docx_block_url.__doc__ or "")
    .replace("<<BLOCK_ANCHOR_MEASUREMENT>>", DOCX_BLOCK_ANCHOR_MEASUREMENT)
    .replace("<<SECTION_ANCHOR_WARNING>>", DOCX_SECTION_ANCHOR_UI_ONLY)
)

# The edition link's disclosure is authored once in the same place and spliced in the same
# way. It is the whole reason this function is safe to ship: the claim it makes is exactly as
# wide as the click and the two API answers behind it, and the docstring is where a caller
# meets that edge.
docx_edition_url.__doc__ = (docx_edition_url.__doc__ or "").replace(
    "<<EDITION_LINK_DISCLOSURE>>", DOCX_EDITION_LINK_CLICK_MEASUREMENT
)
