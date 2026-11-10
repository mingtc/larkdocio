"""larkdocio.sheets.write_client — the Sheets value-write client.

The Sheets write client: a **raw-HTTP**, **WRITE-app-only**, **throttled**,
**typed** value-write client, the sheets parity of the docx :class:`~larkdocio.write.client.WriteClient`.
It reaches the v2 sheets write endpoints — absent from the pinned ``lark-oapi`` SDK
(live-probed) — with raw ``urllib``, built on the shared core
(:mod:`larkdocio.common`) exactly as the read client (:class:`~larkdocio.sheets.client.SheetsReadClient`)
and the docx writer are:

* **auth** — tenant-token via :func:`~larkdocio.common.transport.fetch_tenant_access_token`,
  resolved from the **WRITE** credential pair (:func:`~larkdocio.common.auth.get_write_credentials`
  — ``LARK_WRITE_APP_*``, **no read/legacy fallback** → :class:`~larkdocio.errors.LarkConfigError`).
  The read credential path is **never** consulted for a write (credential doctrine);
* **throttle** — every write routes through :class:`~larkdocio.common.transport.WriteTransport`
  so writes are capped **≤ 3/sec** (a live probe ran ~1.6/s) and back off on Lark's
  ``99991400`` rate-limit code. No op bypasses it;
* **typed** — a non-zero Lark ``code`` raises the typed taxonomy
  (:class:`~larkdocio.errors.LarkAPIError` / :class:`LarkRateLimitError`) via
  :func:`~larkdocio.common.transport.raise_for_lark_code`; the write-specific
  ``90202`` (wrong range) / ``90204`` (validation) codes surface as inspectable
  :class:`LarkAPIError`\\ s carrying the code.

**``Start:End`` always.** The range-bearing v2 endpoints reject a **bare
single-cell** range (``{sid}!A1``) with ``90202 wrong range``. Every
range this client emits is forced through :func:`normalize_write_range`, so a bare
cell is **structurally impossible** on the wire — a single-cell target becomes
``A1:A1``. (The full L1 A1/range model reuse — validation, used-range targets — is
the A1 model's job; this client carries only the minimal Start:End guard.)

**Scope.** Plain **scalar/string value** writes — ``values`` PUT,
``values_batch_update``, ``values_append``, ``values_prepend`` — **plus the
dropdown-rule write** (``POST …/dataValidation``, :meth:`set_data_validation` — the
``dataValidation`` family the rich multi-select cell pairs with).
Rich **cell** writes reuse the ``values`` PUT (a structured cell is just a value);
style/format belongs to the fidelity leg. **The FILE lifecycle**:
:meth:`create_spreadsheet` brings a workbook into existence and
:meth:`delete_spreadsheet` trashes the whole file — the sheets twins of the docx
:meth:`~larkdocio.write.client.WriteClient.create_document` /
:meth:`~larkdocio.write.client.WriteClient.delete_document`, and what makes working
against **disposable** spreadsheets (create → use → delete in a ``finally``) possible
without leaving the library. They are the FILE's lifecycle, not a range's or a tab's:
neither is a plan-gated write op, and neither goes near the apply engine.
**Structural dimension writes**: :meth:`insert_dimension_range`
(0-idx half-open), :meth:`delete_dimension_range` (1-idx inclusive), :meth:`append_dimension`,
and the mandatory geometry re-read :meth:`read_sheet_geometry` — the raw native-convention
transport; the semantic→native index conversion (the structural guard) lives one layer up in
the gated ``write_apply`` request objects. **Dimension PROPERTIES** (the fourth verb on that
path): :meth:`set_dimension_properties` — row height / column width / hide-show, **1-idx
INCLUSIVE** (the *delete* convention, characterized live before the method was written,
**not** insert's half-open span). The ``values_append INSERT_ROWS`` variant reuses
:meth:`append_values`. **Merge/unmerge + tab writes**:
:meth:`merge_cells` (``MERGE_ALL``) / :meth:`unmerge_cells` (both range-bearing, forced to
``Start:End`` — the ``90202`` guard), :meth:`batch_update_sheets` (the ``sheets_batch_update``
tab add/copy/delete endpoint — the ``requests[]`` array passed verbatim), and the write-side
tab-identity read :meth:`query_tabs`; the merge-aware fate reasoning + the destructive-safe
removed-tab snapshot live one layer up in the gated ``write_apply`` request objects. The
remaining write op (style/format) is the fidelity leg's.

**The two write-side reads.** :meth:`SheetsWriteClient.read_revision`
(the ``metainfo.properties.revision`` compare-and-swap anchor) and
:meth:`SheetsWriteClient.read_values` (the raw ``UnformattedValue`` before-snapshot /
precondition read) are the reads the gated apply engine
(:mod:`larkdocio.sheets.write_apply`) performs **as part of the gated write flow** — the
WRITE app reading its own compare-and-swap anchor + before-snapshot, exactly as the docx
:class:`~larkdocio.write.client.WriteClient` reads ``get_block`` for its stale-anchor
re-validation (credential doctrine: a write's own reads use WRITE creds, never the
read app). They **bypass the ≤3/s WRITE throttle** — reads are not write-rate-limited
(``common.transport``: the throttle governs writes).
"""
import urllib.parse
import urllib.request

from larkdocio.common.auth import apply_ipv4_pin, get_write_credentials
from larkdocio.common.auth import WRITE_ENV
from larkdocio.common.destination import require_destination
from larkdocio.common.transport import (
    CredentialedRawHttpClient,
    WriteTransport,
    api_base,
    fetch_tenant_access_token,
    raise_for_lark_code,
)
from larkdocio.errors import LarkAPIError, LarkConfigError
from larkdocio.sheets.models import parse_frozen_panes


# --------------------------------------------------------------------------- #
# The spreadsheet FILE lifecycle (LD-176)                                        #
# --------------------------------------------------------------------------- #

#: Lark's **"this spreadsheet token is deleted / not found"** code — what any **sheets** call
#: against a trashed token answers (``Path param :spreadsheet_token is deleted``). This is the
#: **confirmation** code: reading a token you just deleted and getting this error is how you
#: prove the file is really gone, which a ``code: 0`` from the delete does not.
#:
#: What the code MEANS, and the capture behind it, are authored once for the whole library in
#: ``larkdocio.common.error_codes`` (LD-531). What stays here is the number this surface
#: compares against and the name it compares under — a code is worth centralizing, a comparison
#: is not.
SPREADSHEET_GONE_CODE = 1310249

#: Lark's **"this file is already in the trash"** code — what the **Drive file delete** answers
#: for a file that no longer exists. A *different* endpoint from the one above, with its own
#: code: live-observed 2026-07-30 (``1061007 file has been delete.``) while proving the
#: lifecycle round-trip, correcting an offline assumption that both answered ``1310249``. This
#: is the code a ``finally``-delete forgives. Authored once, same as its sibling above.
FILE_ALREADY_DELETED_CODE = 1061007

#: Every code that means "the spreadsheet is already gone", spanning both endpoints. Kept as
#: strings so the comparison is representation-agnostic (the wire may hand back an int or a
#: str — the same discipline as the rate-limit code).
#:
#: **This is a per-surface CLASSIFICATION and it stays here (LD-531).** Two endpoints answering
#: the same fact with different numbers is a *sheets teardown* fact; no other surface has a
#: reason to hold it, and the one shared lookup is deliberately not a classifier.
_GONE_CODES = frozenset({str(SPREADSHEET_GONE_CODE), str(FILE_ALREADY_DELETED_CODE)})

#: The v3 spreadsheet-collection path — the ONE create endpoint.
_SPREADSHEETS_V3_PATH = "/open-apis/sheets/v3/spreadsheets"

#: The Drive file path a spreadsheet is trashed through, and the file-type query it needs.
#: (A spreadsheet is a Drive FILE; there is no sheets-v3 delete.)
_DRIVE_FILE_PATH = "/open-apis/drive/v1/files/{token}"
_DRIVE_SHEET_TYPE = "sheet"

#: ``(create, delete)`` — the file-lifecycle calls on this client, named beside the methods
#: themselves so the discovery registry (``larkdocio.capabilities()``) can PROJECT them
#: instead of keeping a second hand-maintained list. A name here that is not a method on the
#: class fails at projection time.
LIFECYCLE_OPS = ("create_spreadsheet", "delete_spreadsheet")


#: **The disclosure that cost this library a live object.** Authored once, here, and met twice:
#: in :meth:`SheetsWriteClient.create_spreadsheet`'s docstring and restated on the returned
#: value as :attr:`CreatedSpreadsheet.capture_the_token`, so a caller reading a returned object
#: — not the module — still meets it. Dogfood round 5 lost a workbook to exactly this (ranked
#: major #8 in its digest, which was retired from the dev repo on 2026-09-18).
CAPTURE_THE_TOKEN = (
    "capture the token: a create whose spreadsheet_token is dropped is an orphan by "
    "construction, because nothing else can name that workbook — and a workbook filed where no "
    "human interface can browse cannot be found again by looking"
)


class CreatedSpreadsheet(dict):
    """One spreadsheet created in a folder: **what Lark answered.**

    **It IS the reply's own ``data.spreadsheet`` dict** — a ``dict`` subclass whose body is
    that payload unchanged, so ``created["spreadsheet_token"]``, ``.get``, ``in``, iteration,
    ``len``, ``.keys()/.values()/.items()``, ``json.dumps``, ``dict(created)``, ``{**created}``
    and ``==`` against the plain dict all answer exactly what they answered when this method
    returned a bare dict. The one thing that changes is ``type(created) is dict``, now
    ``False`` (``isinstance`` answers ``True``).

    :attr:`spreadsheet_token`, :attr:`title`, :attr:`url` and :attr:`folder_token` are **views
    onto that same body**, not a second copy, so an attribute cannot drift from its key.

    ``url`` is **Lark's own** — this reply carries one, unlike the docx create's
    (:data:`larkdocio.write.client.DOCX_REPLY_CARRIES_NO_URL`), and it is handed on exactly as
    it arrived. Nothing here assembles a URL from a host and a token.

    :data:`CAPTURE_THE_TOKEN` is restated on the value as :attr:`capture_the_token`.
    """

    __slots__ = ()

    #: Restated on the value itself — the LD-464/round-5 defect class, met where a caller is.
    capture_the_token = CAPTURE_THE_TOKEN

    @property
    def spreadsheet_token(self):
        """The token every other sheets call takes. Never absent: ``create_spreadsheet``
        raises rather than hand back a value that cannot be used or cleaned up."""
        return self.get("spreadsheet_token")

    @property
    def title(self):
        """The title Lark stored, as the reply echoed it."""
        return self.get("title")

    @property
    def url(self):
        """**Lark's own** web address for the workbook — carried, never constructed. ``None``
        if this reply omitted the key, which is a real answer and not a gap to fill in."""
        return self.get("url")

    @property
    def folder_token(self):
        """Where it landed, as the reply reported it — the reply's own key, not an echo of the
        argument, so it is what Lark says rather than what was asked for."""
        return self.get("folder_token")


def spreadsheet_is_gone(error) -> bool:
    """True iff ``error`` says the spreadsheet is **already gone**.

    THE one check a teardown needs, so nobody has to know which endpoint answers which
    number: a delete of an already-trashed file and a read of a trashed token report the fact
    with **different** codes, and both mean the same thing. Use it to forgive exactly that
    outcome in a ``finally`` — and to *confirm* a delete landed — while every other failure
    (a permission problem, a transport failure) still surfaces:

    .. code-block:: python

        try:
            client.delete_spreadsheet(token)
        except LarkAPIError as exc:
            if not spreadsheet_is_gone(exc):
                raise

    Anything that is not a Lark error carrying one of those codes is ``False`` — including a
    code-less error (a failure below Lark, where whether the file is gone is unknown and must
    not be assumed).
    """
    code = getattr(error, "code", None)
    return code is not None and str(code) in _GONE_CODES


# --------------------------------------------------------------------------- #
# The plan-time @mention id check (LD-148 / dogfood round-2 T27)                 #
# --------------------------------------------------------------------------- #

#: The contacts batch endpoint the mention-id check reads. Same endpoint the READER uses for
#: @mention display names (``read/client.py`` — via the SDK); reached with raw HTTP here so
#: the WRITE app performs its own plan-time read (credential doctrine D1).
_CONTACT_USERS_BATCH_PATH = "/open-apis/contact/v3/users/batch"

#: The endpoint's ids-per-call limit (same as the reader's SDK chunking).
_USER_BATCH_CHUNK = 50

#: Lark's "one or more of these ids is not a valid / existing id" code — the ONE code that is
#: **positive proof of non-existence**, because its ``error.field_violations[]`` names the
#: offending ids individually. Live-proven read-only 2026-07-28 (log_id
#: ``20260728152453A52E092131CF9A78E884``): a bogus ``open_id`` answers
#: ``99992351`` + ``field_violations: [{"field": "user_ids", "value": "<id>",
#: "description": "id not exist"}]``. Kept as an int constant compared representation-
#: agnostically (the wire may hand back an int or a str).
INVALID_USER_IDS_CODE = 99992351


def _invalid_user_ids(resp, chunk) -> list:
    """The ids Lark named as nonexistent in an :data:`INVALID_USER_IDS_CODE` response.

    Reads ``error.field_violations[]`` — the **per-id** attribution — and keeps only values
    that were actually in the chunk we asked about, so a drifted/echoed field can never make
    the engine refuse an id the caller never wrote. When the code says "invalid ids" but the
    body carries **no** parsable violation, nothing is reported invalid: the check only ever
    refuses on positive proof (the caller then discloses the unproven state).
    """
    error = (resp or {}).get("error") or {}
    asked = set(chunk)
    named = []
    for violation in error.get("field_violations") or []:
        if not isinstance(violation, dict):
            continue
        value = violation.get("value")
        if value in asked and value not in named:
            named.append(value)
    return named


def normalize_write_range(a1_range: str) -> str:
    """Force an A1 range to an explicit ``Start:End`` — the ``90202`` guard.

    Splits off an optional ``{sheetId}!`` prefix and, when the range body carries
    no ``:``, duplicates the single cell (``A1`` → ``A1:A1``) so a bare single-cell
    range is **structurally impossible** to emit (a live probe confirmed a bare cell → ``90202
    wrong range``). An already-``Start:End`` range is returned unchanged — order is
    **preserved verbatim** (reversed/validation is the A1 model's job; this guard only
    guarantees the colon is present).
    """
    if a1_range is None:
        raise LarkConfigError("write range must not be None")
    raw = a1_range.strip()
    if not raw:
        raise LarkConfigError("write range must not be empty")
    # rpartition on the LAST '!' splits an optional {sheetId}! prefix from the
    # cell range; a range with no prefix keeps head='' and body=raw.
    prefix, sep, body = raw.rpartition("!")
    head = prefix + sep if sep else ""
    cell = body if sep else raw
    if ":" in cell:
        return head + cell
    return f"{head}{cell}:{cell}"


def _value_range(a1_range, values) -> dict:
    """The ``{range, values}`` value-range body, range forced to ``Start:End``.

    THE single chokepoint every op routes its range(s) through — so no path can
    place a bare cell on the wire.
    """
    return {"range": normalize_write_range(a1_range), "values": values}


def _sheets_v2_path(spreadsheet_token, suffix) -> str:
    """The v2 sheets path: ``…/sheets/v2/spreadsheets/{tok}/{suffix}``."""
    return f"/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/{suffix}"


# --------------------------------------------------------------------------- #
# The FLOAT-IMAGE family (LD-448) — a picture anchored OVER a range.           #
# --------------------------------------------------------------------------- #

#: The v3 float-image collection on one tab. The **tab** appears here and nowhere earlier on
#: this route: the upload that mints the token is parented on the **spreadsheet**.
_FLOAT_IMAGES_PATH = (
    "/open-apis/sheets/v3/spreadsheets/{token}/sheets/{sheet_id}/float_images")


def _float_images_path(spreadsheet_token, sheet_id) -> str:
    return _FLOAT_IMAGES_PATH.format(token=spreadsheet_token, sheet_id=sheet_id)


#: **THE HIGHEST-CONSEQUENCE DISCLOSURE ON THE FLOAT ROUTE — authored ONCE here and quoted
#: wherever the route is described** (:mod:`larkdocio.sheets.media`, the guide's recipe, and
#: ``SHEETS.md`` in the source repository). Two paraphrases of a disclosure are two texts that can drift into
#: disagreeing about what was measured. Evidence: the sheets-media spike's captures ``108-``
#: (the refusal) and ``201-`` (the re-query proving no phantom was created), in the source repository.
FLOAT_IMAGE_REFUSAL_IS_NOT_A_RETRY = (
    "THIS ROUTE MIS-TYPES A REFUSAL AS A SERVER ERROR. Binding a float_image_token that was "
    "never minted was measured to answer HTTP 500 with 1315203 \"Server Error, Retry Later\" "
    "while actually refusing: a fresh float_images/query showed nothing had been created. So "
    "an error here is a REFUSAL, not a transient failure — DO NOT RETRY it on the strength of "
    "its message, and never classify it as transient. Nothing in this library retries it. The "
    "only thing that establishes what exists on the tab is a fresh float_images/query, and "
    "any media token already uploaded is PERMANENT, UNPURGEABLE RESIDUE"
)


def _disclose(error, disclosure) -> None:
    """Grow a typed error's message by ``disclosure``, keeping its class, code, msg and body.

    The alternative — raising a new error type — would drop the taxonomy a caller sorts on
    (a rate limit must stay a rate limit, a scope denial must keep its console link).
    """
    head = error.args[0] if error.args else ""
    error.args = (f"{head} — {disclosure}",) + tuple(error.args[1:])


class SheetsWriteClient(CredentialedRawHttpClient):
    """Throttled, typed, WRITE-app-only Sheets value-write client on the shared core.

    ``transport`` / ``urlopen`` / ``token_fetcher`` are injectable so the
    request-building, throttling, and error-typing are unit-testable offline
    (see ``tests/test_sheets_write_client.py``); the defaults are the real
    :class:`WriteTransport`, ``urllib``, and the shared token fetcher.
    """

    def __init__(
        self,
        app_id,
        app_secret,
        domain="larksuite.com",
        *,
        transport=None,
        urlopen=urllib.request.urlopen,
        token_fetcher=fetch_tenant_access_token,
        timeout=30,
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._base = api_base(domain)
        self._transport = transport or WriteTransport()
        self._urlopen = urlopen
        self._token_fetcher = token_fetcher
        self._timeout = timeout
        self._token = None

    def _credential_pair(self):
        """The WRITE pair — this client resolves no other, so a rejected credential here
        names ``LARK_WRITE_APP_*`` and never the pair a reader is resolving (LD-672)."""
        return WRITE_ENV

    # -- construction ----------------------------------------------------- #

    @classmethod
    def from_write_credentials(cls, domain="larksuite.com", **kwargs):
        """Build a client from the **WRITE** credential pair (+ IPv4 pin).

        Resolves via :func:`~larkdocio.common.auth.get_write_credentials`
        (``LARK_WRITE_APP_*`` — **no** read/legacy fallback): a missing or
        half-configured write pair is a loud :class:`~larkdocio.errors.LarkConfigError`,
        never a silent promotion of a read-only app to a write (credential doctrine
        the least-privilege split). Applies the shared IPv4 pin (idempotent; honors
        ``LARK_DISABLE_IPV4_PIN``).
        """
        app_id, app_secret = get_write_credentials()
        apply_ipv4_pin()
        return cls(app_id, app_secret, domain, **kwargs)

    # -- transport (over common.transport.RawHttpClient) ------------------ #

    def _raw_request(self, method, path, body=None, params=None):
        """One raw v2 attempt over the shared core (B2 — body-bearing, with GET-side
        ``params``). Returns the parsed JSON body (dict). ``params`` is appended as a
        query string with A1-range punctuation (``! : ,``) left unescaped (the shared
        core's ``_QUERY_SAFE``). The shared skeleton's default HTTPError posture
        applies (B1): a Lark error body (e.g. ``90202``) is parsed and **returned** so
        the transport can see a ``99991400`` and back off and :func:`raise_for_lark_code`
        can type the rest — never raised here — and a non-JSON body degrades to
        ``{"code","msg"}``; a genuine transport (``URLError``) failure raises the typed
        :class:`~larkdocio.errors.LarkAPIError`.
        """
        return self._send(method, path, body=body, params=params)

    def _write(self, method, path, body=None, *, context="sheets write"):
        """Throttled write: pace + 99991400 backoff (the shared transport), then
        type any non-zero Lark ``code``. Returns the parsed response ``data``."""
        resp = self._transport.execute(lambda: self._raw_request(method, path, body))
        typed = raise_for_lark_code(resp, context=context,
                                    credential_env=WRITE_ENV)
        return typed.get("data") if isinstance(typed, dict) else None

    def _read(self, path, params=None, *, context="sheets read"):
        """UN-throttled GET (reads are not write-rate-limited), then type any non-zero
        Lark ``code``. Returns the parsed response ``data``. The write-side reads the
        gated apply engine's compare-and-swap needs (revision + before-snapshot) route
        through here, NOT the write transport — so they never spend throttle budget."""
        resp = self._raw_request("GET", path, params=params)
        typed = raise_for_lark_code(resp, context=context,
                                    credential_env=WRITE_ENV)
        return typed.get("data") if isinstance(typed, dict) else None

    # -- the spreadsheet FILE lifecycle (LD-176) --------------------------- #
    #
    # Deliberately FIRST, and deliberately far from `batch_update_sheets` (the TAB
    # add/copy/delete op): the two destructive scopes must not read as neighbours, because
    # confusing "trash the workbook" with "remove a tab" costs a workbook.

    def create_spreadsheet(self, title="", *, folder_token) -> "CreatedSpreadsheet":
        """Create a spreadsheet in ``folder_token``; returns a :class:`CreatedSpreadsheet`.

        The sheets twin of
        :meth:`~larkdocio.write.client.WriteClient.create_document`, and the call that makes
        the **disposables** pattern followable: create a throwaway workbook, do your write
        work against it, and trash it with :meth:`delete_spreadsheet` in a ``finally``, so
        no experiment ever touches a document someone owns.

        **The destination is the caller's** — ``folder_token`` is **required**, and every
        spelling of "none" you can actually pass — ``None``, empty, whitespace — is refused
        **locally, before any call**, with :class:`~larkdocio.errors.MissingDestinationError`.
        **Omitting the keyword is a different failure, and an earlier one:** ``folder_token``
        is keyword-only with no default, so leaving it out of the call entirely raises Python's
        own ``TypeError`` (``missing 1 required keyword-only argument: 'folder_token'``) before
        this library ever runs — pass ``folder_token=None`` (or any other refused spelling) to
        reach the teaching refusal instead of the bare ``TypeError``. It used to default to the
        empty string, which Lark accepts and files the workbook in the application's own
        space: a space with no human interface, whose trash cannot be listed and where a delete
        is a trash rather than a purge. The rule and its measurements are on
        :mod:`larkdocio.common.destination`; nothing here creates a folder to put the workbook
        in. So the disposables pattern is followable *and* visible: the throwaway workbook lands
        in a folder you can open.

        **The returned value IS the reply's ``data.spreadsheet``** — a ``dict`` subclass
        carrying that payload unchanged, so every subscript, ``.get``, membership test, splat,
        ``json.dumps`` and ``==`` against the plain dict keeps its old answer. It carries
        ``spreadsheet_token`` (the token every other call takes), ``title``, ``url`` and
        ``folder_token`` — as keys *and* as attributes reading those same keys. **This reply's
        ``url`` is real**: it is Lark's own answer, carried as it arrived and never assembled
        (unlike the docx create, whose reply has none —
        :data:`larkdocio.write.client.DOCX_REPLY_CARRIES_NO_URL`).

        **Capture the token.** :data:`CAPTURE_THE_TOKEN`, and it is restated on the returned
        value as :attr:`CreatedSpreadsheet.capture_the_token`. If the reply carries no
        ``spreadsheet_token`` this raises :class:`~larkdocio.errors.LarkAPIError` rather than
        handing back an object that cannot be used or cleaned up.

        A fresh workbook comes with one tab; ask :meth:`query_tabs` for its ``sheet_id``
        (an A1 range addresses a tab by that opaque id, never by its title). Rides the
        shared write throttle like every other write op.
        """
        require_destination(folder_token, what="a spreadsheet")
        body = {"title": title, "folder_token": folder_token}
        data = self._write(
            "POST", _SPREADSHEETS_V3_PATH, body, context="create spreadsheet")
        spreadsheet = (data or {}).get("spreadsheet") or {}
        if not spreadsheet.get("spreadsheet_token"):
            raise LarkAPIError(
                "create spreadsheet succeeded but the reply carried no "
                f"spreadsheet_token — nothing can address or clean up what was created: "
                f"{data!r}"
            )
        return CreatedSpreadsheet(spreadsheet)

    def delete_spreadsheet(self, spreadsheet_token):
        """Trash the **whole spreadsheet FILE** — **not a tab** — and return the reply data.

        The destructive scope is the entire workbook: every tab, every value, every rule it
        holds goes to the Drive trash with it. **This is not the tab delete.** To remove ONE
        tab from a workbook that survives, use the plan-gated tab op
        (``DeleteTab`` through the sheets write engine's
        ``dry_run`` → ``apply``), which previews the removal and snapshots the tab's identity
        first. Reach for this call only for a workbook you are finished with — typically one
        you created yourself with :meth:`create_spreadsheet`.

        Needs a Drive scope (a spreadsheet is a Drive file; there is no sheets-native
        delete). **Not idempotent, on purpose:** deleting a file that is already in the trash
        raises the typed :class:`~larkdocio.errors.LarkAPIError` carrying
        :data:`FILE_ALREADY_DELETED_CODE` — never a silent success — so a teardown can forgive
        exactly that one outcome (:func:`spreadsheet_is_gone`) and still fail loudly on
        anything else, such as a permission problem.

        **Confirming it landed is a separate act, and worth doing:** a ``code: 0`` here means
        "accepted". Address the token again (``query_tabs``) and the sheets side answers
        :data:`SPREADSHEET_GONE_CODE` — *that* error is the proof. The two codes differ because
        the two endpoints do; :func:`spreadsheet_is_gone` spans both.
        """
        path = _DRIVE_FILE_PATH.format(token=spreadsheet_token)
        return self._write(
            "DELETE", f"{path}?type={_DRIVE_SHEET_TYPE}", None,
            context="delete spreadsheet",
        )

    # -- v2 value-write surface (AC1) ------------------------------------ #

    def put_values(self, spreadsheet_token, a1_range, values):
        """``PUT …/values`` — overwrite ``a1_range`` with ``values`` (Start:End)."""
        path = _sheets_v2_path(spreadsheet_token, "values")
        body = {"valueRange": _value_range(a1_range, values)}
        return self._write("PUT", path, body, context="sheets values put")

    def batch_update_values(self, spreadsheet_token, value_ranges):
        """``POST …/values_batch_update`` — write N ranges in one call.

        ``value_ranges`` is a list of ``{"range", "values"}`` dicts; each range is
        forced to ``Start:End`` (no bare cell can slip through the batch path).
        """
        path = _sheets_v2_path(spreadsheet_token, "values_batch_update")
        body = {
            "valueRanges": [
                _value_range(vr["range"], vr["values"]) for vr in value_ranges
            ]
        }
        return self._write("POST", path, body, context="sheets values batch update")

    def append_values(self, spreadsheet_token, a1_range, values,
                      insert_data_option=None):
        """``POST …/values_append`` — append after the range's used rows.

        Default (``insert_data_option=None``) is the **non-structural**
        overwrite-in-place / used-range append. The **structural** ``INSERT_ROWS``
        variant (which shifts rows) is opt-in via ``insert_data_option`` and is
        otherwise deliberately parked.
        """
        path = _sheets_v2_path(spreadsheet_token, "values_append")
        if insert_data_option:
            path += "?" + urllib.parse.urlencode(
                {"insertDataOption": insert_data_option}
            )
        body = {"valueRange": _value_range(a1_range, values)}
        return self._write("POST", path, body, context="sheets values append")

    def prepend_values(self, spreadsheet_token, a1_range, values):
        """``POST …/values_prepend`` — insert before the range, shifting existing
        rows down."""
        path = _sheets_v2_path(spreadsheet_token, "values_prepend")
        body = {"valueRange": _value_range(a1_range, values)}
        return self._write("POST", path, body, context="sheets values prepend")

    # -- v2 dropdown-rule write (LD-120) --------------------------------- #

    def set_data_validation(self, spreadsheet_token, a1_range, rule):
        """``POST …/dataValidation`` — set a dropdown (list) rule on ``a1_range``.

        The **dataValidation family** endpoint: ``rule`` is the encoder's
        (:func:`~larkdocio.sheets.rich_encode.encode_dropdown_rule`) range-independent
        ``{"dataValidationType":"list","dataValidation":{"conditionValues":[…],"options":{…}}}``
        payload; this op prepends the target ``range`` (forced to ``Start:End`` — the
        ``90202`` guard, so a bare single cell is structurally impossible on the wire) and
        POSTs the body. The encoder owns the **`90204`** colors caveat (a
        ``highlightValidData:true`` without a 1:1 ``colors`` array is refused **before** this
        write, a typed
        :class:`~larkdocio.sheets.rich_encode.DropdownColorsError`); a server-side ``90204``
        (or any non-zero code) still surfaces typed via :func:`raise_for_lark_code`. The rule
        write rides the shared ≤3/s WRITE throttle like every other write op. Not a
        value-write — it flows through the gated apply engine as a
        :class:`~larkdocio.sheets.write_apply.DropdownRuleWriteRequest`.
        """
        path = _sheets_v2_path(spreadsheet_token, "dataValidation")
        body = {"range": normalize_write_range(a1_range), **rule}
        return self._write("POST", path, body, context="sheets data validation set")

    # -- v2 cell-STYLE writes (LD-188) ------------------------------------ #

    def put_style(self, spreadsheet_token, a1_range, style):
        """``PUT …/style`` — set one cell style on ``a1_range`` (``appendStyle``).

        ``style`` is the wire dict :meth:`~larkdocio.sheets.requests.CellStyle.wire` builds
        (``{"font": {...}, "backColor", "foreColor", "formatter"}``); this op wraps it in the
        ``appendStyle`` envelope with the target range forced to ``Start:End`` — the ``90202``
        guard, and a **captured** one on this very endpoint: a bare single cell answers
        ``90202 wrong range=<sheet_id>!B2`` (captured in
        ``tests/captures/sheets-write-spike/captures/01-endpoint-matrix.json`` (in the source repository) and
        re-probed since, on a
        throwaway spreadsheet of our own).

        The reply carries its post-write ``revision`` **nested**, at ``data.updates.revision``
        (probed), which is why the apply leg looks inside that envelope before falling back to
        a ``metainfo`` read.

        Not called directly in the normal path: a style write flows through the gated engine as
        a :class:`~larkdocio.sheets.requests.StyleWriteRequest` (``dry_run`` → ``apply``,
        revision compare-and-swap), whose plan discloses that **verifying** a style needs the
        asynchronous whole-workbook xlsx export.
        """
        # HISTORY (contributor-facing, deliberately in a comment): this implementation lived in
        # tests/sheets_write_harness.py::SheetsStyleWriter, where the style-leg fidelity gate had
        # been writing {"font":{"bold":true},"backColor":"#FFFF00","formatter":"0.00%"} nightly
        # since LD-118 while the wheel itself could not set a style at all. LD-188 promoted it
        # here; the harness now passes this client as its styler.
        path = _sheets_v2_path(spreadsheet_token, "style")
        body = {"appendStyle": {"range": normalize_write_range(a1_range), "style": style}}
        return self._write("PUT", path, body, context="sheets style put")

    def batch_update_styles(self, spreadsheet_token, style_ranges):
        """``PUT …/styles_batch_update`` — N styles over N ranges in ONE call.

        ``style_ranges`` is a list of ``{"ranges": [...], "style": {...}}`` dicts (the ``data``
        array the endpoint takes, which
        :meth:`~larkdocio.sheets.requests.BatchStyleWriteRequest.wire_data` builds). **Every
        range is forced to ``Start:End`` here too.** This project's own coverage notes recorded
        this form as immune to the bare-cell ``90202`` trap because it takes a ``ranges`` array,
        and that is **false** — probed live, ``{"ranges": ["<sheet_id>!C1"]}`` answered
        ``90202 wrong range=<sheet_id>!C1`` exactly like the single-range op. The reply carries
        **no** ``revision`` at all (only per-range ``responses``), so the apply leg reads it
        back from ``metainfo`` rather than guessing.
        """
        path = _sheets_v2_path(spreadsheet_token, "styles_batch_update")
        body = {
            "data": [
                {"ranges": [normalize_write_range(r) for r in item["ranges"]],
                 "style": item["style"]}
                for item in style_ranges
            ]
        }
        return self._write("PUT", path, body, context="sheets styles batch update")

    # -- v2 structural dimension writes (LD-121) -------------------------- #

    def insert_dimension_range(self, spreadsheet_token, sheet_id, major_dimension,
                               start_index, end_index, inherit_style=None):
        """``POST …/insert_dimension_range`` — insert blank rows/cols at a NATIVE span.

        The insert endpoint's native convention is **0-indexed, half-open
        ``[start_index, end_index)``** — ``[1, 2)`` inserts **one** blank
        row at 0-index 1 and shifts everything at ≥1 down by one. This client is the
        **faithful native transport**: it places ``start_index`` / ``end_index`` on the
        wire verbatim (never reinterpreting them) — the insert-vs-delete index-convention
        guard lives one layer up, in the gated request objects
        (:class:`~larkdocio.sheets.write_apply.InsertRowsAt` /
        :class:`~larkdocio.sheets.write_apply.InsertColsAt`), which is the **only**
        caller-facing structural surface (a raw index is never hand-built by a caller).

        The byte-exact capture carries **no** ``inheritStyle`` key, so it is an off-by-
        default optional extra: omitted unless ``inherit_style`` is passed. The reply's
        ``data`` is ``{}`` (no count) — the requested span width is the authoritative
        add-count; the gated engine re-reads geometry to confirm the shift.
        """
        path = _sheets_v2_path(spreadsheet_token, "insert_dimension_range")
        dimension = {
            "sheetId": sheet_id,
            "majorDimension": major_dimension,
            "startIndex": start_index,
            "endIndex": end_index,
        }
        body = {"dimension": dimension}
        if inherit_style is not None:
            body["inheritStyle"] = inherit_style
        return self._write("POST", path, body, context="sheets insert dimension range")

    def delete_dimension_range(self, spreadsheet_token, sheet_id, major_dimension,
                               start_index, end_index):
        """``DELETE …/dimension_range`` — delete rows/cols at a NATIVE span; reply carries
        ``delCount``.

        The delete endpoint's native convention is **1-indexed, INCLUSIVE
        ``[start_index, end_index]``** — ``[2, 3]`` removes the 2 rows at
        0-index 1 and 2 and returns ``delCount: 2``. This is the load-bearing asymmetry
        against the 0-idx half-open **insert** span above; the client passes the indices
        to the wire verbatim (the semantic→native conversion lives in the gated
        :class:`~larkdocio.sheets.write_apply.DeleteRows` /
        :class:`~larkdocio.sheets.write_apply.DeleteCols` request objects). The gated
        engine **trusts the reply's ``delCount``** and re-reads geometry (never assumes
        parity).
        """
        path = _sheets_v2_path(spreadsheet_token, "dimension_range")
        body = {
            "dimension": {
                "sheetId": sheet_id,
                "majorDimension": major_dimension,
                "startIndex": start_index,
                "endIndex": end_index,
            }
        }
        return self._write("DELETE", path, body, context="sheets delete dimension range")

    def append_dimension(self, spreadsheet_token, sheet_id, major_dimension, length):
        """``POST …/dimension_range`` — append ``length`` blank rows/cols at the grid end.

        The dimension-append (distinct from the ``insert_dimension_range`` at-a-position
        op): the body carries ``length`` (no start/end — an append has no positional
        convention trap), and the reply carries ``addCount``. The gated engine
        **trusts the reply's ``addCount``** and re-reads geometry.
        """
        path = _sheets_v2_path(spreadsheet_token, "dimension_range")
        body = {
            "dimension": {
                "sheetId": sheet_id,
                "majorDimension": major_dimension,
                "length": length,
            }
        }
        return self._write("POST", path, body, context="sheets append dimension range")

    def set_dimension_properties(self, spreadsheet_token, sheet_id, major_dimension,
                                 start_index, end_index, properties):
        """``PUT …/dimension_range`` — set rows'/columns' **height, width, or visibility**.

        The **fourth** verb on the dimension path, and the one whose index convention had to be
        characterized before it could be written, because the other three do not agree with
        each other. All three, side by side:

        * :meth:`insert_dimension_range` — **0-indexed, half-open ``[start, end)``**;
        * :meth:`delete_dimension_range` — **1-indexed, INCLUSIVE ``[start, end]``**;
        * **this one** — **1-INDEXED, INCLUSIVE ``[start_index, end_index]``**, i.e. it
          follows the *delete* convention, **not** the insert one.

        That is **probed, not inferred** (characterized live against throwaway
        spreadsheets before this method existed): ``{startIndex: 2, endIndex: 3}`` with a ``fixedSize`` landed the
        height on sheet rows **2 and 3**; ``startIndex: 0`` is refused outright (``90202 …
        StartIndex or EndIndex must greater than 0``), so a 0-indexed reading is not even
        expressible; and ``{2, 2}`` touches row 2 alone. Guessing it from the insert sibling
        would have resized the wrong rows silently.

        ``properties`` is the ``dimensionProperties`` dict — ``{"visible": bool}`` and/or
        ``{"fixedSize": int}`` (pixels). This client is the **faithful native transport**: it
        places ``start_index`` / ``end_index`` / ``properties`` on the wire verbatim, never
        reinterpreting them; the semantic→native conversion and every plan-time refusal live
        one layer up in the gated request objects
        (:class:`~larkdocio.sheets.requests.SetRowProperties` /
        :class:`~larkdocio.sheets.requests.SetColProperties`), which are the only
        caller-facing surface.

        Probed edges the gated layer refuses before they reach here: an **empty**
        ``properties`` (``90204 dimensionProperties FixedSize and Visible are nil``), a
        **reversed** band (``90202 … EndIndex must greater than or equal to StartIndex``), a
        **negative** ``fixedSize`` (``90204 invalid operation``), a band past the declared grid
        (``90202 … endIndex must less than or equal to sheetMaxRowCount``), and
        ``fixedSize: 0`` — which Lark **accepts** and which **clears the custom size** rather
        than hiding anything.

        The reply ``data`` is ``{}`` (no count, no ``revision``) — the gated engine reads the
        post-write ``revision`` back from ``metainfo``. A property write moves nothing, so
        there is no geometry delta to verify; what a dimension property actually became is
        readable **only** through the xlsx export leg (``metainfo`` and the v3 tab query carry
        no per-row/column height, width or hidden state at all — probed).
        """
        path = _sheets_v2_path(spreadsheet_token, "dimension_range")
        body = {
            "dimension": {
                "sheetId": sheet_id,
                "majorDimension": major_dimension,
                "startIndex": start_index,
                "endIndex": end_index,
            },
            "dimensionProperties": dict(properties or {}),
        }
        return self._write("PUT", path, body, context="sheets set dimension properties")

    def read_sheet_geometry(self, spreadsheet_token, sheet_id):
        """``GET …/sheets/v3/…/sheets/query`` → the named tab's ``{row_count,
        column_count, merges}`` — the MANDATORY structural re-read.

        The gated apply engine re-reads geometry **after every structural write** and
        verifies the observed row/column-count delta against the requested span (never
        assuming the reply's ``addCount``/``delCount`` and the geometry agree). Returns a
        plain dict (``merges`` verbatim — 0-indexed END-inclusive) or ``None`` when the
        ``sheet_id`` is absent (a vanished tab). An un-throttled read (reads are not
        write-rate-limited; WRITE creds — a write's own re-read).
        """
        path = f"/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query"
        data = self._read(path, context="sheets geometry re-read")
        for sheet in (data or {}).get("sheets") or []:
            if sheet.get("sheet_id") == sheet_id:
                grid = sheet.get("grid_properties") or {}
                return {
                    "row_count": grid.get("row_count"),
                    "column_count": grid.get("column_count"),
                    "merges": sheet.get("merges") or [],
                }
        return None

    # -- v2 merge/unmerge + tab writes (LD-122) --------------------------- #

    def merge_cells(self, spreadsheet_token, a1_range, merge_type="MERGE_ALL"):
        """``POST …/merge_cells`` — merge ``a1_range`` (default ``MERGE_ALL``).

        The merge endpoint takes a ``range`` (forced to ``Start:End`` — the ``90202``
        guard, so a bare single cell is structurally impossible on the wire) + a
        ``mergeType``. **Anchor-value semantics:** the top-left cell keeps
        its value; every covered cell's value is DISCARDED — that data loss is previewed
        explicitly by the gated engine (:class:`~larkdocio.sheets.write_apply.MergeCells`)
        before the write. This client is the faithful transport; the merge-aware
        grow/shift/shrink/dissolve reasoning lives one layer up. The reply ``data`` carries
        ``{"spreadsheetToken": …}`` (no ``revision`` — the engine falls back to metainfo).

        **``MERGE_ROWS`` / ``MERGE_COLUMNS`` are refused one layer up, not here.** Lark accepts
        them (they merge one region per row / per column), but larkdocio's loss preview is
        MERGE_ALL's model and over-reports the loss for them, so
        :class:`~larkdocio.sheets.requests.MergeCells` raises
        :class:`~larkdocio.sheets.requests.MergeTypeError` at construction
        (:data:`~larkdocio.sheets.requests.MERGE_VARIANTS_NOT_GATE_COVERED`). This method stays
        the faithful transport and will send whatever ``mergeType`` you hand it — which means a
        raw call here gets **no loss preview**, no dry-run and no compare-and-swap at all, for
        any merge type. Go through the gated engine unless you are deliberately outside it.
        """
        path = _sheets_v2_path(spreadsheet_token, "merge_cells")
        body = {"range": normalize_write_range(a1_range), "mergeType": merge_type}
        return self._write("POST", path, body, context="sheets merge cells")

    def unmerge_cells(self, spreadsheet_token, a1_range):
        """``POST …/unmerge_cells`` — dissolve the merge covering ``a1_range``.

        The unmerge endpoint takes only a ``range`` (forced to ``Start:End`` — the
        ``90202`` guard). After the unmerge the covered cells become independent (empty)
        cells; the anchor retains its value (no value is restored to the covered cells).
        The reply mirrors :meth:`merge_cells` (``{"spreadsheetToken": …}``, no ``revision``).
        """
        path = _sheets_v2_path(spreadsheet_token, "unmerge_cells")
        body = {"range": normalize_write_range(a1_range)}
        return self._write("POST", path, body, context="sheets unmerge cells")

    def batch_update_sheets(self, spreadsheet_token, requests):
        """``POST …/sheets_batch_update`` — tab add / copy / delete.

        The tab-lifecycle endpoint: ``requests`` is the verbatim ``requests[]`` array of
        ``{"addSheet": …}`` / ``{"copySheet": …}`` / ``{"deleteSheet": …}`` objects (the
        gated engine's :class:`~larkdocio.sheets.write_apply.AddTab` /
        :class:`~larkdocio.sheets.write_apply.CopyTab` /
        :class:`~larkdocio.sheets.write_apply.DeleteTab` build them — a caller never
        hand-assembles the wire shape). The reply ``data.replies[]`` is 1:1 with the
        requests; an ``addSheet`` / ``copySheet`` reply carries the **new** tab's
        ``properties.sheetId``, a ``deleteSheet`` reply carries ``{result, sheetId}``. This
        client passes the array through untouched; it never forces a range (no A1 range is
        involved) and never reinterprets a request.
        """
        path = _sheets_v2_path(spreadsheet_token, "sheets_batch_update")
        body = {"requests": requests}
        return self._write("POST", path, body, context="sheets batch update (tabs)")

    def query_tabs(self, spreadsheet_token):
        """``GET …/sheets/v3/…/sheets/query`` → each tab's identity + geometry + merges.

        The write-side tab-identity read (the write app reading its own tab set) — the
        twin of :meth:`~larkdocio.sheets.client.SheetsReadClient.query_sheets`. Returns a
        list of ``{sheet_id, title, index, hidden, row_count, column_count, merges}`` dicts in
        sheet order. The gated engine uses it to snapshot the **removed tab's identity** before
        a destructive tab delete (destructive-safe — the apply-log carries it so a
        consumer could recreate the tab) and to diff the tab set (the tab leg). An
        un-throttled read (reads are not write-rate-limited; WRITE creds — a write's own
        read).

        **``hidden`` lives here and nowhere cheaper.** This is the tab-presentation family's
        verification leg for all three of its fields (``index`` / ``title`` / ``hidden``),
        because ``metainfo`` does **not** report ``hidden`` at all — probed twice, including a
        read taken while a tab really was hidden, whose sheet objects carried only
        ``columnCount`` / ``frozenColCount`` / ``frozenRowCount`` / ``index`` / ``rowCount`` /
        ``sheetId`` / ``title``. Surfacing the field here adds **zero new HTTP**: it was already
        on this endpoint's wire.

        A payload that names no ``hidden`` for a tab yields ``None``, never ``False``: "the
        answer is unknown" and "the tab is visible" are different facts, and the honesty rule
        the frozen read established (:func:`~larkdocio.sheets.models.parse_frozen_panes`)
        applies to this flag too.
        """
        path = f"/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query"
        data = self._read(path, context="sheets tab query (write-side)")
        tabs = []
        for sheet in (data or {}).get("sheets") or []:
            grid = sheet.get("grid_properties") or {}
            raw_hidden = sheet.get("hidden")
            tabs.append({
                "sheet_id": sheet.get("sheet_id"),
                "title": sheet.get("title"),
                "index": sheet.get("index"),
                "hidden": raw_hidden if isinstance(raw_hidden, bool) else None,
                "row_count": grid.get("row_count"),
                "column_count": grid.get("column_count"),
                "merges": sheet.get("merges") or [],
            })
        return tabs

    # -- v2 write-side reads for the gated apply engine (S3/LD-111) ------- #

    def read_revision(self, spreadsheet_token):
        """``GET …/metainfo`` → ``data.properties.revision`` — the compare-and-swap anchor.

        The gated apply engine (:mod:`larkdocio.sheets.write_apply`) caches this at plan
        time and re-reads it immediately before **each** write, refusing ``STALE_SHEET``
        if it advanced (every write bumps ``revision`` +1, reads never do).
        The dimension replies omit ``revision`` so it is read from ``metainfo`` here. An
        un-throttled read (WRITE creds — a write's own compare-and-swap read).
        """
        data = self._read(
            _sheets_v2_path(spreadsheet_token, "metainfo"),
            context="sheets metainfo revision",
        )
        return ((data or {}).get("properties") or {}).get("revision")

    def read_frozen_panes(self, spreadsheet_token, sheet_id=None):
        """``GET …/metainfo`` → each tab's **frozen row/column counts** + its grid + the
        spreadsheet ``revision``, in ONE call — the freeze family's verification leg.

        The write-side twin of
        :meth:`~larkdocio.sheets.client.SheetsReadClient.get_frozen_panes` (WRITE creds — a
        write's own plan-time read and post-write read-back), returning plain dicts in this
        client's house style rather than the read client's typed
        :class:`~larkdocio.sheets.models.FrozenPanes`.

        ``metainfo`` earns its place here by answering **four** questions in one un-throttled
        read, which is why the freeze preview costs exactly one call: what is frozen now (so the
        plan can disclose a freeze that replaces an existing one), what the grid is (the
        plan-time out-of-range refusal), which tabs exist (the ``UNKNOWN_TAB`` split), and the
        current ``revision`` (the compare-and-swap anchor). Probed live —
        ``tests/captures/sheets-freeze-probe/captures/01-updateSheet-FREEZE-and-metainfo-frozen-read.json``
        (in the source repository).

        Returns ``{"revision": int|None, "sheets": {sheet_id: record}}``, or — with ``sheet_id``
        — that one tab's ``record`` (``None`` when the tab is absent, which is how the preview
        tells "not a tab of this spreadsheet" from "frozen counts unknown"). A record is
        ``{"frozen_rows", "frozen_cols", "row_count", "column_count", "title", "index",
        "source"}``, and a tab whose payload carries **no usable frozen counts** is absent from
        the mapping rather than defaulted to zero: "unknown" must never read as "unfrozen".
        """
        data = self._read(
            _sheets_v2_path(spreadsheet_token, "metainfo"),
            context="sheets metainfo (frozen panes)",
        )
        sheets = {}
        for sheet in (data or {}).get("sheets") or []:
            sid = sheet.get("sheetId")
            panes, _reason = parse_frozen_panes(sheet, source="metainfo")
            if not sid or panes is None:
                continue
            sheets[sid] = {
                "frozen_rows": panes.rows,
                "frozen_cols": panes.cols,
                "row_count": sheet.get("rowCount"),
                "column_count": sheet.get("columnCount"),
                "title": sheet.get("title"),
                "index": sheet.get("index"),
                "source": panes.source,
            }
        state = {
            "revision": ((data or {}).get("properties") or {}).get("revision"),
            "sheets": sheets,
        }
        if sheet_id is None:
            return state
        return sheets.get(sheet_id)

    def validate_user_ids(self, open_ids):
        """``GET …/contact/v3/users/batch`` → which of ``open_ids`` Lark says **do not exist**.

        The plan-time @mention id check the gated engine runs: the failure class that
        used to escape ``apply()`` as a raw ``LarkAPIError: Code 90204, Msg: id not found``
        is caught at ``dry_run`` instead.
        Returns ``{"checked": [...], "resolved": {open_id: name}, "invalid": [...]}``.

        **Falsification-based, because that is what the endpoint actually reports** (probed
        read-only 2026-07-28 with the WRITE app, log_id
        ``20260728152453A52E092131CF9A78E884``):

        * a **nonexistent** id → code ``99992351`` with ``error.field_violations[]`` naming
          that exact id (``{"field": "user_ids", "value": "<id>", "description": "id not
          exist"}``) — **positive, per-id proof**, which is what ``invalid`` carries;
        * a **real** id → code ``0`` with ``items: []`` when the app has no contact *detail*
          scope. So "absent from ``resolved``" is **NOT** evidence of non-existence and is
          never reported as invalid; ``resolved`` is a bonus, not the signal.

        A **mixed** batch is answered by the invalid-ids code as a whole, so the valid ids in
        it simply come back unproven (not invalid) — the check only ever *falsifies*.

        Any **other** non-zero code (a missing scope, an API drift) **raises** the typed
        :class:`~larkdocio.errors.LarkAPIError` — the caller (``ops._validate_mention_ids``)
        turns that into a ``mention_validation: "unavailable"`` disclosure on the plan rather
        than pretending the ids were checked. An un-throttled read (WRITE creds — a write's
        own plan-time read); chunked ≤50 ids/call (the endpoint's limit).
        """
        checked = [i for i in (open_ids or ()) if i]
        result = {"checked": list(checked), "resolved": {}, "invalid": []}
        for start in range(0, len(checked), _USER_BATCH_CHUNK):
            chunk = checked[start:start + _USER_BATCH_CHUNK]
            params = [("user_id_type", "open_id")] + [("user_ids", i) for i in chunk]
            resp = self._raw_request("GET", _CONTACT_USERS_BATCH_PATH, params=params)
            code = (resp or {}).get("code")
            if code is not None and str(code) == str(INVALID_USER_IDS_CODE):
                result["invalid"].extend(_invalid_user_ids(resp, chunk))
                continue
            typed = raise_for_lark_code(
                resp, context="contact user batch (mention check)",
                credential_env=WRITE_ENV)
            data = typed.get("data") if isinstance(typed, dict) else None
            for user in (data or {}).get("items") or []:
                open_id = user.get("open_id")
                name = user.get("name") or user.get("en_name") or user.get("nickname")
                if open_id and name:
                    result["resolved"][open_id] = name
        return result

    def read_value_range(self, spreadsheet_token, a1_range,
                         value_render_option=None):
        """``GET …/values/{range}`` → the whole ``valueRange``: ``{range, revision,
        values, majorDimension}``.

        The **verdict read** for a write whose proof is what the cell now holds rather
        than what the write answered — the in-cell image op
        (:func:`larkdocio.sheets.media.put_image_in_sheet`) needs the range and the
        revision the read itself reports, and :meth:`read_values` deliberately answers only
        the bare matrix.

        ``value_render_option`` defaults to **nothing sent at all**, which is the request
        shape the ``embed-image`` cell value was measured under (the sheets-media spike's
        capture ``203-``, in the source repository). Pass one to ask for a specific rendering; :meth:`read_values`
        does exactly that.

        Un-throttled, like every write-side read (a write's own before/after read never
        spends throttle budget).
        """
        path = _sheets_v2_path(spreadsheet_token, f"values/{a1_range}")
        params = {"valueRenderOption": value_render_option} if value_render_option else None
        data = self._read(path, params=params,
                          context="sheets values read (write-side)")
        return (data or {}).get("valueRange") or {}

    def read_values(self, spreadsheet_token, a1_range,
                   value_render_option="UnformattedValue"):
        """``GET …/values/{range}`` → the **raw** values matrix (``UnformattedValue``).

        The before-snapshot / precondition read for the gated apply engine: the target's
        current **raw** stored values (not a display string), so the compare-and-swap's
        precondition compares like-for-like against the plan's capture. An un-throttled
        read (WRITE creds — a write's own before-read).

        The matrix half of :meth:`read_value_range`, which is the one call; this is what
        every existing caller wants and its shape is unchanged.
        """
        return self.read_value_range(
            spreadsheet_token, a1_range,
            value_render_option=value_render_option).get("values") or []

    # -- v2 IN-CELL IMAGE write (LD-447) ---------------------------------- #

    def put_values_image(self, spreadsheet_token, a1_range, data, name):
        """``POST …/values_image`` — write ``data`` as the **value of one cell**.

        The measured one-call route (the sheets-media spike's capture ``202-``, in the
        source repository): the bytes
        travel **in the JSON body, as an array of integers**, alongside the target range
        (forced to ``Start:End`` — the ``90202`` guard) and a display ``name``. There is
        **no** ``medias/upload_all`` leg on this route at all, and Lark mints its **own**
        media token for the cell.

        **THE INT-ARRAY BODY IS A SIZE CEILING.** One byte becomes up to four characters on
        the wire (``255,``), so the request is roughly **3–4× the file's own size** — a
        consumer sizing an upload budget from the file will under-provision. The exact
        limit is **unmeasured**: only an 88-byte PNG was ever sent.

        Returns the write's own ``data`` (``revision`` / ``updateRange``), which is **not
        a verdict** — an accepted call is not a stored one. The verdict is a fresh
        :meth:`read_value_range`, which is what
        :func:`larkdocio.sheets.media.put_image_in_sheet` does around this call.
        """
        path = _sheets_v2_path(spreadsheet_token, "values_image")
        body = {"range": normalize_write_range(a1_range),
                "image": list(data), "name": name}
        return self._write("POST", path, body, context="sheets values image write")

    # -- v3 FLOAT IMAGE bind / query / remove (LD-448) ---------------------- #

    def create_float_image(self, spreadsheet_token, sheet_id, *, float_image_token,
                           a1_range, width, height, offset_x=0, offset_y=0):
        """``POST …/sheets/{sid}/float_images`` — anchor an uploaded token OVER a range.

        **This is the BIND, and it is the third beat of a three-beat route.** The bytes were
        already uploaded through ``medias/upload_all`` with ``parent_type: sheet_image`` and
        ``parent_node`` = **the spreadsheet token** — *the workbook*, not this tab and not a
        cell; the tab appears for the first time here, in the path and in ``a1_range``. On the
        docx route the upload binds to the **block**, which is why a docx habit misleads here
        (:func:`larkdocio.sheets.media.put_float_image_in_sheet` is the op that does all three
        beats so the order cannot be got wrong from outside).

        ``a1_range`` is forced to ``Start:End`` like every other range this client emits (the
        ``90202`` guard). The measured shape is a single cell, ``"{sheetId}!A1:A1"``;
        multi-cell and merged ranges are **unmeasured, not refuted**.

        **THE ANSWER IS NOT THE VERDICT, and one refusal on this route wears a server error's
        clothes.** Binding a token that was never minted answers **HTTP 500 with
        ``1315203 "Server Error, Retry Later"``** and creates nothing — measured, with the
        re-query that proves no phantom appeared (the sheets-media spike's captures ``108-``
        and ``201-``, in the source repository). It is a **REFUSAL**, so **it must never be retried**:
        nothing here retries it, the refusal is raised typed with Lark's verbatim body, and
        the only thing that establishes what exists is a fresh :meth:`query_float_images`.

        **The bind does NOT police image-vs-file tokens.** A token uploaded with
        ``parent_type: sheet_file`` is **accepted** here with ``code 0`` and is then listed as
        a float image (captures ``207-``/``208-``). Nothing in a token's text says which
        family it came from, so this method relays Lark's acceptance and discloses it rather
        than refusing on a guess; the op above cannot reach that case at all, because it mints
        the token it binds.

        Returns Lark's own ``float_image`` object (``float_image_id``, ``float_image_token``,
        ``range``, ``width``, ``height``, ``offset_x``, ``offset_y``).
        """
        path = _float_images_path(spreadsheet_token, sheet_id)
        body = {
            "float_image_token": float_image_token,
            "range": normalize_write_range(a1_range),
            "width": width,
            "height": height,
            "offset_x": offset_x,
            "offset_y": offset_y,
        }
        try:
            data = self._write("POST", path, body, context="sheets float image create")
        except LarkAPIError as exc:
            # The typed error keeps its class, its code, its msg and Lark's body — only the
            # message grows, by the one authoring of what an error MEANS on this route. A
            # second, paraphrased warning is how two texts drift into disagreeing.
            _disclose(exc, FLOAT_IMAGE_REFUSAL_IS_NOT_A_RETRY)
            raise
        return (data or {}).get("float_image") or {}

    def query_float_images(self, spreadsheet_token, sheet_id):
        """``GET …/sheets/{sid}/float_images/query`` — **the verdict read** for this route.

        The list of float images anchored on one tab. It is the only call that establishes
        what exists: an upload's ``code 0`` is not a bind (a fresh query before any create
        answers ``{"items": []}`` — capture ``105-``) and a delete's ``code 0`` is not a
        removal (capture ``303-``/``304-``).

        A read, so it is un-throttled like every other write-side read. Answers ``[]`` for a
        tab with no float images — an empty tab, never an error.

        **This is the only shipped caller of this route.** No READ-surface op reports a tab's
        float images, so a values read still cannot see one in any form; that gap is disclosed
        in :mod:`larkdocio.sheets.render` rather than implied.
        """
        path = f"{_float_images_path(spreadsheet_token, sheet_id)}/query"
        data = self._read(path, context="sheets float images query")
        return list((data or {}).get("items") or [])

    def delete_float_image(self, spreadsheet_token, sheet_id, float_image_id):
        """``DELETE …/sheets/{sid}/float_images/{id}`` — remove one float image.

        Returns Lark's own reply data. **That reply is not proof.** A ``code 0`` here means
        *accepted*; what proves the picture is gone is a fresh :meth:`query_float_images` no
        longer listing the id (captures ``303-``/``304-``), which is what
        :func:`larkdocio.sheets.media.remove_float_image_from_sheet` does around this call.

        **It does not remove the bytes.** The media token the upload minted is **permanent,
        unpurgeable residue** — **no route in Lark's open API purges drive media, measured,
        not assumed** (the nine spellings tried, the fourteen sends and the scope the claim
        may not exceed are in :data:`larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA`) — and
        neither this delete nor trashing the whole workbook takes the bytes away.
        """
        path = f"{_float_images_path(spreadsheet_token, sheet_id)}/{float_image_id}"
        return self._write("DELETE", path, None, context="sheets float image delete")
