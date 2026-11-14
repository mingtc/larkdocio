"""larkdocio.common.url — shared URL validation / unescaping.

Relocated from ``larkdocio.utils.url`` into the shared read/write core (LD-061)
because both the reader and the forthcoming writer resolve Lark
document URLs. ``larkdocio.utils.url`` remains as a transparent back-compat shim.

Behavior is **byte-identical** to the pre-extraction module — this is a move, not
a rewrite. ``validate_download_url`` keeps raising the builtin ``ValueError`` on a
malformed URL (its established, tested contract; a local input-validation failure,
not a Lark API round-trip).
"""
import urllib.parse
import re
from dataclasses import dataclass
from typing import Optional, Tuple, Union


def unescape_url(raw_url: str) -> str:
    try:
        return urllib.parse.unquote(raw_url)
    except Exception:
        return raw_url


#: The path shapes that name a **document** — what the docx download path can resolve.
#: ``docs`` is the unsupported legacy shape; it is *recognised* here and refused further in,
#: which is the same division the two shapes below now follow.
DOCUMENT_URL_TYPES = ("docs", "docx", "wiki")

#: The **type discriminator → the surface that reads that type.** This is what makes the
#: middle value of :func:`validate_download_url`'s return a usable discriminator rather than a
#: label: a caller holding a URL routes on it instead of re-parsing the URL, which is exactly
#: the symmetry the sheets recipes lacked while they hand-rolled the parse.
#:
#: ``base`` routes to the **Base (bitable)** surface (``larkdocio.base``), whose reads
#: ``read_base`` / ``read_base_markdown`` take either a Base URL or the bare ``app_token`` its
#: slug is (the surface also carries plan-gated record- and schema-write engines).
#: Recognition is still not a download — this map says which surface reads a type, and the
#: docx download path refuses everything that is not a document.
#:
#: ``drive`` routes a Drive folder URL to the **Drive** surface: the folder read
#: (``larkdocio.drive.read_folder``, the ``larkdocio folder`` verb) lists and reads what is
#: inside it. This map turns a folder link into a folder token; it never follows the link.
URL_TYPE_SURFACES = {
    **{document_type: "docx" for document_type in DOCUMENT_URL_TYPES},
    "sheets": "sheets",
    "base": "base",
    "drive": "drive",
}

#: **The URL PATH SHAPE → the type discriminator it reports.** Every shape but one is its own
#: discriminator, which is why this table did not need to exist while the accepted set was five
#: single-segment shapes. A Drive folder is the exception: its path carries **two** segments
#: (``/drive/folder/<token>``), while the discriminator a caller routes on is the single word
#: ``drive`` — so the path vocabulary and the type vocabulary have stopped being the same list
#: and are no longer allowed to pretend they are.
#:
#: The accepting pattern is built from THIS table; :data:`URL_TYPE_SURFACES` is what a caller
#: routes on. Their agreement — every shape reports a known type, every known type is reachable
#: from some shape — is a guarded invariant rather than a convention.
URL_PATH_SHAPES = {
    **{document_type: document_type for document_type in DOCUMENT_URL_TYPES},
    "sheets": "sheets",
    "base": "base",
    "drive/folder": "drive",
}

#: What a rejected URL is told, verbatim. Names **what is accepted** — now all six path
#: shapes, since a spreadsheet, a Base and a Drive folder URL are recognised rather than refused
#: — and the one
#: knob that widens the host set (``allowHost`` is the public CLI flag ``--allowHost`` / this
#: function's own ``allow_host`` parameter, so naming it is help, not a leak). It also draws the
#: line recognition does not cross: knowing what a URL points at is not being able to download
#: it, and the caller finds that out here rather than from a deeper, vaguer failure.
#:
#: It deliberately no longer teaches the two-line hand-rolled parse it used to. That expression
#: was a workaround for this function refusing the URL; the function accepts it now, so
#: teaching the workaround would send a consumer to re-implement what they just called.
#: The folder line names the surface a folder url belongs to and the call that reads it.
#: **The token alphabet, authored once.** A Lark token is an unbroken run of
#: ``[A-Za-z0-9]`` and nothing else, and it occupies its **whole** path segment. Both
#: parses below read the token region through this one pattern (``larkdocio.base.read``
#: holds the same shape for a bare ``app_token``), so the alphabet is one decision rather
#: than five copies drifting apart.
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

#: What a **mangled token region** is told (LD-396). Distinct from the generic refusal above
#: on purpose: this URL *is* a recognised Lark shape on a recognised host — only its token
#: is not a token — and a caller who is told "not a recognised Lark URL" would go looking in
#: the wrong place. It quotes the offending region so the refusal is discoverable rather than
#: silent, and states the rule it broke.
_MANGLED_TOKEN_MESSAGE = (
    "not a Lark token: {token!r} in {raw_url!r}. A token is an unbroken run of letters and "
    "digits filling its whole path segment; this one carries something else (a hyphen, an "
    "underscore, a dot, a space). The url is refused WHOLE rather than truncated to the "
    "leading run — a truncated token looks exactly like a real one and becomes a lookup for "
    "a document that does not exist, or worse, one that does. Check the link you pasted."
)

_INVALID_URL_MESSAGE = (
    "not a recognised Lark URL: {raw_url!r}. Accepted: "
    "https://<host>.feishu.cn|larksuite.com/<docs|docx|wiki|sheets|base|drive/folder>/<token> "
    "(any number of subdomains; one extra host may be allowed via allowHost). The returned "
    "type says WHICH surface the url names, and recognition is not reach: only docx and wiki "
    "can be handed to a document download — a sheets url is read through the Sheets surface, "
    "a base url through the Base surface (larkdocio.base.read_base_markdown), and a "
    "drive/folder url names a Drive folder, whose type is 'drive' and whose surface is the "
    "drive one, read by `larkdocio folder \"<url>\" -o ./out/` (or "
    "larkdocio.drive.read_folder) — a folder url is parsed here, not followed."
)
# LD-658 AC2: this clause used to end "no folder read has shipped yet", which had been false
# since the folder read shipped — `larkdocio folder` is an advertised CLI verb and `read_folder`
# is in `drive.__all__`. It is the copy that RENDERS (both raise sites below format it), and a
# user who mistyped the host of a working folder link was told the feature does not exist. The
# true half is kept verbatim: this module reports a url's TYPE and never follows it.


def host_and_token(raw_url, path_shape: str, caller: str) -> Tuple[str, str]:
    """The **tenant host** and the object token, read off an object's own ``https`` URL.

    The link minters' shared front half. ``path_shape`` is the single path segment the URL must
    carry (``"base"``, ``"docx"``, ``"sheets"``); ``caller`` names the function in every refusal,
    so a consumer is told which call refused and why rather than meeting a bare parse error.

    It exists **here**, in the module that owns URL parsing, rather than in each surface that
    mints a link: a minter that hand-rolled its own split would be the same two-line expression
    the guide spent a release teaching consumers to stop writing, and
    :mod:`larkdocio.base.deep_link` additionally may not reach a URL library at all (the Base
    package is held raw-HTTP-free by a guard **in the source repository**,
    ``tests/test_base_client.py``, and that guard is a floor, not an obstacle to route around).

    Returns ``(tenant_host, token)`` — both **verbatim**, both from the caller's own URL. It
    derives no host: :func:`validate_download_url` returns the **API** domain, which is not the
    host a working link lives on. Anything that cannot supply both — an empty/non-string URL, a
    non-``https`` URL, a hostless URL, or a path that is not ``/<path_shape>/<token>`` — is a
    ``ValueError`` refusal, never a default.
    """
    if not raw_url or not isinstance(raw_url, str):
        raise ValueError(
            f"{caller} refuses a missing url — the tenant host is an input, never derived "
            f"from the API domain and never invented; pass the {path_shape}'s own https URL"
        )
    parts = urllib.parse.urlsplit(raw_url)
    if parts.scheme != "https" or not parts.netloc:
        raise ValueError(
            f"{caller} needs the {path_shape}'s own https URL (carrying the tenant host); got "
            f"{raw_url!r}. A bare token cannot be used here: a token carries no host, and a "
            "link on the API domain is not a link on your tenant."
        )
    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) != 2 or segments[0] != path_shape:
        raise ValueError(
            f"{caller} needs a /{path_shape}/<token> URL to read the token and the tenant "
            f"host from; got {raw_url!r}"
        )
    return parts.netloc, segments[1]


def validate_download_url(raw_url: str, allow_host: str = "") -> Tuple[str, str, str]:
    """Parse a Lark URL into ``(domain, url_type, token)``, or raise ``ValueError``.

    ``url_type`` is one of :data:`URL_TYPE_SURFACES`' keys — the three document shapes plus
    ``sheets``, ``base`` and ``drive`` — so **one** function answers "what is this URL, and what
    reads it", and a caller routes on the returned type instead of writing the parse again. Both
    spreadsheet entry points in the shipped guide used to carry the same hand-rolled two-line
    URL→token expression precisely because this function refused their URL; recognising the
    shape is what let those copies collapse into this call.

    ``domain`` is the **API** domain (``feishu.cn`` | ``larksuite.com`` | ``allow_host``), not
    the tenant host in the URL — which is the other half of what the hand-rolled expression
    could not produce, and a documented trap in its own right.

    Recognising a type is not the same as being able to read it *here*: only ``docx``/``wiki``
    reach the document download (``docs`` is the unsupported legacy shape), a ``sheets`` URL is
    read through the Sheets surface, and a ``base`` URL through the Base surface
    (``larkdocio.base.read_base_markdown``, which also carries the plan-gated record- and
    schema-write engines). The refusal message states that division and names the surface that
    reads each type, so a caller is routed rather than merely refused.

    **A ``drive/folder`` URL** reports the type ``drive`` and its token is the **folder
    token**, which the Drive surface's folder read takes (``larkdocio folder "<url>"`` or
    ``larkdocio.drive.read_folder``). Recognising it is the whole of what this function does
    for it: it turns a folder link into a folder token and never follows it.

    Widens **path** shapes only — and the folder shape is the first accepted path with **two**
    segments, which is why the shape vocabulary now lives in :data:`URL_PATH_SHAPES` beside the
    type vocabulary rather than being assumed identical to it. Host policy is unchanged:
    ``allow_host`` remains the single opt-in, rejection remains a builtin ``ValueError`` (its
    established contract), and every URL shape accepted before is accepted unchanged.

    This answers **what a URL points at at the surface level and where it is read**. To read the
    fragment or query of a *deep* link — a docx section anchor, a spreadsheet tab or cell, a
    Base record — call :func:`parse_deep_link` instead: it returns a typed address carrying the
    opaque parts unaltered, whereas this function reports only the coarse type and drops them.
    Neither the return tuple below nor its type vocabulary moves for that; the deep-link parse is
    a **separate** callable so this contract stays exactly as its consumers already depend on it.

    **Not to be merged with**
    :func:`larkdocio.sheets.embed.split_compound_token`, which solves a different problem: it
    splits a docx type-30 **compound token** (``<spreadsheet_token>_<sheet_id>``) on its last
    underscore. That input is not a URL and this input is not a compound token; the two look
    like "the token parsers" from a distance and consolidating them would break both.
    """
    hosts = ["feishu.cn", "larksuite.com"]
    if allow_host:
        hosts.append(allow_host)

    escaped_hosts = [re.escape(h) for h in hosts]
    hosts_pattern = "|".join(escaped_hosts)

    # Allow 0..N subdomain labels before the base host.
    # Example: https://your-domain.larksuite.com/docx/<id>
    # Longest shape first, so a two-segment shape cannot be shadowed by a one-segment prefix of
    # itself if one is ever added ("drive" and "drive/folder" would otherwise be order-sensitive).
    shapes_pattern = "|".join(
        re.escape(shape) for shape in sorted(URL_PATH_SHAPES, key=len, reverse=True)
    )
    # The token region is captured as the WHOLE path segment (LD-396), not as the leading
    # alphanumeric run of it. The old pattern ended the token at the first character outside
    # the alphabet and returned the prefix, so `…/docx/Ab-c_1` yielded `'Ab'` — a silent
    # truncation into a structurally plausible token. Capturing the segment and then
    # requiring the alphabet to fill it is what makes the parse full-token-or-refuse.
    pattern = rf"^https://([\w-]+\.)*({hosts_pattern})/({shapes_pattern})/([^/?#]*)"
    reg = re.compile(pattern)

    match = reg.search(raw_url)
    if not match:
        raise ValueError(_INVALID_URL_MESSAGE.format(raw_url=raw_url))

    # groups:
    # 1: optional subdomains (if any)
    # 2: base host (feishu.cn | larksuite.com | allowHost)
    # 3: the matched PATH SHAPE — a key of URL_PATH_SHAPES, which is not always the type
    # 4: the token REGION — the whole segment, not yet known to be a token
    token = match.group(4)
    if not token:
        # A shape with no token segment at all was never a recognised URL and still isn't.
        raise ValueError(_INVALID_URL_MESSAGE.format(raw_url=raw_url))
    if not _TOKEN_RE.fullmatch(token):
        raise ValueError(_MANGLED_TOKEN_MESSAGE.format(token=token, raw_url=raw_url))
    return match.group(2), URL_PATH_SHAPES[match.group(3)], token


# --------------------------------------------------------------------------- #
# Deep-link parsing — the four observed grammars, carried unaltered.            #
#                                                                               #
# A deep link is a URL that points BELOW a whole document: at a section of a    #
# doc, a tab or cell of a spreadsheet, or a single Base record. Four such       #
# grammars have been observed from the Lark UI. This parse recognises them and  #
# returns a typed address; it does NOT widen validate_download_url, whose       #
# public 3-tuple and type vocabulary a consumer already depends on.             #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DocAnchor:
    """A docx **section** deep link: ``…/docx/<doc_token>#share-<share_token>``.

    ``share_token`` is the fragment's opaque tail, carried **exactly** as it arrived —
    never normalised, split, lower-cased or validated.

    It is **NOT a ``block_id`` and must never be treated as one.** The field is named
    ``share_token`` precisely so it cannot be mistaken for a block id. The fragment is a
    share token the Lark web client mints when a human copies a section link; it is a
    *separately minted* value, not any block's id — an exhaustive check of a real
    document's every block found no match, and the docx block-get endpoint returns
    "not found" for the share token while returning the real block for a real id. No API
    mints, lists or resolves one. So a ``DocAnchor`` is an **address, not a capability**:
    it can be recognised and carried, and it can NOT be fetched. There is no docx
    share/permalink endpoint to turn it into a request the API will accept.
    """

    doc_token: str
    share_token: str


@dataclass(frozen=True)
class SheetAnchor:
    """A spreadsheet deep link: ``…/sheets/<spreadsheet_token>?sheet=<sheet_id>`` and,
    for a cell/range link, ``&rangeId=<sheet_id>_<opaque>&rangeVer=<n>``.

    ``sheet_id`` identifies the tab and is an id every Sheets read already returns — the
    one part of this address that IS actionable (see :func:`larkdocio.sheets.tab_url`,
    which mints exactly the tab link).

    ``range_id`` and ``range_ver`` are ``None`` for a tab link and, for a cell/range link,
    carry the ``rangeId`` and ``rangeVer`` **exactly** as they arrived (``range_ver`` stays
    a string; it is not parsed to an int). ``range_id`` is opaque and **versioned** — a
    stored server-side object, not a computed address — and is carried **whole**: it is NOT
    the docx compound token and is deliberately not fed to
    :func:`larkdocio.sheets.embed.split_compound_token`, whose shape it merely rhymes with.
    A ``range_id`` can NOT be minted or resolved: no endpoint in the Sheets surface creates
    or looks one up, so a cell/range anchor is an address only.
    """

    spreadsheet_token: str
    sheet_id: str
    range_id: Optional[str] = None
    range_ver: Optional[str] = None


@dataclass(frozen=True)
class RecordAnchor:
    """A Base **record** deep link: ``…/record/<record_token>``.

    ``record_token`` is carried **exactly** as it arrived. This parse claims nothing about
    reachability: turning a record link into fetched data is a separate, API-facing
    operation, not something this offline parse offers.
    """

    record_token: str


@dataclass(frozen=True)
class NotADeepLink:
    """The typed answer for a URL that is **not** one of the four recognised deep-link
    grammars — a plain document/sheet/base URL with no fragment or query, or a
    non-Lark URL. It carries the original ``url`` and nothing else: the parse never
    returns a partially-filled anchor and never guesses. A plain document, spreadsheet or
    Base URL is the province of :func:`validate_download_url`.
    """

    url: str


#: A parsed deep link: one of the four typed addresses, or the typed not-a-deep-link answer.
DeepLink = Union[DocAnchor, SheetAnchor, RecordAnchor, NotADeepLink]

#: The tenant-host pattern a deep link may carry — the same host policy as
#: :func:`validate_download_url` (0..N subdomain labels before the base host), so the
#: multi-label tenant host (``<tenant>.larksuite.com`` and deeper) is accepted exactly as it
#: is there — the extra labels are the whole point, since ``larksuite.com`` cannot produce them.
_DEEP_LINK_HOST = r"([\w-]+\.)*(feishu\.cn|larksuite\.com)"


def parse_deep_link(url: str, allow_host: str = "") -> "DeepLink":
    """Parse a Lark **deep** link into a typed address, carrying every opaque part unaltered.

    Recognises the four observed grammars and nothing else:

    * ``…/docx/<doc>#share-<token>``  → :class:`DocAnchor`
    * ``…/sheets/<tok>?sheet=<id>``   → :class:`SheetAnchor` (tab)
    * ``…/sheets/<tok>?sheet=<id>&rangeId=<id>_<opaque>&rangeVer=<n>`` → :class:`SheetAnchor` (cell/range)
    * ``…/record/<token>``            → :class:`RecordAnchor`

    Anything else — including a **plain** document/spreadsheet/Base URL with no fragment or
    query — returns :class:`NotADeepLink`; the parse never returns a half-filled anchor and
    never guesses. The Base ``…/base/<tok>?table=&view=[&record=]`` query form is **not**
    among the recognised grammars and is deliberately left as ``NotADeepLink`` — **for a
    different reason than it once was**. Until 2026-08-17 the stated reason was that the
    grammar was *unverified*; that reason is kept here as dated history and no longer holds,
    because the grammar was click-measured that day and
    :func:`larkdocio.base.table_url` / :func:`larkdocio.base.view_url` now mint it (the edge
    of that evidence is :data:`BASE_DEEP_LINK_CLICK_MEASUREMENT`, quoted below). What did
    **not** change is the behaviour: extending this parse would move a shipped typed return
    value for an input consumers already pass, which is its own change with its own
    consumers — so the exclusion stands on that, and on nothing about the evidence.

        <<BASE_DEEP_LINK_MEASUREMENT>>

    **Pass-through fidelity is the contract.** The ``share_token``, the ``rangeId``, the
    ``rangeVer`` and the record token are returned **exactly** as they arrived — not
    normalised, lower-cased, split, re-encoded or validated. The library cannot mint or
    fetch a ``share_token`` or a ``rangeId`` (see the types' own docstrings), but it can
    losslessly *carry* them, which is what an agent maintaining a document full of
    human-pasted links actually needs.

    This is the **deep-link** counterpart of :func:`validate_download_url`: that function
    answers "what surface reads this URL" and returns a coarse ``(domain, type, token)``
    3-tuple, dropping the fragment and query; this one keeps them. The two are separate
    callables on purpose — ``validate_download_url``'s public tuple does not move.
    """
    if not url or not isinstance(url, str):
        return NotADeepLink(url)

    hosts = r"([\w-]+\.)*(feishu\.cn|larksuite\.com" + (
        "|" + re.escape(allow_host) if allow_host else ""
    ) + ")"
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not re.fullmatch(hosts, parts.netloc):
        return NotADeepLink(url)

    segments = [s for s in parts.path.split("/") if s]

    # FULL-TOKEN-OR-REFUSE (LD-396). Every grammar below addresses its subject by a token in
    # segment 1, so the alphabet is checked ONCE, here, for all of them: a token region
    # carrying anything outside `[A-Za-z0-9]` makes the url not-a-deep-link. This parse never
    # truncated (it reads whole segments), but it did accept a mangled region and hand it on
    # as a doc/spreadsheet/record token, which is the same trap seen from the other side.
    # The opaque tails — the `share-` fragment, `rangeId`, `rangeVer`, `sheet` — are NOT
    # token regions and stay pass-through-verbatim, unvalidated, exactly as promised.
    if len(segments) == 2 and not _TOKEN_RE.fullmatch(segments[1]):
        return NotADeepLink(url)

    # docx section anchor — the fragment is a #share-<token>, nothing else counts
    if len(segments) == 2 and segments[0] == "docx" and parts.fragment.startswith("share-"):
        return DocAnchor(doc_token=segments[1], share_token=parts.fragment[len("share-"):])

    # spreadsheet tab / cell — the ?sheet= query is what makes it a deep link
    if len(segments) == 2 and segments[0] == "sheets":
        # Parse the raw query WITHOUT urllib's percent-decoding so every value is the
        # exact input slice (pass-through fidelity). The observed tokens carry no encoding.
        pairs = dict(
            kv.split("=", 1) for kv in parts.query.split("&") if "=" in kv
        )
        sheet_id = pairs.get("sheet")
        if sheet_id:
            return SheetAnchor(
                spreadsheet_token=segments[1],
                sheet_id=sheet_id,
                range_id=pairs.get("rangeId"),
                range_ver=pairs.get("rangeVer"),
            )
        return NotADeepLink(url)

    # Base record permalink
    if len(segments) == 2 and segments[0] == "record":
        return RecordAnchor(record_token=segments[1])

    return NotADeepLink(url)


# --------------------------------------------------------------------------- #
# The two loud negatives — authored ONCE here, quoted verbatim wherever they    #
# appear (the shipped guide, capabilities() notes, and the dev-repo capability  #
# matrices). A deep link the library can PARSE is not one it can MINT or FETCH; #
# these say so plainly, so the next consumer does not re-run the spike that     #
# established it. Consumer dialect only.                                        #
# --------------------------------------------------------------------------- #

#: Docx **section** (`#share-`) links are UI-only — neither mintable nor fetchable — and the
#: near-miss spelling of one is HAZARDOUS, with the false toast quoted. The verdict is scoped
#: to the `share-` grammar alone; the bare-fragment grammar beside it is a separate, measured
#: claim (:data:`DOCX_BLOCK_ANCHOR_MEASUREMENT`).
DOCX_SECTION_ANCHOR_UI_ONLY = (
    "A docx section link (`…/docx/<doc>#share-<token>`) is UI-only: this library cannot "
    "mint one and cannot fetch one. The fragment is a share token the Lark web client mints "
    "when a person copies a section link; it is NOT a block id (an exhaustive check of a "
    "real document's every block found no match, and the block-get endpoint returns "
    "not-found for the share token while returning the block for a real id), and no docx "
    "share or permalink endpoint exists to turn it into anything the API will accept. This "
    "is not a permissions problem: the data does not exist in the API at all, so no grant "
    "would change either answer. That verdict is about the `share-` grammar and nothing "
    "wider: the OTHER docx fragment grammar — a bare `…/docx/<doc>#<block_id>` — IS "
    "mintable, and is a separate measured claim (see `docx_block_url`). Do not try to "
    "bridge the two. The obvious guess, `…/docx/<doc>#share-<block_id>`, navigates nowhere "
    'and shows a toast reading "The selection content has been deleted" about content that '
    "is perfectly intact — observed on every block kind tried, and the same lie-class as "
    "the sheets cell-link toast: a reader who sees it will file a data-loss bug against "
    "your document or against this library. To point at a passage in band, emit the block "
    "ids with `emit_block_ids` and mint the bare-fragment link with `docx_block_url` — "
    "a share URL is not available."
)

#: Docx **block** (`#<block_id>`) links ARE mintable — with the edge of the evidence stated,
#: because a positive capability claim is owed the same enumeration as a negative one.
DOCX_BLOCK_ANCHOR_MEASUREMENT = (
    "A docx block link (`…/docx/<doc>#<block_id>`) IS mintable, offline: "
    "`docx_block_url(doc_url, block_id)` builds one from the document's own URL and a block "
    "id the reader already emits, and makes zero API calls. Here is the edge of the "
    "evidence, so the claim is never read wider than what was measured. The bare fragment "
    "was clicked on 2026-08-10 in the Lark WEB client, on one tenant, against all six block "
    "kinds tried: heading1, heading2, paragraph, table, bullet and code. Every one of them "
    "anchors — a heading, paragraph or bullet target is jumped to, while a table or code "
    "target is moved to with a momentary highlight, which is how those blocks show a "
    "selection. The `?blockId=<block_id>` query form was clicked in the same sitting and "
    "does nothing at all. UNMEASURED, and therefore neither refuted nor supported: the "
    "mobile client, the desktop app client, wiki-wrapped documents (`…/wiki/<node>`, which "
    "this function refuses rather than guess at), and any other tenant. Whether a link "
    "scrolls is a rendering behavior of the Lark client, so no API call can widen this "
    "measurement — only another click can."
)

#: Docx **named-edition** (`?edition_id=`) links are mintable, and the construction is now
#: **clicked** — LD-419 landed the 2026-08-11 click that settled the query half, so the
#: constant's old name (`…_CLICK_UNVERIFIED`) was renamed to match its body rather than
#: contradict it. The disclosure's job is unchanged (the supersession rule: preserve the reason, supersede only
#: the conclusion): keep the claim scoped to what was observed on, which is now one client on
#: one tenant on one day, with every other axis still named as unmeasured. Authored ONCE here;
#: quoted verbatim into the function's docstring, the shipped guide and the release notes.
DOCX_EDITION_LINK_CLICK_MEASUREMENT = (
    "A docx named-edition link (`…/docx/<doc>?edition_id=<version token>`) is mintable "
    "offline — `docx_edition_url(doc_url, version_token)` builds one from the document's own "
    "URL and a version token, and makes zero API calls — and it ships "
    "click-verified — the `?edition_id=` grammar was clicked on 2026-08-11 in the Lark WEB "
    "client, on one tenant, and it opened the named version. "
    "Here is the edge of the evidence, so the claim is never read wider than what was "
    "measured. The click was made against a harness-created two-paragraph document whose two "
    "states were proven to differ AT THE API LEVEL first — a read pinned at the version's "
    "recorded revision returned the first paragraph only, while a head read taken in the same "
    "sitting returned both — so a browser showing one state could not be an accident of the "
    "fixture. What was seen: through the edition URL the document showed STATE ONE only, and "
    "Lark's own UI labelled that view an older version; through the control URL (the plain "
    "document URL, unmodified) it showed both paragraphs, head. MEASURED: the QUERY half, by "
    "that click; and the PATH half, `https://<tenant host>/docx/<doc token>`, which is "
    "the document's URL as Lark itself reports it (the drive metas/batch_query verb asked "
    "`with_url: true`, 2026-08-11), and it is character-for-character the grammar "
    "`docx_block_url` already mints; the version token is Lark's own, returned by the "
    "versions family. UNMEASURED, and therefore neither refuted nor supported: the mobile "
    "client, the desktop app client, wiki-wrapped documents (`…/wiki/<node>`, which this "
    "function refuses rather than guess at), any other tenant, and any non-web client. "
    "Whether such a link opens the named version is a rendering behavior of the Lark client, "
    "so no API call can widen this measurement — only another click can. Separately, and "
    "unchanged by the click: no API route resolves an edition token to CONTENT — the versions "
    "family answers no url of any kind, and an edition token resolves to nothing — so keep "
    "recording the (name, token, revision) triple at creation time, because that pairing is "
    "what a pinned historical read actually runs on."
)

#: Base **table / view / record** query links ARE mintable — with the edge of the evidence
#: stated, because a positive capability claim is owed the same enumeration as a negative one.
#: Authored ONCE here (beside the three docx/sheets disclosures, so a reader comparing the
#: strength of four claims finds them in one place); quoted verbatim into
#: :mod:`larkdocio.base.deep_link`'s two functions, the shipped guide and the release notes.
BASE_DEEP_LINK_CLICK_MEASUREMENT = (
    "A Base table/view deep link (`…/base/<app_token>?table=<table_id>&view=<view_id>`, and "
    "with a record `&record=<record_id>`) IS mintable, offline: "
    "`larkdocio.base.table_url(base_url, table_id)` and "
    "`larkdocio.base.view_url(base_url, table_id, view_id)` build one from the Base's own URL "
    "and ids a Base read already returns, and make zero API calls. Here is the edge of the "
    "evidence, so the claim is never read wider than what was measured. MEASURED: the grammar "
    "was clicked by hand on 2026-08-17 in the Lark web client, on one tenant, on one Base. "
    "The navigating click was made against a NON-FIRST table, and that detail is the "
    "measurement rather than a footnote — on that Base's first table the target view is its "
    "only view, so a correct navigation and a default landing are indistinguishable, and an "
    "earlier click against exactly that target was read as \"does not navigate\" and was a "
    "false negative. Against the non-first table the Base opened directly on the named table "
    "and view. A second click carried `&record=<record_id>` and the record card opened. The "
    "ids those links were built from were checked alive and byte-identical ten days after "
    "they were first read — tables listed, views listed, the record fetched — so no id had "
    "been re-minted underneath the reading. UNMEASURED, and therefore neither refuted nor "
    "supported: the mobile client, the desktop app client, any other tenant, any other Base, "
    "and any span longer than those ten days. Whether such a link navigates is a rendering "
    "behaviour of the Lark client, so no API call can widen this measurement — only another "
    "click can. FOR A RECORD, PREFER `larkdocio.base.record_permalink`: that address is "
    "minted by Lark itself rather than composed here, and it was measured byte-identical "
    "across a week (read 2026-08-07/08, re-read 2026-08-15). A constructed `record=` link is "
    "the answer for the ids you already hold, not the better address."
)

#: Sheets **cell/range** links are UI-only, and guessing one is HAZARDOUS — with the toast quoted.
SHEETS_CELL_LINK_UI_ONLY = (
    "A sheets cell or range link is UI-only, and guessing one is hazardous. The `rangeId` in "
    "`…?sheet=<id>&rangeId=<id>_<opaque>&rangeVer=<n>` is opaque and versioned — a stored "
    "server-side object, not a computed address — and no endpoint in the Sheets surface "
    "mints, lists or resolves one. The obvious workaround makes it worse: a guessed "
    "`range=<A1>` URL half-works. It lands on the right tab and then shows a toast reading "
    '"The cell was deleted" about cells that are perfectly intact — identically for any '
    "coordinate, stably across refreshes. Do not build such a URL: a reader who sees that "
    "toast will file a data-loss bug against your sheet or against this library. This is not "
    "a permissions problem: the data does not exist in the API at all, so no grant would "
    "change either answer. Tab-level links ARE mintable — see `larkdocio.sheets.tab_url` — "
    "but cell-level ones are not. "
    "WHAT THIS IS AND IS NOT ABOUT: it is about a URL that POINTS AT a cell, and it is not "
    "about putting a link INSIDE one. Writing a cell whose value is a labeled clickable link "
    "SHIPS and works — `RichCellWriteRequest.hyperlink(range, link, text=…)`, worked through "
    "in the guide's section `Recipe: write a hyperlink and a styled run into a cell`. "
    "This paragraph is easy to misread as a verdict on that question, so the two are "
    "separated here rather than left adjacent."
)


# The Base measurement is authored once above and quoted verbatim into the parse's own
# docstring (a docstring must be a literal, so the quotation is spliced in after the def).
# The parse meets the question directly: a reader who sees a Base ?table=&view= url answered
# NotADeepLink is owed the reason that is true TODAY, not the one that was true when the
# grammar had never been clicked.
parse_deep_link.__doc__ = (parse_deep_link.__doc__ or "").replace(
    "<<BASE_DEEP_LINK_MEASUREMENT>>", BASE_DEEP_LINK_CLICK_MEASUREMENT
)
