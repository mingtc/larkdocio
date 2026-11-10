"""larkdocio.base.read — the PUBLIC Base read surface (LD-248).

The first point at which a consumer can call larkdocio and get a Base back. Two entry
points, deliberately:

* :func:`read_base` returns the **structured intermediate** — field specs, record ids and
  rendered cells — so a consumer is not forced through a string to reach the data;
* :func:`read_base_markdown` returns the **Markdown**, for the reading form.

Both take **either a Base URL or a bare ``app_token``**, and the difference is resolved by
:func:`resolve_base` rather than guessed further in.

**A Base URL's slug IS its ``app_token`` — verified here, not inherited.** An earlier
warning held that the slug "is not necessarily the ``app_token``", because the
``.env`` Scratch-Base URL's slug and the token the captures use differ. That difference was
**two different Bases**, not a slug/token mismatch (open item O3, resolved 2026-08-03). The
claim is therefore re-checked on its own merits and holds: the slug in the committed
``.env.example`` URL is byte-identical to the ``app_token`` that same Base's own
``GET …/apps/{app_token}`` capture reports, and the shipped live read arm reaches the real
Base with a token derived from exactly that URL. So resolving a URL is sound, and the
docstrings say plainly which form each entry point takes.

**Recognising a URL is not the same as it naming a Base.** A ``sheets`` or ``docx`` URL
parses fine and is still refused here, by name — handing a docx token to the Base client
would fail later and vaguer.

**Five reads per Base, and not one more.** App meta once (for the ``time_zone`` every date
cell is rendered in), the table list once, then fields and records per table. Views are
**not** listed: a view is not a projection (``view_id`` is not a column selector and
``hidden_fields`` has no API effect), so listing them would be a per-table API call bought
for nothing.

**READ credentials only.** The client resolves the read pair through
:mod:`larkdocio.common.auth`; the write pair is never consulted, and no write string
appears anywhere in this package.
"""
import re
from typing import Optional, Tuple

from larkdocio.base.cells import RenderContext
from larkdocio.base.table import (
    BaseRead,
    DEFAULT_HEADING_LEVEL,
    assemble_base,
    assemble_table,
    render_base,
)
from larkdocio.common.url import validate_download_url
from larkdocio.errors import LarkConfigError

#: The character set a Lark token is drawn from — the same one the URL validator's own
#: pattern accepts, so "a bare token" means exactly "what a URL could have carried".
_TOKEN = re.compile(r"^[A-Za-z0-9]+$")


def resolve_base(base: str) -> Tuple[Optional[str], str]:
    """A Base URL **or** a bare ``app_token`` → ``(api_domain_or_None, app_token)``.

    A URL is parsed by the shared :func:`~larkdocio.common.url.validate_download_url`, which
    has recognised ``/base/`` as a URL type since well before this surface existed — so it
    cannot drift from
    what the library accepts elsewhere. The returned ``domain`` is the **API** domain
    (``larksuite.com`` | ``feishu.cn``), not the tenant host in the URL.

    A bare token carries no domain, so ``None`` is returned and the caller's default stands.
    Anything that is neither — a blank, a URL naming another surface, a string with a slash
    or a space — is refused here rather than sent to Lark to fail vaguer.
    """
    if not isinstance(base, str) or not base.strip():
        raise LarkConfigError(
            "Cannot read a Base: pass a Base URL "
            "(https://<host>/base/<app_token>) or a bare app_token")
    candidate = base.strip()
    if candidate.lower().startswith(("http://", "https://")):
        domain, url_type, token = validate_download_url(candidate)
        if url_type != "base":
            raise LarkConfigError(
                f"Not a Lark Base URL (recognised as {url_type!r}): {candidate!r}. "
                "Recognising a URL is not the same as it naming a Base — a "
                f"{url_type!r} url is read through its own surface.")
        return domain, token
    if not _TOKEN.match(candidate):
        raise LarkConfigError(
            f"Not a Base app_token: {candidate!r}. Pass a Base URL "
            "(https://<host>/base/<app_token>) or the bare app_token.")
    return None, candidate


def read_base(
    base: str,
    *,
    client=None,
    domain: str = "larksuite.com",
    resolve_links: bool = False,
    retain_raw: bool = False,
) -> BaseRead:
    """Read a whole Base and return the **structured intermediate**.

    ``base`` is **either a Base URL or a bare ``app_token``** (:func:`resolve_base`); a URL
    also supplies the API domain, which then overrides ``domain``. ``client`` is injectable
    — the default is a :class:`~larkdocio.base.client.BaseReadClient` built from the
    environment's READ credentials.

    What comes back is a :class:`~larkdocio.base.table.BaseRead`: the app's name and
    ``time_zone``, then one :class:`~larkdocio.base.table.BaseTableRead` per table in
    ``GET …/tables`` order, each carrying its field specs and its rows. Every row is exactly
    as wide as the field list, because rows project against the **fields**, never against
    the keys a record happens to carry. Pass the result to
    :func:`~larkdocio.base.table.render_base` for Markdown, or read it directly.

    **Each table carries the ``revision`` it was read at, at no extra call.** The number rides
    the ``GET …/tables`` reply this read already receives, so exposing it costs nothing — it is
    the same field the write engine uses as its compare-and-swap anchor. What it means is on
    :class:`~larkdocio.base.table.BaseTableRead`, and a consumer building a change-detection
    ledger should read that first: it is **per-table isolated** (the app revision does not
    move), it is an **op counter rather than a row counter**, **``0`` is a real value** while
    ``None`` means *not known*, and there is **no ``If-Match``** — the anchor is an
    observation, so any guard on it is client-side read-compare-write. A Base with no tables,
    or a change that moves no table's counter, leaves a ledger nothing to compare.

    **A view is not a projection, so this surface takes no ``view_id``.** ``view_id`` is
    **not a column selector**: a view with fields hidden still returns every field in
    unscoped order, and the records read under it returns the same field keys per row. L1
    renders the **table's** schema. The only genuine server-side projection is
    ``field_names``, which L1 does not expose either.

    **``resolve_links`` is OFF by default, and off means byte-identical.** With it absent this
    function makes the same five reads it always made and a link cell renders the linked
    record **ids**, exactly as before. Switched on, it follows every link to its target and
    renders each linked record as its target table's **schema-designated primary field** —
    which costs extra reads, batched per **target table** and never per cell, and is disclosed
    on the result as :attr:`~larkdocio.base.table.BaseRead.link_resolution` (how many calls,
    which tables, and the typed per-id outcome). A link whose target record was deleted is a
    **normal** case with a typed marker, not an error: see
    :mod:`larkdocio.base.link_resolution`. Two resolutions in the **same run** are
    byte-identical; a target renamed between runs legitimately changes the output.

    **``retain_raw`` is OFF by default, and off is byte-identical too.** Every value this
    function returns is otherwise *display-shaped*: a Date arrives as an epoch and leaves as
    ``2025/07/01``, an Email leaves as ``[you@example.com](mailto:you@example.com)``, a Person
    leaves as a comma-joined display name — perfect for reading, wrong for comparing, and the
    reason a consumer who wants to dedupe, diff or chart has to re-derive from the wire.
    Switched on, each row also carries
    :attr:`~larkdocio.base.table.BaseRow.raw_fields`: the record's ``fields`` body **exactly
    as Lark returned it**, no key renamed, no absence coerced, no type changed — and
    :func:`~larkdocio.base.model.snapshot_table` carries it through to
    :meth:`~larkdocio.base.model.SnapshotRecord.raw`. It is **not** a normalized typed middle
    form: there is no ``datetime``, no ``Decimal`` and no person class anywhere behind it, and
    a caller who wants one builds it from the epoch this hands over, with their own timezone
    opinion. **It costs no extra call** — the payload is already received, and the flag only
    decides whether it is kept — **but it does cost memory, and the number is measured, not
    hand-waved: ≈7× the rendered cells** (≈260 KB against ≈38 KB for a 64-row read of a real
    four-column table; both forms are kept, and the wire body is by far the larger, because a
    Lookup or Person cell that renders as a short name arrives as a nested structure).
    Retention is per read: drop the read and it is gone.

    Read-only, and paced: every call passes the client's shared limiter.
    """
    url_domain, app_token = resolve_base(base)
    if client is None:
        from larkdocio.base.client import BaseReadClient

        client = BaseReadClient.from_read_credentials(url_domain or domain)

    app = client.get_app(app_token)
    time_zone = getattr(app, "time_zone", None)
    context = RenderContext(time_zone=time_zone)
    # Fetched before anything is rendered, because resolution needs the RAW cells: a rendered
    # cell is a string, and a string cannot be followed to its target.
    # ``revision`` rides this same reply, read defensively exactly as the write engine's own
    # compare-and-swap anchor is (`base/apply.py`): absent means None — "not known" — never 0.
    raw = [
        (table.table_id, table.name,
         client.list_fields(app_token, table.table_id),
         client.search_records(app_token, table.table_id),
         getattr(table, "revision", None))
        for table in (client.list_tables(app_token) or ())
    ]

    resolution = None
    if resolve_links:
        from larkdocio.base.link_resolution import resolve_links as _resolve
        from larkdocio.base.table import field_spec

        schemas = {table_id: [field_spec(f) for f in fields]
                   for table_id, _name, fields, _records, _revision in raw}
        resolution = _resolve(
            client=client,
            app_token=app_token,
            sources=[(table_id, schemas[table_id], records)
                     for table_id, _name, _fields, records, _revision in raw],
            # Every table of THIS Base is already read, so a link that stays inside it costs
            # no schema call at all — the resolver spends its budget on records.
            known_schemas=schemas,
            context=context,
        )
        context = RenderContext(time_zone=time_zone, links=resolution)

    tables = [
        assemble_table(table_id=table_id, name=name, fields=fields, records=records,
                       context=context, retain_raw=retain_raw, revision=revision)
        for table_id, name, fields, records, revision in raw
    ]
    return assemble_base(
        app_token=getattr(app, "app_token", None) or app_token,
        name=getattr(app, "name", "") or "",
        time_zone=time_zone,
        tables=tables,
        link_resolution=resolution,
    )


def read_base_markdown(
    base: str,
    *,
    client=None,
    domain: str = "larksuite.com",
    heading_level: int = DEFAULT_HEADING_LEVEL,
    resolve_links: bool = False,
) -> str:
    """Read a whole Base and return **Markdown** — one ``##`` heading and one GFM table per
    Base table, in ``GET …/tables`` order.

    ``base`` is **either a Base URL or a bare ``app_token``**, exactly as for
    :func:`read_base`; this is that function plus
    :func:`~larkdocio.base.table.render_base`, and nothing else. Use :func:`read_base` when
    you want the data rather than the reading form — the Markdown can always be produced
    from it later without a second network read.

    ``resolve_links`` is passed straight through and is **off by default**; note that the
    Markdown form drops the resolution's **cost disclosure** with everything else structured,
    so a caller who wants to see what the extra reads cost should take :func:`read_base`.

    **The per-table ``revision`` is deliberately NOT in the Markdown either.** A version is a
    fact about the read, not a line of the document, and printing it would move bytes every
    consumer's diff already depends on. Take :func:`read_base` for the version — each
    :class:`~larkdocio.base.table.BaseTableRead` carries its own ``revision``, and that class's
    docstring says what the number means.

    **There is deliberately no ``retain_raw`` here.** Markdown *is* the display form, so
    retaining the wire values behind a string that has already discarded them would be memory
    bought for something no caller of this function can reach. Take :func:`read_base` for the
    raw view.
    """
    return render_base(
        read_base(base, client=client, domain=domain, resolve_links=resolve_links),
        heading_level,
    )
