"""larkdocio.base.client — the throttled, typed Base read client.

The cell renderers turn a payload into Markdown; this is what feeds them. One transport, one throttle, one error taxonomy,
pagination that runs to exhaustion, and ``POST …/records/search`` pinned as *the* record read.

**The transport is SDK-typed, with a RAW fallback only where an SDK gap is actually
hit.** ``lark_oapi.api.bitable.v1`` is already in the pinned SDK — no new dependency
(CLAUDE.md § House rules, in the dev repo) — and it ships typed request builders and response models for all
five reads this client makes. **No gap was hit, so there is no raw path here at all**, and
none is pre-declared: the rule is that a raw leg must be *justified by a gap
actually encountered*, recorded with the specific shortfall that forced it. There is nothing
to record, which is the honest state, and the guard scans this package for raw-HTTP
constructs so it stays that way until something genuinely forces the issue.

**How a committed capture becomes a fixture.** The probe packs saved Lark's raw JSON
(``tests/captures/base-study/captures/``, in the source repository). The offline suite feeds that JSON back
through the **SDK's own deserializer** (``JSON.unmarshal(payload, SomeResponse)``) and hands
the resulting typed object to an injected transport. So the tests exercise the same objects a live call produces,
and an API drift — a renamed key, a changed nesting — reddens **at deserialization** rather
than travelling on as a plausible-looking ``None`` (PROJECT.md § Quality bar, in the dev repo:
fixtures pin real payload shapes).

**Two traps, both pinned by tests, both cheap to get wrong.**

1. **``page_size`` is a QUERY-STRING parameter.** In the query it works as documented; in the
   **body it is silently ignored** and the server returns the whole page-1 set — ``code:0``
   either way (parity § Verdict, ``p1-q1-01``). The SDK's typed builder puts it in the query,
   which is precisely why the typed builder is not a style preference.
2. **``records/search`` silently ignores every body key it does not recognise** (R12): the
   bogus key ``{"zzz": 1}`` and four plausible grouping keys all behave identically to ``{}``.
   So *"it returned code:0"* proves nothing about whether a parameter was honoured. Two
   consequences are built into this client. **By construction:** every request is built from
   the SDK's typed builders, never a hand-assembled dict, so a key cannot be silently
   misplaced. **By restraint:** a parameter whose effect no test can demonstrate is a
   parameter that does not ship. Every one that does ship arrived with its demonstration:
   ``page_size`` and ``page_token`` in the query and ``automatic_fields: false`` in the body
   are the unconditional three, and the three **narrowing** body keys ``search_records``
   accepts — ``filter``, ``view_id``, ``sort`` — each landed with a **differential** live
   proof (a filtered read compared against an unfiltered read of the same table in the same
   run, with an R12 control beside it), never with a ``code:0``. That is the bar for widening
   this client, and it did not move: it is the reason ``field_names``, grouping and the rest
   below are still absent.

**What is deliberately NOT sent, and why.**

* ``text_field_as_array`` — no observable effect on ``search`` (which is always array-shaped);
  the flag belongs to the legacy ``GET …/records``.
* ``user_id_type`` — this surface renders person fields **name-only**, so the id form is
  unobservable in the output and no test could prove the parameter changed anything.
* ``field_names`` — the server-side projection is real but **name-keyed**: a ``field_id`` is a
  hard ``1254045``. L1 does not expose it (a full read already returns every column, and every
  unexposed parameter is one fewer silent-ignore surface). The refusal stays in the taxonomy so
  a caller who meets it elsewhere gets a legible answer.
* ``filter`` / ``sort`` / ``view_id`` — **these three now ship**, on ``search_records`` and
  nowhere else, each keyword-only and each defaulting to *absent* so the render path's read is
  byte-identical to what it always sent. What made them shippable was not that they are real
  (they always were) but that their effects are **observable differentially**; ``view_id`` does
  not combine with the other two, because how a saved filter composes with a request one is
  not. **Grouping is still not expressible at all** — ``records/search`` swallows all four
  plausible grouping keys exactly as it swallows ``{"zzz": 1}`` — and must never be offered.

**``records/search`` is THE read.** The legacy ``GET …/records`` list is not used. The four
read endpoints return **three different encodings** of the same data — the legacy GET returns
``Formula: 2`` bare and duplicates the id as both ``id`` and ``record_id``, ``search`` returns
``Formula: {"type":2,"value":[2]}`` and only ``record_id``, and the create echo adds a third
shape — so pinning a fixture to the wrong route rots it silently (opener R7).

**Be gentle.** Every call passes the shared :class:`~larkdocio.common.transport.RateLimiter`
first, at the spacing the three probe packs actually ran: **483 live calls at ≥1.2 s with no
limit hit** (opener 96 + P0 197 + parity 190). Rate limits were **deliberately not probed**
(opener R9) and are not probed here — the posture is documented from that evidence, the way
the Sheets tier is documented, and there is no retry-on-``99991400`` loop in this module
because that would be a probe by another name.

**READ credentials only.** The pair is resolved through :mod:`larkdocio.common.auth`; the
``LARK_WRITE_APP_*`` pair is never consulted and is not named anywhere in this package.
Binding rider from PROJECT.md § Credential aliasing (in the dev repo): on the tenant these
measurements were made on, the READ and WRITE pairs **named one app**, so the code keeps treating them as distinct and
**no same-tenant probe here may be cited as proof of scope separation** — that claim needs a
genuinely separate app.
"""

# The transport ruling this module is under is D2 (SDK-typed; a raw leg only
# where an SDK gap is actually hit, recorded with the shortfall that forced it). The
# rule itself is stated in the docstring above in plain language: a consumer reads that
# text through help(), and an internal decision id resolves to nothing for them.
from typing import List, Optional, Sequence

from lark_oapi.api.bitable.v1 import (
    App,
    AppTable,
    AppTableField,
    AppTableRecord,
    AppTableView,
    BatchGetAppTableRecordRequest,
    BatchGetAppTableRecordRequestBody,
    ChildrenFilter,
    Condition as SdkCondition,
    FilterInfo as SdkFilterInfo,
    GetAppRequest,
    ListAppTableFieldRequest,
    ListAppTableRequest,
    GetAppTableViewRequest,
    ListAppTableViewRequest,
    SearchAppTableRecordRequest,
    SearchAppTableRecordRequestBody,
    Sort as SdkSort,
)

from larkdocio.base.errors import raise_for_base_code
from larkdocio.base.view_filters import BaseFilterRefusal, SearchFilter, SortKey
from larkdocio.common.auth import get_read_credentials, resolved_read_env
from larkdocio.common.sdk_client import (
    require_credentials,
    resolve_rate_limiter,
    resolve_sdk_client,
)
from larkdocio.errors import LarkConfigError

#: The window the pace is expressed over: one minute.
BASE_RATE_WINDOW_SECONDS = 60.0

#: Client-side cap per :data:`BASE_RATE_WINDOW_SECONDS`. 50/minute is a **1.2 s** spacing —
#: exactly the pace the three probe packs sustained across 483 live calls without meeting a
#: limit. A number measured in this repository's own evidence, not one read off a doc page and
#: not one anybody walked into.
DEFAULT_MAX_READS_PER_WINDOW = 50

#: Page size requested on every paged read, in the **query string** where it is honoured.
#: Inside the documented ceiling of every endpoint here, and large enough that an ordinary
#: table is one or two pages.
DEFAULT_PAGE_SIZE = 100

#: Hard stop on a single walk. The ordinary guards (no cursor, or a repeated cursor) end a
#: walk long before this; this is the backstop for a server handing back an endless chain of
#: fresh cursors.
MAX_PAGES = 200

#: ``automatic_fields`` is pinned **false**. It adds record-level ``created_by`` /
#: ``last_modified_by`` person objects (personal data) and changes nothing inside
#: ``fields``, so it costs a privacy surface and buys the render nothing.
AUTOMATIC_FIELDS = False

#: How many record ids one ``records/batch_get`` call may carry. This is Lark's **documented**
#: ceiling for the endpoint, and it is deliberately **not probed** — the standing posture is
#: that a limit is documented from published evidence rather than discovered by walking into
#: it (opener R9, the LD-100 precedent). A caller asking for more than this is refused
#: **locally, before any call**, because the alternative is to discover the ceiling on the
#: wire; the batching caller chunks to it instead.
BATCH_GET_MAX_IDS = 100

#: **What an EMPTY ask really does, measured live (2026-08-04) rather than assumed.**
#: ``records/batch_get`` with ``record_ids: []`` is **refused** ``99992402 field validation
#: failed``, and the body's ``field_violations`` name the offending field and the rule in
#: Lark's own words: *"record_ids (the min len is 1)"*. That matters beyond ergonomics. This
#: family's standing hazard (R12) is that ``records/search`` **silently ignores** a body key it
#: does not recognise, so a ``code:0`` proves nothing about whether a parameter was honoured —
#: and here there is **no parameter-free control to compare against**, because the endpoint
#: *validates* the key instead of swallowing it. That refusal is the strongest evidence the
#: parameter is real, so it is recorded and asserted by the live arm rather than designed
#: around: this client sends the empty ask through and lets **Lark's own answer** reach the
#: caller, which is more specific and more actionable than any local message would be.
BATCH_GET_EMPTY_ASK_REFUSED_CODE = 99992402

def _search_condition(condition: dict) -> SdkCondition:
    builder = SdkCondition.builder() \
        .field_name(condition["field_name"]) \
        .operator(condition["operator"])
    if "value" in condition:
        builder = builder.value(list(condition["value"]))
    return builder.build()


def _search_filter_info(body: dict) -> SdkFilterInfo:
    """A serialised :class:`~larkdocio.base.view_filters.SearchFilter` as the SDK's **own** typed
    ``FilterInfo`` — rebuilt through the typed builders, key by key, never handed over as a dict.

    That is the module's by-construction R12 defence applied to the widest body key this client
    sends: a key the SDK has no builder for cannot be spelled here at all, so the one class of
    mistake R12 makes invisible — a plausible key in the wrong place, answered ``code:0`` — has
    no way in.

    **One level of nesting, because one level is what is captured.** ``p1-q3-01`` step 24 sent
    ``children`` one deep and got the right single row back; nothing sent two. The SDK agrees by
    accident of its own shape — ``ChildrenFilter`` has no ``children`` field — so a deeper tree
    would have to be hand-assembled to travel at all, and it is refused instead.
    """
    builder = SdkFilterInfo.builder().conjunction(body["conjunction"])
    builder = builder.conditions([_search_condition(c) for c in body.get("conditions", ())])
    children = body.get("children") or ()
    if children:
        for child in children:
            if child.get("children"):
                raise BaseFilterRefusal(
                    "a filter nested more than ONE level deep is refused: `children` is proven "
                    "one deep on records/search (p1-q3-01 step 24) and no capture nests twice, "
                    "and the SDK's own ChildrenFilter has no `children` field — so sending it "
                    "would mean hand-assembling the body this client never hand-assembles. "
                    "Flatten the inner group. Nothing was sent.")
        builder = builder.children([
            ChildrenFilter.builder()
            .conjunction(child["conjunction"])
            .conditions([_search_condition(c) for c in child.get("conditions", ())])
            .build()
            for child in children])
    return builder.build()


def _checked_search_filter(value) -> SearchFilter:
    if isinstance(value, SearchFilter):
        return value
    from larkdocio.base.view_filters import FilterSpec, ViewFilterInfo

    if isinstance(value, ViewFilterInfo):
        raise BaseFilterRefusal(
            "that is the VIEW dialect — the `field_id`-keyed body for PATCH …/views/{view_id}, "
            "which filters the rows a person sees. A read is filtered by the SEARCH dialect, "
            "which is `field_name`-keyed: build it with "
            "larkdocio.base.view_filters.search_filter(spec) from the same FilterSpec. "
            "Nothing was sent.")
    if isinstance(value, FilterSpec):
        raise BaseFilterRefusal(
            "a FilterSpec describes a filter without saying which of the two dialects it is "
            "for, and this client will not choose for you — the choice is between keying by "
            "`field_name` and by `field_id`. Run search_filter(spec) and pass the result. "
            "Nothing was sent.")
    raise BaseFilterRefusal(
        f"a read filter is a larkdocio.base.view_filters.SearchFilter — the token-sealed product "
        f"of search_filter(spec); got {type(value).__name__}. A correct-LOOKING mapping is still "
        "refused: the seal is what says the operator, the value encoding and the conjunction "
        "were all checked. Nothing was sent.")


def _checked_sort(value) -> List[SortKey]:
    keys = list(value)
    if not keys:
        raise BaseFilterRefusal(
            "an empty sort is refused rather than sent: on this route it is a no-op body key, "
            "and a no-op that looks like an instruction is exactly what R12 makes unreadable. "
            "Pass sort=None for an unsorted read. Nothing was sent.")
    for key in keys:
        if not isinstance(key, SortKey):
            raise BaseFilterRefusal(
                f"a sort key is a larkdocio.base.view_filters.SortKey; got "
                f"{type(key).__name__}. Nothing was sent.")
    return keys


class BaseReadClient:
    """Reads a Base: its app meta, its tables, and per table its views, fields and records.

    ``sdk_client`` and ``rate_limiter`` are injectable so request construction, pacing,
    pagination and error typing are all testable without a network — the
    :class:`~larkdocio.comments.client.CommentsReadClient` shape. The defaults are a real SDK
    client built from the supplied credentials and a limiter at
    :data:`DEFAULT_MAX_READS_PER_WINDOW` per :data:`BASE_RATE_WINDOW_SECONDS`.
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        domain: str = "larksuite.com",
        *,
        sdk_client=None,
        rate_limiter=None,
        page_size: int = DEFAULT_PAGE_SIZE,
        timeout: int = 30,
    ):
        self._domain = domain
        self._page_size = page_size
        self._api_calls = 0
        self._limiter = resolve_rate_limiter(
            rate_limiter, DEFAULT_MAX_READS_PER_WINDOW, BASE_RATE_WINDOW_SECONDS)
        self._sdk = resolve_sdk_client(
            sdk_client, app_id, app_secret, domain, timeout=timeout,
            no_credentials="Cannot read a Base: no credentials were resolved")

    @classmethod
    def from_read_credentials(cls, domain: str = "larksuite.com", **kwargs):
        """Build from the environment's READ credentials. A Base read is a read; the write
        pair is never consulted here."""
        app_id, app_secret = get_read_credentials()
        require_credentials(
            app_id, app_secret,
            "Cannot read a Base: no read credentials in the environment")
        return cls(app_id, app_secret, domain, **kwargs)

    # ---- pacing ----------------------------------------------------------- #

    @property
    def limiter(self):
        """The limiter every call on this client passes through."""
        return self._limiter

    @property
    def api_calls(self) -> int:
        """How many API calls this client has made. Incremented in exactly one place, so it
        counts real requests rather than intentions."""
        return self._api_calls

    def _paced(self, call, request):
        """Acquire a slot, then make exactly one API call. Every call in this module goes
        through here, so no op can be added that bypasses the pace."""
        self._limiter.acquire()
        self._api_calls += 1
        return call(request)

    def _checked(self, call, request, context):
        return raise_for_base_code(self._paced(call, request), context=context,
                                   credential_env=resolved_read_env())

    # ---- the paged walk --------------------------------------------------- #

    def _walk_pages(self, fetch_page) -> List:
        """Follow a cursor-paged endpoint to **exhaustion** — "the first page" is never "the
        table" — and stop under every shape of answer that would otherwise not terminate.

        The named hazard this exists for: a freshly created Base's default table ships with
        **10 auto-provisioned empty rows**, so a first-page-only read of a populated table can
        return nothing but those empties and read as "no data". The opener's own probe 05 was
        fooled by exactly that before probe 06 corrected it.

        The walk ends when the body says there is no more, when it claims more but hands back
        no usable cursor, when it hands back a cursor already used (which would replay the same
        page forever), or at :data:`MAX_PAGES`.

        *(Base-local rather than lifted into ``common/``: the comments client's walk is the
        same idea, but it is a private method on a shipped read client and moving it would make
        a feature story a refactor of that surface — the LD-246 posture, restated. A shared
        cursor walker is a worthwhile follow-up, not a rung of this story.)*
        """
        items: List = []
        bodies: List = []
        token: Optional[str] = None
        seen = set()
        self._pages = ()
        try:
            for _ in range(MAX_PAGES):
                body = fetch_page(token)
                bodies.append(body)
                items.extend(getattr(body, "items", None) or ())
                if not getattr(body, "has_more", None):
                    return items
                token = getattr(body, "page_token", None)
                if not token or token in seen:
                    # "There is more" with nothing to ask for next, or with the cursor we just
                    # used: believe the cursor, not the flag, and stop.
                    return items
                seen.add(token)
            return items
        finally:
            self._pages = tuple(bodies)

    @property
    def last_walk_pages(self) -> tuple:
        """The page bodies the **most recent** cursor walk on this client actually saw.

        The walk above stops under four shapes and only one of them is exhaustion, so "how many
        rows came back" cannot answer "did I see the whole table". This publishes the record
        that can: :meth:`larkdocio.base.model.ReadProof.from_pages` classifies these bodies, and
        the destructive rung's cross-table scan **refuses** a delete whose scan cannot be shown
        to have run to the end (:mod:`larkdocio.base.loss_preview`). Nothing on the read path
        consults it, and reading it costs no call.

        Only the last walk is kept, so the retention is bounded by one listing — and the bodies
        hold the very items the walk already returned to the caller.
        """
        return getattr(self, "_pages", ())

    # ---- the operations --------------------------------------------------- #

    def get_app(self, app_token: str) -> App:
        """The Base's own metadata — ``name``, ``revision``, ``is_advanced``, ``time_zone``.

        ``time_zone`` is load-bearing for rendering: every date cell is a pure function of
        ``(value, date_formatter, time_zone)``, and a docx-born embedded Base has none at all.

        **``None`` here is a real answer and not an error**: the key is absent from the **wire**
        — measured both raw and SDK-parsed, and they agree — for a Base born inside a docx and
        for any Base created without declaring a zone. What the read does about it is the one
        policy in :mod:`larkdocio.base.date_zone`: it renders in the assumed zone and
        **discloses** that on the result rather than presenting an unqualified date.
        """
        request = GetAppRequest.builder().app_token(app_token).build()
        response = self._checked(self._sdk.bitable.v1.app.get, request,
                                 f"read the Base {app_token}")
        return response.data.app

    def list_tables(self, app_token: str) -> List[AppTable]:
        """Every table in the Base, following the cursor to exhaustion."""
        def page(token):
            builder = ListAppTableRequest.builder() \
                .app_token(app_token) \
                .page_size(self._page_size)
            if token:
                builder = builder.page_token(token)
            return self._checked(self._sdk.bitable.v1.app_table.list, builder.build(),
                                 f"list the tables of {app_token}").data

        return self._walk_pages(page)

    def list_views(self, app_token: str, table_id: str) -> List[AppTableView]:
        """Every view on a table. Read for completeness of the schema picture — a view's
        hidden fields do **not** change what the API projects, so L1 renders the TABLE's
        schema, not a view's."""
        def page(token):
            builder = ListAppTableViewRequest.builder() \
                .app_token(app_token) \
                .table_id(table_id) \
                .page_size(self._page_size)
            if token:
                builder = builder.page_token(token)
            return self._checked(self._sdk.bitable.v1.app_table_view.list, builder.build(),
                                 f"list the views of table {table_id}").data

        return self._walk_pages(page)

    def get_view(self, app_token: str, table_id: str, view_id: str) -> AppTableView:
        """ONE view, **with its `property`** — which the listing above does not carry.

        Measured live (2026-08-04): the same view returns
        ``property.filter_info`` from ``GET …/views/{view_id}`` and has the ``property`` key
        **absent entirely** from ``GET …/views``. L1's rendering needs neither — it renders the
        table's schema, not a view's — but a view WRITE is verified by re-reading the view, and
        that verification is only possible through this endpoint. Nothing paged: one view, one
        call.
        """
        request = GetAppTableViewRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .view_id(view_id) \
            .build()
        response = self._checked(self._sdk.bitable.v1.app_table_view.get, request,
                                 f"read the view {view_id} of table {table_id}")
        return response.data.view

    def list_fields(self, app_token: str, table_id: str) -> List[AppTableField]:
        """Every field on a table, **in table order** — the projection a row is rendered
        against. An empty cell is an ABSENT KEY in ``search``, so the field list, never the
        union of a record's own keys, is what makes rows line up."""
        def page(token):
            builder = ListAppTableFieldRequest.builder() \
                .app_token(app_token) \
                .table_id(table_id) \
                .page_size(self._page_size)
            if token:
                builder = builder.page_token(token)
            return self._checked(self._sdk.bitable.v1.app_table_field.list, builder.build(),
                                 f"list the fields of table {table_id}").data

        return self._walk_pages(page)

    def search_records(self, app_token: str, table_id: str, *,
                       filter: Optional[SearchFilter] = None,
                       view_id: Optional[str] = None,
                       sort: Optional[Sequence[SortKey]] = None) -> List[AppTableRecord]:
        """Records from a table, via ``POST …/records/search`` — **the pinned read**.

        With no keyword the answer is the whole table and the body carries exactly one key,
        ``automatic_fields: false``. The three optional keywords are the **narrowing** ones, and
        they are one decision rather than three:

        * ``filter`` — a :class:`~larkdocio.base.view_filters.SearchFilter`, the token-sealed
          product of ``search_filter(spec)``. The **view** dialect
          (:class:`~larkdocio.base.view_filters.ViewFilterInfo`), a bare ``FilterSpec`` and a
          plain dict are each refused **before any call**, each saying which one to run;
        * ``view_id`` — read the rows **a saved view shows**, so a view filter written through
          this library can be read back through it;
        * ``sort`` — a sequence of :class:`~larkdocio.base.view_filters.SortKey`, applied in the
          order given. The field is named by its **human name**; a ``fld…`` id is ``1254016
          InvalidSort`` and is refused locally.

        **``view_id`` does not combine with ``filter`` or ``sort``.** How a view's saved filter
        composes with a request filter — intersect, override, ignore — is not shown by any
        capture this library holds, and this endpoint's family answers ``code:0`` to every
        reading. The combination is therefore refused with that reason rather than shipped on a
        guess. Filter *or* read a view; to narrow a view further, read it and filter in Python.

        **What travels, and how it is built.** ``filter`` / ``view_id`` / ``sort`` are **body**
        keys, assembled through the SDK's own typed builders key by key — never handed over as a
        dict — which is this module's by-construction defence against R12: ``records/search``
        silently ignores a body key it does not recognise, so a misplaced key would be
        ``code:0`` and invisible. For the same reason, none of these parameters shipped on a
        ``code:0``: each was proven **differentially** against an unfiltered read of the same
        table in the same run — a filtered read returning a strict subset, a match-nothing
        filter returning nothing rather than everything, a ``desc`` sort exactly reversing its
        ``asc``, and a ``view_id`` read agreeing with the filter its view has saved. Those
        proofs are two live arms in the source repository, ``tests/test_live_base_read_filter.py`` and
        ``tests/test_live_base_view_scoped_read.py``.

        **Across page boundaries.** A filtered read still walks to exhaustion, and the body is
        rebuilt inside the page closure, so ``filter`` / ``view_id`` / ``sort`` are **re-sent on
        every page**. ``page_size`` and ``page_token`` stay on the **query string** — where the
        server honours them — so ``has_more`` / ``page_token`` semantics are exactly the
        unfiltered ones, and :attr:`last_walk_pages` reports a filtered walk the same way it
        reports an unfiltered one: one entry per page body seen, which is what lets a caller
        show a filtered read ran to the end rather than stopping at page one.
        """
        if view_id is not None and (filter is not None or sort is not None):
            raise BaseFilterRefusal(
                "a `view_id` read and a request `filter`/`sort` are not combined by this "
                "client: how a view's SAVED filter composes with a request one is `uncaptured` "
                "— no capture in this library shows it, and records/search answers `code:0` to "
                "every reading, so a guess here would be indistinguishable from being ignored. "
                "Read the view, then narrow in Python, or filter the table directly. "
                "Nothing was sent.")
        filter_info = _search_filter_info(_checked_search_filter(filter).to_dict()) \
            if filter is not None else None
        sort_keys = _checked_sort(sort) if sort is not None else None

        def page(token):
            body_builder = SearchAppTableRecordRequestBody.builder() \
                .automatic_fields(AUTOMATIC_FIELDS)
            if filter_info is not None:
                body_builder = body_builder.filter(filter_info)
            if view_id is not None:
                body_builder = body_builder.view_id(view_id)
            if sort_keys is not None:
                body_builder = body_builder.sort([
                    SdkSort.builder().field_name(key.field.name).desc(key.desc).build()
                    for key in sort_keys])
            builder = SearchAppTableRecordRequest.builder() \
                .app_token(app_token) \
                .table_id(table_id) \
                .page_size(self._page_size) \
                .request_body(body_builder.build())
            if token:
                builder = builder.page_token(token)
            return self._checked(self._sdk.bitable.v1.app_table_record.search, builder.build(),
                                 f"read the records of table {table_id}").data

        return self._walk_pages(page)

    def batch_get_records(self, app_token: str, table_id: str, record_ids,
                          *, with_shared_url: bool = False):
        """**Named** records from one table, via ``POST …/records/batch_get`` — the SECOND
        POST read on this client, and the one link resolution spends its budget on.

        The answer is the SDK's own response body, which carries **three** lists and not one:
        the ``records`` that came back, the ``absent_record_ids`` Lark could not find, and the
        ``forbidden_record_ids`` it would not hand over (``03-records-batch-get.json``). The
        middle one is why a resolver need not treat a missing record as an error at all — the
        endpoint reports the absence *per id*, inside a ``code:0`` body.

        **The body carries what the caller asked for, and nothing else.** ``records/batch_get``
        is a POST read and sits in the same family as the R12 trap the module docstring names:
        an unrecognised body key is not refused, it is ignored, so a ``code:0`` proves nothing
        about whether a parameter was honoured. The restraint is the defence — the **default
        call sends ``record_ids`` and no other key**, byte-for-byte what it always sent
        (``user_id_type`` and ``automatic_fields`` stay absent: a person id form is
        unobservable in a name-only render, and the automatic fields are record-level personal
        data the render does not use).

        **``with_shared_url`` is the ONE key that rides on request — and only on request.** It
        defaults ``False`` and, off, is not sent at all, so the render path's read is
        byte-identical to what it always sent. On, the body adds ``with_shared_url: true`` and
        each returned record carries a **stable per-record permalink**. **Which field it lands
        in was MEASURED, not assumed:** on this batch route the permalink arrives under
        ``shared_url`` (``record_url`` stays absent), and it is **byte-identical** to the
        ``record_url`` the single-record GET returns for the same id — proven stable across
        sessions with a fresh bearer. Its measured shape is
        ``https://<host>/record/<27ch opaque>`` — **no signature, no expiry, no query
        parameters**: an **address**, not a credential.

        **This AMENDS the earlier decision that "a shared URL is a credential-class link this
        library never renders" — with its reason intact.** That reason still stands: this
        library never returns a credential-class link. What was measured is that it is **not
        true of THIS field on THIS route** — a Base record's ``shared_url`` here is the stable
        permalink, carrying none of the signature/expiry parameters that mark the genuinely
        credential-class links the ``shared_url`` precedent was written for (the short-lived
        signed attachment links :mod:`larkdocio.base.media` still never renders). The rule did
        not change; its scope was measured. The flag is off by default and only a caller who
        asks for the permalink pays for it — see :func:`larkdocio.base.record_permalink`, the
        per-selection entry point that spends this flag.

        Not paged: the caller names the ids, so the answer is bounded by the ask. An ask longer
        than :data:`BATCH_GET_MAX_IDS` is refused **here, before any call** — chunking is the
        caller's job and discovering the ceiling on the wire is not this library's habit.

        An **empty** ask is the other way round and deliberately so: it is sent, and Lark
        refuses it ``99992402`` naming ``record_ids (the min len is 1)``
        (:data:`BATCH_GET_EMPTY_ASK_REFUSED_CODE`). That refusal is *evidence* — it is what
        proves this endpoint validates the key rather than ignoring it the way R12's family
        ignores an unrecognised one — and Lark's own violation is a better answer than a local
        message. Nothing in this library sends one: the resolver skips a target with no ids.
        """
        ids = [i for i in (record_ids or ())]
        if len(ids) > BATCH_GET_MAX_IDS:
            raise LarkConfigError(
                f"records/batch_get takes at most {BATCH_GET_MAX_IDS} record ids in one call; "
                f"{len(ids)} were passed. Chunk the ask — the ceiling is documented and is "
                "deliberately not probed by walking into it.")
        body_builder = BatchGetAppTableRecordRequestBody.builder().record_ids(ids)
        if with_shared_url:
            body_builder = body_builder.with_shared_url(True)
        body = body_builder.build()
        request = BatchGetAppTableRecordRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .request_body(body) \
            .build()
        return self._checked(self._sdk.bitable.v1.app_table_record.batch_get, request,
                             f"read {len(ids)} named records of table {table_id}").data
