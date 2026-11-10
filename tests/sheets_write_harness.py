"""Leak-proof Sheets self-provision harness (LD-112).

The Sheets twin of the docx ``tests/write_harness.py`` / ``tests/test_live_write_harness.py``
W0 gate. It promotes the LD-107 write spike's proven ``disposable()`` lifecycle
(``dev/sheets-write-spike/probes/_lib.py``) into reusable **test infrastructure** the
write-round-trip gate (S5 / LD-113) builds on: **create → populate → mutate → verify →
DELETE-in-``finally`` → not-found re-query**, with a **persisted ledger** of every created
token and a **zero-orphan close-out** that independently re-queries each ledger token.

**Disposables ONLY (D7 — the load-bearing invariant).** Every write/delete target is a
spreadsheet this harness **self-provisions** — it creates it (v3) and destroys it (drive
v1) in the same run. The harness has **no** code path that reads the scratch-sheet, the
read-canary, or the block-zoo env targets (or any real document) as a write destination —
a token can only ever enter the system through :func:`disposable`'s own create. The static
D7 guard (``tests/test_sheets_write_harness.py``) asserts those target names never appear in
this source. Disposable titles carry
the grep-able ``larkdocio-harness-DISPOSABLE-<nonce>`` prefix so a stray survivor is trivially
findable (and the close-out ledger is the authoritative sweep list).

**Leak-proofing.** Every disposable is created through :func:`disposable`, a context manager
that records the token to a :class:`Ledger` on create and **deletes in a ``finally``** so a
mid-test crash still cleans up. A delete that **fails** (a non-``0``, non-not-found code)
leaves the token in the ledger flagged ``deleted=False`` with its failure code — **never
silently dropped** — so :func:`close_out` (and a human sweep) can still find it. An
already-gone token deletes idempotently (the API returns ``1310249`` — a not-found delete is
treated as "gone").

**The create/delete pair is the SHIPPED one (LD-176).** This harness used to build its own
raw create/delete requests, which made it the only implementation of a lifecycle the library
did not offer — so a consumer following the guide's disposables doctrine had to leave the
library, and the harness's long-proven behavior was unavailable to them. Both operations now
go through the shipped ``SheetsWriteClient.create_spreadsheet`` / ``.delete_spreadsheet``:
**one implementation, and the shipped path is the path every ``live_write`` run exercises.**
The gateway keeps only the two thin adaptations the harness needs — the create result reshaped
for the ledger, and the shipped delete's typed error turned back into the code the ledger
records (a ``finally`` must record an outcome, never raise on the way out of a failing test).

**Structure.** Everything is dependency-injected so the whole lifecycle is offline-unit-
testable (``tests/test_sheets_write_harness.py``): :class:`SheetsLifecycleGateway` takes the
shipped write ``client`` (create + delete) plus a raw ``(method, path, body, params)`` request
callable for the close-out re-query (real: throttled ``urllib`` on the shared core; test: a
recording double); :func:`disposable` / :func:`close_out` depend only
on a gateway's three duck-typed methods (``create_spreadsheet`` / ``delete_spreadsheet`` /
``query_spreadsheet``) plus a :class:`Ledger`. The value-write legs (populate / mutate /
verify) delegate to the same shipped
:class:`~larkdocio.sheets.write_client.SheetsWriteClient`
bound to the disposable's own token. The live cycle is ``tests/test_live_sheets_write_harness.py``.

The one endpoint shape still built here is the close-out re-query,
``GET /open-apis/sheets/v3/spreadsheets/{tok}/sheets/query`` — it needs the RAW reply code
(a gone token answers a non-zero code) to tell "gone" from "still resolves", which a typed
client call raises away.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from larkdocio.common.auth import apply_ipv4_pin, get_write_credentials
from larkdocio.common.transport import (
    WriteTransport,
    api_base,
    fetch_tenant_access_token,
)
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.write_client import (
    SPREADSHEET_GONE_CODE,
    SheetsWriteClient,
    spreadsheet_is_gone,
)

# Lark's "spreadsheet deleted / not found" code — a gone token re-queried returns
# this (LD-107 close-out: all 7 tokens → 1310249). Used to judge "gone" (clean) vs
# "still resolves" (an orphan/leak) and to treat a not-found delete as idempotent.
# THE SHIPPED CONSTANT (LD-176): one definition, so the harness's notion of "gone" and the
# client's cannot drift apart.
NOT_FOUND_CODE = SPREADSHEET_GONE_CODE

# The grep-able disposable-title prefix (D7): every self-provisioned spreadsheet is
# titled ``larkdocio-harness-DISPOSABLE-<nonce>`` so a stray survivor is trivially
# findable by name (the ledger is the authoritative sweep list; this is the backstop).
DISPOSABLE_TITLE_PREFIX = "larkdocio-harness-DISPOSABLE-"

DOMAIN_DEFAULT = "larksuite.com"


class HarnessError(Exception):
    """A harness-lifecycle failure (a create that returned no token, a value-write
    leg used with no writer wired, an orphan leak). Loud by design — the harness
    never silently yields a bogus token or drops a survivor."""


class OrphanLeakError(HarnessError):
    """The zero-orphan close-out found ≥1 ledger token that still resolves — a leak."""


# --------------------------------------------------------------------------- #
# Naming convention (D7)                                                         #
# --------------------------------------------------------------------------- #

def disposable_title(nonce=None):
    """A grep-able disposable title: ``larkdocio-harness-DISPOSABLE-<nonce>``.

    The default nonce is a monotonic-time + pid suffix so concurrent runs never
    collide and every title is unique (the diff/sweep want unambiguous names)."""
    if nonce is None:
        nonce = f"{int(time.time())}-{os.getpid()}"
    return f"{DISPOSABLE_TITLE_PREFIX}{nonce}"


def is_disposable_title(title):
    """True iff ``title`` is a harness-minted disposable title (the D7 marker)."""
    return isinstance(title, str) and title.startswith(DISPOSABLE_TITLE_PREFIX)


# --------------------------------------------------------------------------- #
# Persisted ledger (leak-proofing)                                              #
# --------------------------------------------------------------------------- #

def _now():
    return datetime.now(timezone.utc).isoformat()


def _is_gone_code(code):
    """True for a delete/query code meaning the spreadsheet is gone: ``0`` (deleted OK) or
    either **already-gone** code — the Drive delete's own ``1061007`` (what an idempotent
    double-delete really answers, live-observed 2026-07-30) and the sheets ``1310249`` a call
    against a trashed token answers. Spanning both is what keeps a ``finally``-delete on an
    already-trashed disposable from being recorded as a possible orphan it is not."""
    if code in (0, "0"):
        return True
    # Routed through the shipped predicate (which takes an ERROR, the shape a consumer has)
    # rather than re-listing the codes here — the point is that there is ONE definition of
    # "gone" and the harness reads it rather than keeping a copy.
    return spreadsheet_is_gone(LarkAPIError("gone", code=code))


class Ledger:
    """A persisted JSON ledger of every disposable this harness created.

    One entry per create — ``{spreadsheet_token, title, created_at, deleted,
    delete_code, deleted_at}`` — appended on create and updated on delete. It lives
    on disk (auditable by a human / a sweep script, and survives across processes)
    so a close-out in a later run can still re-query every token. A delete that
    fails leaves ``deleted=False`` with its ``delete_code`` — the token is **flagged,
    never dropped**.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._entries = self._read()

    def _read(self):
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return []

    def _flush(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def record_create(self, token, title):
        self._entries.append({
            "spreadsheet_token": token,
            "title": title,
            "created_at": _now(),
            "deleted": False,
            "delete_code": None,
            "deleted_at": None,
        })
        self._flush()

    def record_delete(self, token, code):
        """Mark ``token``'s delete outcome. ``deleted`` flips True only for a
        gone code (``0`` / ``1310249``); a genuine failure code leaves it False so
        the token stays flagged for the close-out / a sweep (never silently dropped).
        Idempotent — a second (gone) delete keeps ``deleted`` True."""
        for e in self._entries:
            if e["spreadsheet_token"] == token:
                e["deleted"] = bool(e["deleted"]) or _is_gone_code(code)
                e["delete_code"] = code
                e["deleted_at"] = _now()
                break
        self._flush()

    def entries(self):
        return list(self._entries)

    def tokens(self):
        return [e["spreadsheet_token"] for e in self._entries]


# --------------------------------------------------------------------------- #
# Shared throttled WRITE-app transport                                          #
# --------------------------------------------------------------------------- #

def build_throttled_write_request(domain=DOMAIN_DEFAULT, *, throttle=None):
    """A real ``(method, path, body=None, params=None) -> (status, dict)`` request
    callable bound to a WRITE-app tenant token (``LARK_WRITE_APP_*`` — no read/legacy
    fallback; credential doctrine D1), with the shared IPv4 pin applied.

    The single WRITE-app transport the harness's self-provision surfaces share — the
    lifecycle gateway (:meth:`SheetsLifecycleGateway.from_write_credentials`) and the
    probe scripts under ``dev/`` both build on it, so the auth + ≤3/s throttle machinery
    lives in exactly one place. Writes
    (``POST``/``PUT``/``DELETE``) route the shared ≤3/s :class:`WriteTransport`; reads
    (the close-out re-query) bypass it (reads are not write-rate-limited).
    """
    apply_ipv4_pin()
    app_id, app_secret = get_write_credentials()
    base = api_base(domain)
    transport = throttle or WriteTransport()
    token_box = {"v": None}

    def _token():
        if token_box["v"] is None:
            token_box["v"] = fetch_tenant_access_token(app_id, app_secret, domain)
        return token_box["v"]

    def _raw(method, path, body, params):
        url = base + path
        if params:
            url += "?" + urllib.parse.urlencode(params, safe="!:,")
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={
                "Authorization": f"Bearer {_token()}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        try:
            resp = urllib.request.urlopen(req, timeout=40)
            return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def request(method, path, body=None, params=None):
        if method in ("POST", "DELETE", "PUT"):
            return transport.execute(lambda: _raw(method, path, body, params))
        return _raw(method, path, body, params)

    return request


# --------------------------------------------------------------------------- #
# Lifecycle gateway (create v3 / delete drive-v1 / query v3)                     #
# --------------------------------------------------------------------------- #

class SheetsLifecycleGateway:
    """The three self-provision lifecycle ops: create + delete through the **shipped**
    client, and the close-out re-query over an injected raw-``request``.

    ``client`` is the shipped :class:`~larkdocio.sheets.write_client.SheetsWriteClient`
    (or any object exposing its two lifecycle methods): the create/delete pair used to be
    hand-built here, and is not any more — one implementation, exercised by every
    ``live_write`` run (LD-176). ``request`` is a
    ``(method, path, body=None, params=None) -> (status, dict)`` callable — real: a throttled
    ``urllib`` request bound to a WRITE-app tenant token (see :meth:`from_write_credentials`);
    test: a recording double — and it serves the **re-query only**, which needs the raw reply
    code (a gone token answers a non-zero code) that a typed client call raises away.

    Only these three ops exist. None of them accepts an externally-sourced doc URL/token as a
    target (D7): a token enters the system only via :meth:`create_spreadsheet`.
    """

    def __init__(self, request, *, client=None):
        self._request = request
        self._client = client

    def _lifecycle(self):
        if self._client is None:
            raise HarnessError(
                "the lifecycle gateway has no `client` (SheetsWriteClient) wired, so it "
                "cannot create or delete a disposable; build it with "
                "SheetsLifecycleGateway.from_write_credentials(...) or pass client=..."
            )
        return self._client

    def create_spreadsheet(self, title, *, folder_token=None):
        """Create the disposable through the shipped ``create_spreadsheet``, in a named folder.

        ``folder_token`` omitted ⇒ read from ``LARKDOCIO_DISPOSABLES_FOLDER``, and **SKIP
        LOUDLY** when that is unset. The harness obeys the same caller-supplied-destination
        rule the library enforces: it never files a disposable in the application's own space,
        which no human interface can see.

        Returns the shipped call's own ``spreadsheet`` object (``spreadsheet_token``,
        ``title``, ``url``, …) — the shape :func:`disposable` ledgers from. The shipped call
        raises loudly when the reply carries no token, so a bogus disposable can never be
        yielded.
        """
        if folder_token is None:
            import canary_support

            folder_token = canary_support.require_disposables_folder()
        return self._lifecycle().create_spreadsheet(title, folder_token=folder_token)

    def delete_spreadsheet(self, spreadsheet_token):
        """Trash the disposable through the shipped ``delete_spreadsheet``; report a
        ``{"code": …}`` instead of raising.

        The **only** adaptation: the shipped call is loud (a non-zero code raises the typed
        error, including the deleted-token code), while this runs inside a ``finally`` whose
        job is to record an outcome — a teardown that raised on the way out of a failing test
        would replace the real failure with its own. So the typed error becomes the code the
        :class:`Ledger` records: a gone code marks the token deleted (an idempotent
        double-delete), any other code leaves it **flagged, never silently dropped**.
        """
        try:
            data = self._lifecycle().delete_spreadsheet(spreadsheet_token)
        except LarkAPIError as exc:
            return {"code": exc.code, "msg": exc.msg or str(exc)}
        return {"code": 0, "data": data}

    def query_spreadsheet(self, token):
        """``GET /open-apis/sheets/v3/spreadsheets/{tok}/sheets/query`` — the close-out
        re-query; a gone token resolves to a non-zero code (:data:`NOT_FOUND_CODE`)."""
        _status, resp = self._request(
            "GET", f"/open-apis/sheets/v3/spreadsheets/{token}/sheets/query", None, None
        )
        return resp

    @classmethod
    def from_write_credentials(cls, domain=DOMAIN_DEFAULT, *, throttle=None):
        """Build a gateway on the shared throttled WRITE-app transport
        (``LARK_WRITE_APP_*``, no read/legacy fallback, IPv4 pin, ≤3/s throttle): the shipped
        client for create/delete and :func:`build_throttled_write_request` for the re-query,
        **sharing one limiter** so the two seams cannot exceed the write ceiling between them.
        Used only by the live cycle."""
        limiter = throttle or WriteTransport()
        return cls(
            build_throttled_write_request(domain, throttle=limiter),
            client=SheetsWriteClient.from_write_credentials(domain, transport=limiter),
        )


# --------------------------------------------------------------------------- #
# The style-write leg is SHIPPED CODE now (LD-188). It used to live here, as       #
# `SheetsStyleWriter`, because `SheetsWriteClient` had no style op — the wheel     #
# could READ style and not write it. LD-188 promoted it into                       #
# `SheetsWriteClient.put_style` / `.batch_update_styles`, so the harness has no    #
# style writer of its own: pass the shipped client as `styler=` (it satisfies the  #
# same duck type) and the S5 fidelity gate styles through src/ like everything     #
# else. A second implementation here would redden                                  #
# tests/test_sheets_style_write.py's one-implementation guard.                     #
# --------------------------------------------------------------------------- #

def _spreadsheet_of(create_resp):
    """The ``spreadsheet`` object a create handed back, whichever shape it came in.

    Two shapes are accepted deliberately: the shipped
    ``SheetsWriteClient.create_spreadsheet`` returns the ``spreadsheet`` object itself, while a
    duck-typed test gateway may answer the full v3 envelope (``{"code", "data": {...}}``). The
    lifecycle depends on the token and the title, not on which layer unwrapped the reply.
    """
    if not isinstance(create_resp, dict):
        return {}
    if create_resp.get("spreadsheet_token"):
        return create_resp
    data = create_resp.get("data") or {}
    return data.get("spreadsheet") or {}


def _extract_token(create_resp):
    """Dig the ``spreadsheet_token`` out of a create result, or ``None``."""
    return _spreadsheet_of(create_resp).get("spreadsheet_token")


def _extract_title(create_resp):
    """The title a create result reports, or ``None`` (the requested title is the fallback)."""
    return _spreadsheet_of(create_resp).get("title")


def _first_sheet_id(query_resp):
    sheets = ((query_resp.get("data") or {}).get("sheets") or []) if isinstance(query_resp, dict) else []
    return sheets[0].get("sheet_id") if sheets else None


# --------------------------------------------------------------------------- #
# The disposable() context manager (the core lifecycle)                          #
# --------------------------------------------------------------------------- #

@dataclass
class Disposable:
    """A live disposable spreadsheet, bound to its OWN token (D7).

    The value-write legs (:meth:`put_values` / :meth:`append_values` /
    :meth:`read_values`) delegate to the injected LD-109 ``SheetsWriteClient`` with
    ``self.token`` bound — there is no way to point them at another document. Ranges
    are ``{sheet_id}!A1:B2`` forms the caller builds from :attr:`first_sheet_id`.
    """

    token: str
    first_sheet_id: str
    create_resp: dict
    #: the title this disposable really carries — read off the create result, falling back to
    #: the requested one. Exposed as a field (rather than dug out of ``create_resp`` by every
    #: caller) because the create result's shape is the gateway's business, not a gate's.
    title: str = ""
    writer: object = None
    styler: object = None

    def _require_writer(self):
        if self.writer is None:
            raise HarnessError(
                "value-write leg used but no `writer` (SheetsWriteClient) was wired "
                "into disposable(); pass writer=... to populate/verify."
            )
        return self.writer

    def _require_styler(self):
        if self.styler is None:
            raise HarnessError(
                "style-write leg used but no `styler` was wired into disposable(); pass "
                "styler=<SheetsWriteClient> to write cell styles (LD-188 promoted the style "
                "write onto the shipped client, so the value writer IS the styler)."
            )
        return self.styler

    def put_values(self, a1_range, values):
        return self._require_writer().put_values(self.token, a1_range, values)

    def put_style(self, a1_range, style):
        """Write ``style`` to ``a1_range`` on THIS disposable (bound to its own token —
        D7). Delegates to the injected styler's ``put_style`` — the shipped
        :class:`~larkdocio.sheets.write_client.SheetsWriteClient` since LD-188."""
        return self._require_styler().put_style(self.token, a1_range, style)

    def append_values(self, a1_range, values, insert_data_option=None):
        return self._require_writer().append_values(
            self.token, a1_range, values, insert_data_option=insert_data_option
        )

    def read_values(self, a1_range, value_render_option="UnformattedValue"):
        return self._require_writer().read_values(
            self.token, a1_range, value_render_option=value_render_option
        )


@contextmanager
def disposable(gateway, ledger, *, title=None, writer=None, styler=None, folder_token=None):
    """Create a disposable spreadsheet, yield a :class:`Disposable`, and ALWAYS delete
    it in ``finally`` (recording create + delete to ``ledger``).

    A create that returns no token raises :class:`HarnessError` **before** anything is
    ledgered (loud; no bogus yield, no orphan delete attempt). Once created, the token
    is ledgered immediately, so even a crash between create and yield still leaves the
    token on the sweep list and the ``finally`` still deletes it.

    ``writer`` wires the value legs (:class:`~larkdocio.sheets.write_client.SheetsWriteClient`);
    ``styler`` wires the style leg (the same shipped client — LD-188 put ``put_style`` on
    it). Both bind to the
    disposable's own token (D7); either may be omitted when its leg is unused.
    """
    if title is None:
        title = disposable_title()
    create_resp = gateway.create_spreadsheet(title, folder_token=folder_token)
    token = _extract_token(create_resp)
    if not token:
        code = create_resp.get("code") if isinstance(create_resp, dict) else None
        raise HarnessError(
            f"disposable create failed (code={code}) — no spreadsheet_token in "
            f"response; nothing ledgered. resp={create_resp!r}"
        )
    ledger.record_create(token, title)
    try:
        first_sheet_id = _first_sheet_id(gateway.query_spreadsheet(token))
        yield Disposable(
            token, first_sheet_id, create_resp,
            title=_extract_title(create_resp) or title,
            writer=writer, styler=styler,
        )
    finally:
        resp = gateway.delete_spreadsheet(token)
        code = resp.get("code") if isinstance(resp, dict) else None
        ledger.record_delete(token, code)


# --------------------------------------------------------------------------- #
# Zero-orphan close-out (the independent audit)                                  #
# --------------------------------------------------------------------------- #

@dataclass
class CloseOutReport:
    """The result of a close-out sweep over a ledger.

    ``orphans`` are the tokens that STILL resolve (a leak); ``clean`` are the gone
    ones. :attr:`all_clean` / :meth:`raise_if_orphans` are the loud-failure surface.
    """

    ledger_count: int
    orphans: list = field(default_factory=list)
    clean: list = field(default_factory=list)

    @property
    def all_clean(self):
        return not self.orphans

    def raise_if_orphans(self):
        if self.orphans:
            tokens = ", ".join(o["token"] for o in self.orphans)
            raise OrphanLeakError(
                f"close-out found {len(self.orphans)} orphan disposable(s) still "
                f"resolving (a leak): {tokens}. Sweep them (drive v1 delete) — the "
                f"ledger is the authoritative list."
            )


def close_out(gateway, ledger):
    """Independently re-query EVERY ledger token and report orphans loudly.

    A token whose re-query returns ``code 0`` still resolves → an **orphan** (a leak);
    any non-zero code (``1310249`` deleted/not-found) → **gone** (clean). This is the
    zero-orphan proof: the ledger is the create-side record, and this pass is the
    independent delete-side confirmation (the LD-107 close-out shape)."""
    orphans, clean = [], []
    for e in ledger.entries():
        token = e["spreadsheet_token"]
        resp = gateway.query_spreadsheet(token)
        code = resp.get("code") if isinstance(resp, dict) else None
        still_resolves = code in (0, "0")
        record = {
            "token": token,
            "title": e.get("title"),
            "recheck_code": code,
            "still_resolves": still_resolves,
        }
        (orphans if still_resolves else clean).append(record)
    return CloseOutReport(ledger_count=len(ledger.entries()), orphans=orphans, clean=clean)
