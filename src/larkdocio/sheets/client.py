"""larkdocio.sheets.client — the Sheets read client.

Head of the L1 (standalone Sheets values→Markdown) chain. A small **raw-HTTP**
client that fetches spreadsheet data safely, built on the shared core
(:mod:`larkdocio.common`) exactly as the write client is:

* **auth** — tenant-token via :func:`~larkdocio.common.transport.fetch_tenant_access_token`,
  resolved from the **READ** credential pair (:func:`~larkdocio.common.auth.get_read_credentials`
  — ``LARK_READ_APP_*`` → legacy fallback) and under the shared IPv4 pin. The write
  credential path is **never** consulted (credential doctrine; PROJECT.md, in the dev repo).
* **throttle** — every read routes through :class:`~larkdocio.common.transport.RateLimiter`
  with a read cap **≪ Lark's 100/sec** ceiling (:data:`DEFAULT_MAX_READS_PER_SEC`),
  so the client is gentle and purposeful (spike Q5).
* **typed** — a non-zero Lark ``code`` raises the typed taxonomy
  (:class:`~larkdocio.errors.LarkAPIError` / :class:`LarkRateLimitError`) via
  :func:`~larkdocio.common.transport.raise_for_lark_code`; missing read creds raise
  :class:`~larkdocio.errors.LarkConfigError`.

**Raw HTTP, no new dependency.** The v2 ``values`` / ``values_batch_get`` endpoints
are absent from the pinned ``lark-oapi`` SDK (spike Q5/Q7), so — like the write
path — this reaches them with raw ``urllib``. The v3 metadata / ``sheets/query``
endpoints are hit the same way for one uniform code path.

**Explicit render options, always**. Every values read sends an explicit
``valueRenderOption`` (default ``FormattedValue`` — the human-display source; the
unspecified default is a distinct, lossy mode the spike proved), plus
``dateTimeRenderOption=FormattedString`` (dates as display strings, not serial
floats) and ``user_id_type`` (governs ``@user`` mention rendering). There is **one**
value-param builder so no code path can omit ``valueRenderOption``.

Scope: this returns **parsed values / metadata**, not Markdown — used-range
trim, the value→Markdown render, table assembly + the merge join, and
the opt-in docx embedded-sheet deep-read each live in their own module.
"""
import urllib.request

from larkdocio.common.auth import apply_ipv4_pin, get_read_credentials
from larkdocio.common.auth import resolved_read_env
from larkdocio.common.transport import (
    CredentialedRawHttpClient,
    RateLimiter,
    api_base,
    fetch_tenant_access_token,
    raise_for_lark_code,
)
from larkdocio.errors import (
    LarkAPIError,
    LarkConfigError,
    LarkPermissionError,
    LarkRateLimitError,
    LarkSpreadsheetUnreadableError,
    api_error_as,
)
from larkdocio.sheets.extent import UsedRange, declared_grid_range
from larkdocio.sheets.models import (
    SheetFilter,
    SheetTab,
    SpreadsheetMeta,
    ValueRange,
    parse_frozen_panes,
    parse_revision,
)
from larkdocio.sheets.walk import (
    TAB_READ,
    TAB_SKIPPED,
    TabOutcome,
    TabSkip,
    SpreadsheetRead,
    skip_sentence,
)

#: Client-side read cap — gentle, well under Lark's documented 100/sec read ceiling
#: (spike Q5). One literal so tuning the pace is a one-line edit.
DEFAULT_MAX_READS_PER_SEC = 8

#: The D1 default render source: human-display strings ("$1,234.56", "12.34%",
#: "7/26/2026"). ``ToString`` and the unspecified default are lossy and excluded.
DEFAULT_VALUE_RENDER_OPTION = "FormattedValue"
#: Dates/datetimes as formatted display strings, not raw serial floats (spike Q1).
DEFAULT_DATE_TIME_RENDER_OPTION = "FormattedString"
#: Governs how ``@user`` mention cells render (D6; spike Q7 OSS survey).
DEFAULT_USER_ID_TYPE = "open_id"


class SheetsReadClient(CredentialedRawHttpClient):
    """Throttled, typed Sheets read client on the shared core.

    ``urlopen`` / ``token_fetcher`` / ``rate_limiter`` are injectable so the
    request-building, throttling, and error-typing are unit-testable offline
    (see ``tests/test_sheets_client.py``); the defaults are the real ``urllib``,
    the shared token fetcher, and a :class:`RateLimiter` at
    :data:`DEFAULT_MAX_READS_PER_SEC`.
    """

    def __init__(
        self,
        app_id,
        app_secret,
        domain="larksuite.com",
        *,
        urlopen=urllib.request.urlopen,
        token_fetcher=fetch_tenant_access_token,
        rate_limiter=None,
        value_render_option=DEFAULT_VALUE_RENDER_OPTION,
        date_time_render_option=DEFAULT_DATE_TIME_RENDER_OPTION,
        user_id_type=DEFAULT_USER_ID_TYPE,
        timeout=30,
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._base = api_base(domain)
        self._urlopen = urlopen
        self._token_fetcher = token_fetcher
        self._limiter = rate_limiter or RateLimiter(DEFAULT_MAX_READS_PER_SEC)
        self._value_render_option = value_render_option
        self._date_time_render_option = date_time_render_option
        self._user_id_type = user_id_type
        self._timeout = timeout
        self._token = None

    def _credential_pair(self):
        """The READ pair, as resolved right now — a workbook read consults no other
        (LD-672), the same pair this client's scope denials already name."""
        return resolved_read_env()

    # -- construction ----------------------------------------------------- #

    @classmethod
    def from_read_credentials(cls, domain="larksuite.com", **kwargs):
        """Build a client from the **READ** credential pair (+ IPv4 pin).

        Resolves via :func:`~larkdocio.common.auth.get_read_credentials`
        (``LARK_READ_APP_*`` → legacy ``LARK_APP_*``) — the write pair is never
        consulted (credential doctrine). Applies the shared IPv4 pin (idempotent;
        honors ``LARK_DISABLE_IPV4_PIN``). Missing/half-configured read creds are a
        loud :class:`~larkdocio.errors.LarkConfigError`, never a silent fallback.
        """
        app_id, app_secret = get_read_credentials()
        if not app_id or not app_secret:
            raise LarkConfigError(
                "Sheets read client: no READ credentials resolved. Set "
                "LARK_READ_APP_ID/LARK_READ_APP_SECRET (or the legacy "
                "LARK_APP_ID/LARK_APP_SECRET)."
            )
        apply_ipv4_pin()
        return cls(app_id, app_secret, domain, **kwargs)

    # -- transport (over common.transport.RawHttpClient) ------------------ #

    def _raw_get(self, path, params=None):
        """One raw-HTTP GET over the shared core (B2 — GET-only). Returns the parsed
        JSON body (dict). The shared skeleton's default HTTPError posture applies
        (B1): a Lark error body is parsed and **returned** so :func:`raise_for_lark_code`
        can type it — never raised here — and a non-JSON body degrades to
        ``{"code","msg"}``; a genuine transport (``URLError``) failure raises the
        typed :class:`~larkdocio.errors.LarkAPIError`. Auth/bearer caching and request
        construction come from :class:`~larkdocio.common.transport.CredentialedRawHttpClient`.
        """
        return self._send("GET", path, params=params)

    def _get(self, path, params=None, *, context):
        """Throttled + typed GET: pace via the RateLimiter, then type non-zero codes."""
        self._limiter.acquire()
        resp = self._raw_get(path, params)
        return raise_for_lark_code(resp, context=context,
                                   credential_env=resolved_read_env())

    def _value_params(self, value_render_option, date_time_render_option, user_id_type):
        """The ONE builder for values query params — always explicit render options.

        ``valueRenderOption`` is **never** omitted: a ``None``/blank argument falls
        back to the client default (``FormattedValue``), never to Lark's unspecified
        (lossy) default (D1). ``dateTimeRenderOption`` + ``user_id_type`` are always
        sent too (D1/D6).
        """
        return {
            "valueRenderOption": value_render_option or self._value_render_option,
            "dateTimeRenderOption": (
                date_time_render_option or self._date_time_render_option
            ),
            "user_id_type": user_id_type or self._user_id_type,
        }

    # -- v3 typed read surface ------------------------------------------- #

    def get_spreadsheet_meta(self, spreadsheet_token) -> SpreadsheetMeta:
        """The v3 spreadsheet metadata (title / owner / url)."""
        resp = self._get(
            f"/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}",
            context="sheets metadata",
        )
        return SpreadsheetMeta.from_response(resp)

    def query_sheets(self, spreadsheet_token) -> list[SheetTab]:
        """The v3 ``sheets/query`` — every tab's id / title / index / grid extent /
        ``merges`` array / **visibility**, in sheet order.

        :attr:`~larkdocio.sheets.models.SheetTab.hidden` rides along at **zero additional
        cost**: this endpoint answers it on every tab element, so the one GET made here is
        the whole price of knowing which tabs a person cannot see. A tab whose payload does
        not say usably reports ``None``, never ``False``.
        """
        resp = self._get(
            f"/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query",
            context="sheets tab query",
        )
        sheets = (resp.get("data") or {}).get("sheets") or []
        return [SheetTab.from_dict(s) for s in sheets]

    def get_sheet_filter(self, spreadsheet_token, sheet_id) -> SheetFilter | None:
        """The v3 ``.../sheets/{sheet_id}/filter`` — one tab's filter state.

        Returns a :class:`~larkdocio.sheets.models.SheetFilter` (its range, the rows the
        filter **hides**, and the per-column conditions), or ``None`` when the tab has **no
        filter** — which the API reports as a *successful* response whose ``data`` simply
        omits the filter object.

        Non-zero codes raise the typed taxonomy, exactly like every other read op here. The
        graceful, never-raising wrapper a document read should use is
        :meth:`read_tab_filter`.

        The row numbers this returns are **sheet-absolute and 1-indexed** — see
        :class:`~larkdocio.sheets.models.SheetFilter`, which documents how that was
        established and why it differs from the merge geometry's convention.
        """
        resp = self._get(
            f"/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}"
            f"/sheets/{sheet_id}/filter",
            context="sheets filter",
        )
        return SheetFilter.from_response(resp)

    def read_tab_filter(self, spreadsheet_token, tab: SheetTab) -> SheetTab:
        """``tab`` + its filter state, resolved **gracefully** — this never raises.

        Returns a copy of ``tab`` in one of three states: a filter was found
        (:data:`~larkdocio.sheets.models.FILTER_ACTIVE`, carrying the hidden rows), there is
        no filter (:data:`~larkdocio.sheets.models.FILTER_NONE`), or the filter could not be
        read at all (:data:`~larkdocio.sheets.models.FILTER_UNAVAILABLE`, carrying the
        reason).

        **A filter read must never be able to fail a document read.** A missing permission,
        a rejected call, a transport failure — none of them is a reason to lose the
        spreadsheet's contents. But nor may a failure be laundered into "no filter": the
        third state exists so that *not knowing* is stated rather than guessed, and the
        rendered output discloses it as its own note.

        One call per tab, on the same throttle as every other read. A tab whose filter is
        never read stays in the ``not-read`` state and renders unchanged, so this costs
        nothing until it is asked for.
        """
        try:
            sheet_filter = self.get_sheet_filter(spreadsheet_token, tab.sheet_id)
        except Exception as exc:  # noqa: BLE001 — a filter read never fails the read
            return tab.with_filter_unavailable(
                f"the filter read for this tab did not succeed: {exc}"
            )
        return tab.with_filter(sheet_filter)

    # -- v2 metainfo: the FROZEN-PANES read leg (LD-186) ------------------ #

    def get_frozen_panes(self, spreadsheet_token) -> dict:
        """``GET …/sheets/v2/spreadsheets/{token}/metainfo`` → ``{sheet_id: FrozenPanes}``.

        How many leading rows/columns each tab keeps pinned. This is the read that makes a
        freeze **verifiable**: before it existed, larkdocio surfaced a tab's frozen counts
        nowhere at all, so a freeze write had nothing to compare against.

        ``metainfo`` is the endpoint because it is the one read that carries the frozen counts
        **and** the grid they must fit inside (``rowCount`` / ``columnCount``) in a single call
        — established by probing the live API. One call answers the whole spreadsheet; there is
        no per-tab frozen endpoint.

        A tab whose payload carries no usable frozen counts is **absent from the returned
        mapping** rather than defaulted to zero, so a caller can never mistake "unknown" for
        "unfrozen". Non-zero codes raise the typed taxonomy exactly like every other read op
        here; the graceful, never-raising wrapper a document read should use is
        :meth:`read_tabs_frozen`.
        """
        resp = self._get(
            f"/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/metainfo",
            context="sheets metainfo (frozen panes)",
        )
        out = {}
        for sheet in (resp.get("data") or {}).get("sheets") or []:
            sheet_id = sheet.get("sheetId")
            panes, _reason = parse_frozen_panes(sheet, source="metainfo")
            if sheet_id and panes is not None:
                out[sheet_id] = panes
        return out

    def read_tabs_frozen(self, spreadsheet_token, tabs) -> list[SheetTab]:
        """``tabs`` + their frozen state, resolved **gracefully** — this never raises.

        Returns a copy of each tab in one of three states: the tab freezes something
        (:data:`~larkdocio.sheets.models.FROZEN_ACTIVE`, carrying the counts), it freezes
        nothing (:data:`~larkdocio.sheets.models.FROZEN_NONE` — a **known** answer), or the
        answer could not be established (:data:`~larkdocio.sheets.models.FROZEN_UNAVAILABLE`,
        carrying the reason).

        **A frozen read must never be able to fail a document read**, and nor may a failure be
        laundered into "nothing is frozen" — the same posture the filter read takes. The three
        ways this can come back empty (the call failed / the tab was not in the response / the
        response carried no frozen keys) are kept **distinguishable**, each with its own
        recorded reason, because three outcomes that all answer the same nothing is precisely
        how a defect hides.

        **One call for every tab**, not one per tab: ``metainfo`` is spreadsheet-scoped. A tab
        whose frozen state is never read stays ``not-read`` and renders exactly as it always
        has, so this costs nothing until it is asked for.
        """
        try:
            by_id = self.get_frozen_panes(spreadsheet_token)
        except Exception as exc:  # noqa: BLE001 — a frozen read never fails the read
            return [
                tab.with_frozen_unavailable(
                    f"the frozen (metainfo) read for this spreadsheet did not succeed: {exc}"
                )
                for tab in tabs
            ]
        out = []
        for tab in tabs:
            panes = by_id.get(tab.sheet_id)
            if panes is None:
                out.append(tab.with_frozen_unavailable(
                    f"the metainfo read succeeded but carried no usable frozen counts for tab "
                    f"{tab.sheet_id!r} (it was absent from the response, or its payload named "
                    f"neither frozenRowCount nor frozenColCount) — so whether this tab freezes "
                    f"anything is UNKNOWN, which is not the same as nothing being frozen"
                ))
            else:
                out.append(tab.with_frozen(panes))
        return out

    # -- v2 metainfo: the REVISION-ANCHOR read leg (LD-332) --------------- #

    def read_revision(self, spreadsheet_token) -> int | None:
        """``GET …/sheets/v2/spreadsheets/{token}/metainfo`` → ``data.properties.revision``.

        **The spreadsheet's version — one number for the whole spreadsheet, not per tab.**
        This is the anchor a consumer's ledger compares between runs to answer *"is this the
        same version I ingested last time?"*, and it is the **same number**
        :attr:`~larkdocio.sheets.extent.UsedRange.revision` has always carried off the values
        reply — probed read-only (``tests/captures/sheets-revision-anchor-probe/``, in the source repository) — so the two
        read paths report one anchor rather than two vocabularies.

        Returns ``None`` when the reply carries no usable revision; ``None`` means **not
        known**, never revision ``0`` (a real value here). Non-zero codes raise the typed
        taxonomy exactly like every other read op; the graceful, never-raising wrapper a
        document read should use is :meth:`read_tabs_revision`.
        """
        revision, _reason = parse_revision(self._metainfo_revision_raw(spreadsheet_token))
        return revision

    def _metainfo_revision_raw(self, spreadsheet_token):
        resp = self._get(
            f"/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/metainfo",
            context="sheets metainfo (revision anchor)",
        )
        return ((resp.get("data") or {}).get("properties") or {}).get("revision")

    def read_tabs_revision(self, spreadsheet_token, tabs) -> list[SheetTab]:
        """``tabs`` + the spreadsheet's revision anchor, resolved **gracefully** — never raises.

        Returns a copy of each tab in one of two states: the anchor is known
        (:data:`~larkdocio.sheets.models.REVISION_KNOWN`, carrying it in
        :attr:`~larkdocio.sheets.models.SheetTab.revision`), or it could not be established
        (:data:`~larkdocio.sheets.models.REVISION_UNAVAILABLE`, carrying the reason). There is
        no third "this spreadsheet has no revision" state, because that is not a fact about a
        spreadsheet — it is a gap in what the read learned.

        **A version read must never be able to fail a document read**, and nor may a failure be
        laundered into revision ``0`` — the posture the filter and frozen legs already take.

        **One call for every tab**, not one per tab: the anchor is spreadsheet-scoped, so every
        tab of one spreadsheet carries the *same* number by construction. That is the cost this
        leg adds — one ``metainfo`` GET per spreadsheet, and only when asked: a tab whose
        revision is never read stays ``not-read``, because the v3 tab query carries no revision
        at all and nothing here fetches one behind a caller's back.
        """
        try:
            raw = self._metainfo_revision_raw(spreadsheet_token)
        except Exception as exc:  # noqa: BLE001 — a revision read never fails the read
            return [
                tab.with_revision_unavailable(
                    f"the revision (metainfo) read for this spreadsheet did not succeed: {exc}"
                )
                for tab in tabs
            ]
        revision, reason = parse_revision(raw)
        if revision is None:
            return [tab.with_revision_unavailable(reason) for tab in tabs]
        return [tab.with_revision(revision) for tab in tabs]

    # -- v2 raw values read surface -------------------------------------- #

    def get_values(
        self,
        spreadsheet_token,
        a1_range,
        *,
        value_render_option=None,
        date_time_render_option=None,
        user_id_type=None,
    ) -> ValueRange:
        """A single range's values (v2 ``values/{range}``), always with explicit
        render options. ``a1_range`` is ``{sheetId}!A1:D24``."""
        params = self._value_params(
            value_render_option, date_time_render_option, user_id_type
        )
        resp = self._get(
            f"/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values/{a1_range}",
            params,
            context="sheets values",
        )
        return ValueRange.from_dict((resp.get("data") or {}).get("valueRange") or {})

    def batch_get_values(
        self,
        spreadsheet_token,
        ranges,
        *,
        value_render_option=None,
        date_time_render_option=None,
        user_id_type=None,
    ) -> list[ValueRange]:
        """Multiple ranges in ONE call (v2 ``values_batch_get``) — passed as a single
        comma-separated ``ranges=`` param, returned per-range **in order**, each with
        its own ``revision``. ``ranges`` is a list of A1 ranges (may span tabs)."""
        params = self._value_params(
            value_render_option, date_time_render_option, user_id_type
        )
        params["ranges"] = ",".join(ranges)
        resp = self._get(
            f"/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values_batch_get",
            params,
            context="sheets values batch",
        )
        value_ranges = (resp.get("data") or {}).get("valueRanges") or []
        return [ValueRange.from_dict(vr) for vr in value_ranges]

    # -- used-range discovery (S2) --------------------------------------- #

    def read_used_range(
        self,
        spreadsheet_token,
        tab: SheetTab,
        *,
        value_render_option=None,
        date_time_render_option=None,
        user_id_type=None,
    ) -> UsedRange:
        """Discover a tab's **used range**: read the declared grid (the upper bound),
        then trim trailing all-null rows/columns in memory.

        The declared ``row_count`` × ``column_count`` from the v3 tab-query metadata
        (``tab``) is the **upper bound**: this issues **one** values read of exactly
        that grid extent — never a cell past it, never an iterative over-probe — then
        returns a :class:`~larkdocio.sheets.extent.UsedRange` whose matrix is trimmed
        to the minimal used range with **interior nulls preserved** (empty interior
        cells and merge-covered nulls survive, for the merge join).
        """
        a1 = declared_grid_range(tab.sheet_id, tab.row_count, tab.column_count)
        vr = self.get_values(
            spreadsheet_token,
            a1,
            value_render_option=value_render_option,
            date_time_render_option=date_time_render_option,
            user_id_type=user_id_type,
        )
        return UsedRange.from_tab_values(tab, vr.values, revision=vr.revision)

    # -- the whole-workbook walk (LD-383) --------------------------------- #

    def read_spreadsheet(
        self,
        spreadsheet_token,
        *,
        tabs=None,
        value_render_option=None,
        date_time_render_option=None,
        user_id_type=None,
    ) -> SpreadsheetRead:
        """Read **every tab** of a workbook, **skipping a per-tab miss loudly**.

        Enumerate (:meth:`query_sheets`, unless ``tabs`` is supplied) then read each tab's
        used range. A tab Lark refuses — the reported shape is ``90215 not found sheetId`` on
        a tab ``query_sheets`` **itself listed** — is **disclosed and skipped**, and the walk
        continues, so a workbook of 22 tabs with 20 refusals still hands back the 2 that read.
        Before this, the first refusal ended the walk and the caller got nothing.

        The result is a :class:`~larkdocio.sheets.walk.SpreadsheetRead`: an outcome per tab
        (:meth:`~larkdocio.sheets.walk.SpreadsheetRead.accounted` is the "every tab appears
        exactly once" invariant), ``pairs`` for
        :func:`~larkdocio.sheets.table.render_spreadsheet`, and ``skips`` carrying **Lark's own
        verbatim code and msg** per refused tab. The skip is in the **returned structure**, not
        in a log line a caller may not be capturing — a silent short read would be a worse
        defect than the crash this replaces.

        **What is NOT skipped — the boundary.** A skip needs **Lark's own answer about this
        tab**: a :class:`~larkdocio.errors.LarkAPIError` carrying a ``code``, that is neither a
        rate limit (:class:`~larkdocio.errors.LarkRateLimitError`) nor a scope denial
        (:class:`~larkdocio.errors.LarkPermissionError`). A throttle and a denial are facts
        about the *call*, not about the tab, and laundering either into "this tab is
        unreadable" would turn a transient or a missing grant into a permanently short
        document; a codeless failure (a transport error) is not Lark answering at all. Those
        all propagate, as does anything the **enumeration** itself raises — there is no walk to
        continue when the tab list never arrived.

        **All-skipped raises.** If every enumerated tab missed, this raises
        :class:`~larkdocio.errors.LarkSpreadsheetUnreadableError` (a ``LarkAPIError`` subclass)
        carrying all the disclosures, rather than returning an empty workbook that reads like
        an empty *spreadsheet*. A workbook that enumerates **no tabs** is not that case: zero
        of zero is Lark's honest answer, and it comes back as an empty result.

        ``tabs`` lets a caller that already enumerated (or that wants a subset) pass its own
        :class:`~larkdocio.sheets.models.SheetTab` objects instead of paying for a second
        query — the :meth:`read_tabs_frozen` / :meth:`read_tabs_revision` precedent.
        """
        tab_list = list(self.query_sheets(spreadsheet_token) if tabs is None else tabs)
        outcomes = []
        for tab in tab_list:
            try:
                used = self.read_used_range(
                    spreadsheet_token,
                    tab,
                    value_render_option=value_render_option,
                    date_time_render_option=date_time_render_option,
                    user_id_type=user_id_type,
                )
            except LarkAPIError as exc:
                if not _is_per_tab_miss(exc):
                    raise
                outcomes.append(TabOutcome(
                    tab=tab, kind=TAB_SKIPPED,
                    skip=TabSkip(sheet_id=tab.sheet_id, title=tab.title,
                                 code=exc.code, msg=exc.msg,
                                 reason=skip_sentence(exc.code, exc.msg))))
            else:
                outcomes.append(TabOutcome(tab=tab, kind=TAB_READ, used=used))

        read = SpreadsheetRead(spreadsheet_token=spreadsheet_token, outcomes=tuple(outcomes))
        if tab_list and not read.reads:
            raise _all_skipped(spreadsheet_token, read)
        return read


def _is_per_tab_miss(exc) -> bool:
    """Is this Lark's own answer **about one tab** — the only class the walk may skip?

    Requires a Lark ``code`` (a codeless failure is a transport error, not an answer), and
    excludes the two codes that are facts about the *call*: a rate limit and a scope denial.
    Written as its own predicate so the boundary is one named, testable place rather than a
    condition buried in an ``except``.
    """
    if isinstance(exc, (LarkRateLimitError, LarkPermissionError)):
        return False
    if getattr(exc, "denial", None) is not None:
        # The CLASS is not the only way a denial arrives any more (LD-644): a surface with its
        # own typed family carries the record on the base attribute, so the check that matters
        # is *does this answer carry a scope denial*, not *is it spelled LarkPermissionError*.
        # Laundering one into "this tab is unreadable" is the exact mistake the arm above
        # exists to prevent.
        return False
    return exc.code is not None


def _all_skipped(spreadsheet_token, read: SpreadsheetRead) -> LarkSpreadsheetUnreadableError:
    """Every tab missed — build the raise that keeps all the evidence (AC4)."""
    skips = [o.skip for o in read.skips]
    first = skips[0]
    detail = "; ".join(f"{s.sheet_id} ({s.title}): code {s.code}: {s.msg}" for s in skips)
    # Through the shared classification seam like every other Lark code this library reports,
    # even though `_is_per_tab_miss` means a scope denial cannot reach here — it propagates
    # instead of being skipped. A rule with a "this one cannot happen" hole in it is a rule
    # somebody has to re-derive; this way there is no exception to remember, and if the skip
    # boundary ever moves, the classification is already right.
    return api_error_as(
        LarkSpreadsheetUnreadableError,
        f"sheets workbook read failed: {len(skips)} of {len(read.outcomes)} tabs of "
        f"{spreadsheet_token} were refused by Lark and NONE could be read — {detail}",
        code=first.code, msg=first.msg, credential_env=resolved_read_env(), skips=skips)
