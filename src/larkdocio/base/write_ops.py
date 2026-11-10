"""larkdocio.base.write_ops — the Base **record-write** op registry.

**A second registry, not an appended row — and that is the whole design.** The read registry
(:mod:`larkdocio.base.ops`) ships a helper, ``read_only()``, that answers *"does any registered
op mutate?"*. Three landed test files assert it is ``True``, two of them live gates that run
against a real Base, and the capability registry repeats the claim to consumers in shipped
text. Appending a mutating descriptor to that tuple would flip the helper and turn a true
shipped statement into a false one — while the surface it describes had not changed at all. So
the write descriptors live here, in their own ordered table with their own accessor, and *"is
this op set read-only?"* stays a question each registry answers about itself.

``mutates`` is declared **explicitly and has no default**, exactly as on the read side, and for
the same reason: it is not a function of the HTTP verb. Three of the six families below are
``POST`` — the same verb the pinned record *read* uses — so a verb-derived flag would be wrong
in both directions at once.

``endpoint`` and ``http_method`` are stated here but **cross-checked against the SDK request
class itself**, so a descriptor cannot drift away from the call it actually builds; and every
descriptor names a real method on :class:`~larkdocio.base.write_client.BaseWriteClient`.

Every op in this module is a **record** op. No field, table or view write exists at this rung.
"""
from dataclasses import dataclass
from typing import Callable, Tuple

from lark_oapi.api.bitable.v1 import (
    BatchCreateAppTableRecordRequest,
    BatchDeleteAppTableRecordRequest,
    BatchUpdateAppTableRecordRequest,
    CreateAppTableRecordRequest,
    DeleteAppTableRecordRequest,
    UpdateAppTableRecordRequest,
)
from larkdocio.common.citations import dev_repo

_CAPTURES = "tests/captures/base-study/captures"


@dataclass(frozen=True)
class BaseWriteOpDescriptor:
    """One Base record-write op: what it calls, on which verb, and that it mutates.

    * ``name`` — the op's name, and the name of the client method that implements it;
    * ``endpoint`` — the Lark path, cross-checked against ``request_cls``' own ``uri``;
    * ``http_method`` — the verb, likewise cross-checked;
    * ``mutates`` — **mandatory, explicit, never inferred**. Every op here declares ``True``;
    * ``batch`` — whether the op carries many records in one call;
    * ``request_cls`` — the pinned-SDK request class the client builds;
    * ``evidence`` — where this op was proven to work on a live Base.
    """

    name: str
    endpoint: str
    http_method: str
    mutates: bool
    batch: bool
    request_cls: type
    evidence: str


#: The ordered registry — the ONE place a Base record-write op is declared.
WRITE_OPS: Tuple[BaseWriteOpDescriptor, ...] = (
    BaseWriteOpDescriptor(
        name="create_record",
        endpoint="/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records",
        http_method="POST",
        mutates=True,
        batch=False,
        request_cls=CreateAppTableRecordRequest,
        evidence=(dev_repo(f"{_CAPTURES}/06-02-record-create-echo.json · "
                  f"{_CAPTURES}/p1-q6-01-value-writes.json")),
    ),
    BaseWriteOpDescriptor(
        name="update_record",
        endpoint="/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/:record_id",
        http_method="PUT",
        mutates=True,
        batch=False,
        request_cls=UpdateAppTableRecordRequest,
        evidence=dev_repo(f"{_CAPTURES}/p1-q6-01-value-writes.json"),
    ),
    BaseWriteOpDescriptor(
        name="delete_record",
        endpoint="/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/:record_id",
        http_method="DELETE",
        mutates=True,
        batch=False,
        request_cls=DeleteAppTableRecordRequest,
        evidence=dev_repo(f"{_CAPTURES}/06-06-destructive-ops.json"),
    ),
    BaseWriteOpDescriptor(
        name="batch_create_records",
        endpoint=("/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/"
                  "batch_create"),
        http_method="POST",
        mutates=True,
        batch=True,
        request_cls=BatchCreateAppTableRecordRequest,
        evidence=dev_repo(f"{_CAPTURES}/05-06-records-batch-create.json"),
    ),
    BaseWriteOpDescriptor(
        name="batch_update_records",
        endpoint=("/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/"
                  "batch_update"),
        http_method="POST",
        mutates=True,
        batch=True,
        request_cls=BatchUpdateAppTableRecordRequest,
        evidence=dev_repo(f"{_CAPTURES}/p0-2-06-table-revision-granularity.json"),
    ),
    BaseWriteOpDescriptor(
        name="batch_delete_records",
        endpoint=("/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/"
                  "batch_delete"),
        http_method="POST",
        mutates=True,
        batch=True,
        request_cls=BatchDeleteAppTableRecordRequest,
        evidence=dev_repo(f"{_CAPTURES}/p1-q6-01-value-writes.json"),
    ),
)


def write_op(name: str) -> BaseWriteOpDescriptor:
    """The write descriptor named ``name``."""
    for descriptor in WRITE_OPS:
        if descriptor.name == name:
            return descriptor
    raise KeyError(name)


def impl_of(descriptor: BaseWriteOpDescriptor) -> Callable:
    """The client method that implements a write op.

    Resolved lazily by name: the client imports this module for its descriptors, so the
    reverse direction cannot be a module-level import.
    """
    from larkdocio.base.write_client import BaseWriteClient

    return getattr(BaseWriteClient, descriptor.name)


def all_mutate() -> bool:
    """``True`` when every registered write op declares ``mutates``.

    The twin of the read registry's read-only proof, and the reason both can be asserted at
    once: one op set is wholly non-mutating, the other wholly mutating, and neither claim is
    made about the other's table.
    """
    return all(descriptor.mutates is True for descriptor in WRITE_OPS)
