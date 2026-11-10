"""larkdocio.base.write_client — the throttled, typed Base **record-write** client.

The write half of the transport seam. One client, six record families, one throttle, and the
same typed error taxonomy the read client refuses through — with the actionable half of the
message attached, so a refusal tells the caller what to do instead of only what failed.

**WRITE credentials only.** The pair is resolved through :mod:`larkdocio.common.auth`'s write
getter, which has **no fallback**: a read-only app is never silently promoted to run a write.
``LARK_READ_APP_*`` is never consulted here and is not named anywhere in this module.

*The aliasing rider, binding.* On the tenant these measurements were made on, the read and write
credential pairs **named one app**. The library keeps treating them as distinct — it must never
infer one from the other or fall back across them — and, just as importantly, **no probe run on
that tenant may be cited as proof of scope separation**. An isolation test passing here proves
that the code asked for the write pair; it cannot prove the read app lacks write scope, because
on that tenant it does not. That claim needs a genuinely separate app.

**R12 — the discipline this module is built around.** Lark's Base API **silently ignores body
keys it does not recognise**: the bogus control ``{"zzz": 1}`` and four plausible grouping keys
all behave identically to ``{}``, and ``page_size`` placed in the body is dropped while the same
parameter in the query string works. So ``code:0`` proves that a request was accepted, never
that a parameter was honoured. Two consequences are built in.

* **By construction:** every request is assembled from the pinned SDK's typed builders, never a
  hand-written dict, so a key cannot be misspelled or misplaced without the builder refusing it.
* **By restraint:** each call sends exactly the keys its endpoint reads, and nothing else. Every
  parameter this module ships carries a test asserting the answer **differs from the
  parameter-free control**, and a deliberate-defect check moves one parameter to the wrong place
  to prove the discipline reddens rather than merely being stated.

**The keys, and the trap inside them.** ``create`` and ``update`` carry ``fields``.
``batch_create`` / ``batch_update`` carry ``records``. So does ``batch_delete`` — a list of
record ids under the key ``records``, **not** ``record_ids``, which is the neighbouring
``batch_get``'s key. Sending the neighbour's key is the exact wrong-place shape the server
answers with silence, so the shipped body is pinned by a test rather than by a reading of the
docs.

**What is deliberately NOT sent.** ``user_id_type`` (this rung writes no person value, so no
test could prove the id form changed anything), ``client_token`` (an idempotency key whose
effect no offline test can demonstrate) and ``ignore_consistency_check`` (it weakens a guarantee
this rung has no reason to weaken). An unprovable parameter does not ship.

**Be gentle.** Every call passes one shared
:class:`~larkdocio.common.transport.RateLimiter` first, at the spacing the three probe packs
actually sustained — 483 live calls at ≥1.2 s with no limit met. Rate limits were
**deliberately not probed** and are not probed here; the posture is documented from that
evidence, and there is no retry-on-rate-limit loop in this module because that would be a probe
by another name.

**No schema write, no cell-value encoding.** This client sends whatever value mapping it is
handed; deciding what a Location or an Attachment value looks like belongs to the encoder, and
creating or altering fields, tables and views is a later rung. Every op here is a record op.
"""
from typing import Dict, Iterable, List, Sequence, Tuple

from lark_oapi.api.bitable.v1 import (
    AppTableRecord,
    BatchCreateAppTableRecordRequest,
    BatchCreateAppTableRecordRequestBody,
    BatchDeleteAppTableRecordRequest,
    BatchDeleteAppTableRecordRequestBody,
    BatchUpdateAppTableRecordRequest,
    BatchUpdateAppTableRecordRequestBody,
    CreateAppTableRecordRequest,
    DeleteAppTableRecordRequest,
    UpdateAppTableRecordRequest,
)

from larkdocio.base.errors import raise_for_base_code
from larkdocio.common.auth import WRITE_ENV, get_write_credentials
from larkdocio.common.sdk_client import (
    require_credentials,
    resolve_rate_limiter,
    resolve_sdk_client,
)

#: The window the pace is expressed over: one minute.
BASE_WRITE_RATE_WINDOW_SECONDS = 60.0

#: Client-side cap per :data:`BASE_WRITE_RATE_WINDOW_SECONDS`. 50/minute is a **1.2 s**
#: spacing — the pace the three probe packs sustained across 483 live calls without meeting a
#: limit. A number measured in this repository's own evidence, not read off a doc page.
DEFAULT_MAX_WRITES_PER_WINDOW = 50


class BaseWriteClient:
    """Writes records to a Base: create, update and delete, singly or in one batch.

    ``sdk_client`` and ``rate_limiter`` are injectable so request construction, pacing and
    error typing are all testable without a network — the read client's shape. The defaults
    are a real SDK client built from the supplied credentials and a limiter at
    :data:`DEFAULT_MAX_WRITES_PER_WINDOW` per :data:`BASE_WRITE_RATE_WINDOW_SECONDS`.
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        domain: str = "larksuite.com",
        *,
        sdk_client=None,
        rate_limiter=None,
        timeout: int = 30,
    ):
        self._domain = domain
        self._api_calls = 0
        self._limiter = resolve_rate_limiter(
            rate_limiter, DEFAULT_MAX_WRITES_PER_WINDOW, BASE_WRITE_RATE_WINDOW_SECONDS)
        self._sdk = resolve_sdk_client(
            sdk_client, app_id, app_secret, domain, timeout=timeout,
            no_credentials="Cannot write a Base: no credentials were resolved")

    @classmethod
    def from_write_credentials(cls, domain: str = "larksuite.com", **kwargs):
        """Build from the environment's WRITE credentials.

        The write getter has no fallback, so an environment carrying only read credentials
        fails here with a typed configuration error rather than quietly making a write attempt
        on a read-only app.
        """
        app_id, app_secret = get_write_credentials()
        require_credentials(
            app_id, app_secret,
            "Cannot write a Base: no write credentials in the environment")
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
                                   credential_env=WRITE_ENV)

    # ---- the operations --------------------------------------------------- #

    def create_record(self, app_token: str, table_id: str,
                      fields: Dict[str, object]) -> AppTableRecord:
        """Create one record. ``fields`` is the only key on the wire.

        Returns the server's **create echo** — which is a third encoding of a row, distinct
        from both record read routes, so it is returned as the typed record rather than
        re-shaped into something that looks like a read.
        """
        body = AppTableRecord.builder().fields(fields).build()
        request = CreateAppTableRecordRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .request_body(body) \
            .build()
        response = self._checked(self._sdk.bitable.v1.app_table_record.create, request,
                                 f"create a record in table {table_id}")
        return response.data.record

    def update_record(self, app_token: str, table_id: str, record_id: str,
                      fields: Dict[str, object]) -> AppTableRecord:
        """Update one record. Only the named fields are touched; the rest are left alone."""
        body = AppTableRecord.builder().fields(fields).build()
        request = UpdateAppTableRecordRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .record_id(record_id) \
            .request_body(body) \
            .build()
        response = self._checked(self._sdk.bitable.v1.app_table_record.update, request,
                                 f"update record {record_id} in table {table_id}")
        return response.data.record

    def delete_record(self, app_token: str, table_id: str, record_id: str) -> bool:
        """Delete one record, returning whether the server reported it deleted.

        **There is no trash for a record.** A deleted record is gone: re-fetching its id
        answers ``RecordIdNotFound`` rather than an empty result, so a caller cannot undo this
        by reading the row back.
        """
        request = DeleteAppTableRecordRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .record_id(record_id) \
            .build()
        response = self._checked(self._sdk.bitable.v1.app_table_record.delete, request,
                                 f"delete record {record_id} from table {table_id}")
        return bool(getattr(response.data, "deleted", False))

    def batch_create_records(self, app_token: str, table_id: str,
                             rows: Iterable[Dict[str, object]]) -> List[AppTableRecord]:
        """Create many records in one call, in the order given."""
        records = [AppTableRecord.builder().fields(row).build() for row in rows]
        body = BatchCreateAppTableRecordRequestBody.builder().records(records).build()
        request = BatchCreateAppTableRecordRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .request_body(body) \
            .build()
        response = self._checked(self._sdk.bitable.v1.app_table_record.batch_create, request,
                                 f"create records in table {table_id}")
        return list(response.data.records or ())

    def batch_update_records(self, app_token: str, table_id: str,
                             updates: Iterable[Tuple[str, Dict[str, object]]]
                             ) -> List[AppTableRecord]:
        """Update many records in one call. ``updates`` is ``(record_id, fields)`` pairs.

        One batch moves the table's revision **once**, not once per record — which is what
        makes a batch the right shape for a compare-and-swap guard rather than merely faster.
        """
        records = [
            AppTableRecord.builder().record_id(record_id).fields(fields).build()
            for record_id, fields in updates
        ]
        body = BatchUpdateAppTableRecordRequestBody.builder().records(records).build()
        request = BatchUpdateAppTableRecordRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .request_body(body) \
            .build()
        response = self._checked(self._sdk.bitable.v1.app_table_record.batch_update, request,
                                 f"update records in table {table_id}")
        return list(response.data.records or ())

    def batch_delete_records(self, app_token: str, table_id: str,
                             record_ids: Sequence[str]) -> List:
        """Delete many records in one call.

        The body key is ``records`` — a list of record ids. The neighbouring batch **read**
        keys its own body ``record_ids``, and sending that key here is silently ignored rather
        than refused, so the shipped shape is pinned by a test instead of by memory.
        """
        body = BatchDeleteAppTableRecordRequestBody.builder() \
            .records(list(record_ids)) \
            .build()
        request = BatchDeleteAppTableRecordRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .request_body(body) \
            .build()
        response = self._checked(self._sdk.bitable.v1.app_table_record.batch_delete, request,
                                 f"delete records from table {table_id}")
        return list(response.data.records or ())
