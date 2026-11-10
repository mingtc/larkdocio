"""larkdocio.base.ops — the Base op registry, with an EXPLICIT ``mutates`` flag (LD-247).

**Why the flag is declared and never derived.** Three of the Base family's reads are
``POST``: ``…/records/search``, ``…/records/batch_get`` and ``/drive/v1/metas/batch_query``.
A registry that inferred "this mutates" from the HTTP verb would therefore classify *the
pinned record read* as a write — and every downstream thing that keys on the flag (LD-252
consumes it as the read-only proof) would inherit the mistake. So ``mutates`` is a mandatory
field with **no default**: a descriptor cannot be added without answering the question, and
the answer is not a function of the verb.

The other two fields are the opposite kind: ``endpoint`` and ``http_method`` are stated here
but **cross-checked against the SDK request class itself** by the guard, so a descriptor
cannot drift away from the call it actually builds. The shape follows
``larkdocio.sheets.ops.SheetsOpDescriptor`` — one frozen descriptor per family, gathered in
one ordered table that is *the* registration seam.

Every op in this module is a **read**. The Base surface is read-only end to end, and
:func:`read_only` makes that mechanically checkable rather than merely intended.
"""
from dataclasses import dataclass
from typing import Callable, Tuple

from lark_oapi.api.bitable.v1 import (
    BatchGetAppTableRecordRequest,
    GetAppRequest,
    ListAppTableFieldRequest,
    ListAppTableRequest,
    GetAppTableViewRequest,
    ListAppTableViewRequest,
    SearchAppTableRecordRequest,
)
from larkdocio.common.citations import dev_repo


@dataclass(frozen=True)
class BaseOpDescriptor:
    """One Base read op: what it calls, on which verb, and whether it mutates.

    * ``name`` — the op's name, and the name of the client method that implements it;
    * ``endpoint`` — the Lark path, cross-checked against ``request_cls``' own ``uri``;
    * ``http_method`` — the verb, likewise cross-checked. Recorded so the reader can *see*
      that a ``POST`` op declares ``mutates: False``;
    * ``mutates`` — **mandatory, explicit, never inferred**;
    * ``paged`` — whether the op follows a cursor to exhaustion;
    * ``request_cls`` — the pinned-SDK request class the client builds (D2: SDK-typed);
    * ``evidence`` — where this op was proven to work on a live Base.
    """

    name: str
    endpoint: str
    http_method: str
    mutates: bool
    paged: bool
    request_cls: type
    evidence: str


_CAPTURES = "tests/captures/base-study/captures"

#: The ordered registry — the ONE place a Base read op is declared.
OPS: Tuple[BaseOpDescriptor, ...] = (
    BaseOpDescriptor(
        name="get_app",
        endpoint="/open-apis/bitable/v1/apps/:app_token",
        http_method="GET",
        mutates=False,
        paged=False,
        request_cls=GetAppRequest,
        evidence=dev_repo(f"{_CAPTURES}/00-app-meta.json · {_CAPTURES}/p1-q0-01-app-meta.json"),
    ),
    BaseOpDescriptor(
        name="list_tables",
        endpoint="/open-apis/bitable/v1/apps/:app_token/tables",
        http_method="GET",
        mutates=False,
        paged=True,
        request_cls=ListAppTableRequest,
        evidence=dev_repo(f"{_CAPTURES}/00-tables.json · {_CAPTURES}/p1-q0-02-tables.json"),
    ),
    BaseOpDescriptor(
        name="list_views",
        endpoint="/open-apis/bitable/v1/apps/:app_token/tables/:table_id/views",
        http_method="GET",
        mutates=False,
        paged=True,
        request_cls=ListAppTableViewRequest,
        evidence=dev_repo(f"{_CAPTURES}/01-views.json · {_CAPTURES}/p1-q0-03-per-table.json"),
    ),
    BaseOpDescriptor(
        name="get_view",
        endpoint="/open-apis/bitable/v1/apps/:app_token/tables/:table_id/views/:view_id",
        http_method="GET",
        mutates=False,
        paged=False,
        request_cls=GetAppTableViewRequest,
        # WHY THIS OP EXISTS, and it is not for L1's rendering: the LIST endpoint above does
        # NOT return a view's `property` at all — measured live 2026-08-04, where the same view
        # came back with `filter_info` from `GET …/views/{id}` and with the key absent entirely
        # from `GET …/views`. So a view write's READ-BACK cannot be done from the listing, and
        # this is the read that verifies it.
        evidence=dev_repo(f"{_CAPTURES}/p0-3-02-view-patch.json · tests/test_live_base_views.py"),
    ),
    BaseOpDescriptor(
        name="list_fields",
        endpoint="/open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields",
        http_method="GET",
        mutates=False,
        paged=True,
        request_cls=ListAppTableFieldRequest,
        evidence=dev_repo(f"{_CAPTURES}/01-fields.json · {_CAPTURES}/p1-q0-03-per-table.json"),
    ),
    BaseOpDescriptor(
        # THE POST READ. `mutates: False` is a declaration, and this row is why the flag
        # cannot be derived from `http_method`.
        name="search_records",
        endpoint="/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/search",
        http_method="POST",
        mutates=False,
        paged=True,
        request_cls=SearchAppTableRecordRequest,
        evidence=(dev_repo(f"{_CAPTURES}/01-records-search-POST.json · "
                  f"{_CAPTURES}/p1-q1-01-pagination-anomaly.json")),
    ),
    BaseOpDescriptor(
        # THE SECOND POST READ (LD-269), and the one opt-in link resolution spends on. It is
        # not paged: the caller names the ids, so the answer is bounded by the ask and the
        # chunking happens above this line rather than behind a cursor.
        name="batch_get_records",
        endpoint="/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/batch_get",
        http_method="POST",
        mutates=False,
        paged=False,
        request_cls=BatchGetAppTableRecordRequest,
        evidence=dev_repo(f"{_CAPTURES}/03-records-batch-get.json"),
    ),
)


def op(name: str) -> BaseOpDescriptor:
    """The descriptor named ``name``."""
    for descriptor in OPS:
        if descriptor.name == name:
            return descriptor
    raise KeyError(name)


def impl_of(descriptor: BaseOpDescriptor) -> Callable:
    """The client method that implements an op.

    Resolved lazily by name: the client imports this module for its descriptors, so the
    reverse direction cannot be a module-level import.
    """
    from larkdocio.base.client import BaseReadClient

    return getattr(BaseReadClient, descriptor.name)


def read_only() -> bool:
    """``True`` when no registered op mutates — the read-only proof LD-252 AC3 consumes."""
    return all(descriptor.mutates is False for descriptor in OPS)
