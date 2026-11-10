"""larkdocio.base.schema_ops_destructive — the **destructive** schema-op family.

One family module and one line in :data:`larkdocio.base.schema_ops.FAMILY_MODULES`, the contract
the app-and-table family established. What is different here is not the seam but the posture:
these three verbs are the **schema** verbs that destroy cells — a column, a table, a batch of
tables, and everything their cells hold — so each of them ships behind two things nothing else
on this surface has —

* a **cross-table loss preview** (:mod:`larkdocio.base.loss_preview`), produced in the dry run,
  which enumerates what the delete destroys **in every table it reaches**; and
* an **explicit-consent fence** (:func:`larkdocio.base.schema_apply.consent_to_destroy`), so no
  destructive **schema** op is reachable from a default call.

**They are NOT the only Base ops that can lose data, and this family does not claim to be.**
The surface has **three tiers** of destructiveness and states the one that is true of each:

* a **record** delete (:mod:`larkdocio.base.plan` → :mod:`larkdocio.base.apply`) destroys rows
  through the ordinary ``dry_run`` → ``apply`` path, carrying a per-row ``before`` and a value
  precondition but **no consent token** — deleting every row of a table is reachable without
  one;
* a **view** delete (:func:`larkdocio.base.view_plan.delete_view`) carries **neither** —
  ``loss_preview`` is ``None`` and no token is required, because deleting a view destroys a
  presentation and not a cell; and
* a **schema** delete that destroys cells — these three verbs — carries **both**.

So the rule the fence enforces is the narrow one that is actually true: **consent is required
for a schema delete that destroys cells.** Widening that sentence to the whole surface is what
made an earlier wording of this paragraph false; the guided column-type migration
(:mod:`larkdocio.base.field_migration`) is inside the fence for exactly this reason — its
delete step **is** the ``delete_field`` dry run above, so it is admitted at the one consent
door rather than given a second.

**Three ops.** ``DELETE …/tables/{t}/fields/{f}`` · ``DELETE …/tables/{t}`` ·
``POST …/tables/batch_delete``. Deleting the **app** is deliberately not among them: no shipped
op offers a consumer a one-call *"delete this Base"*, and the drive-file delete stays a live
harness primitive.

**DELETE IS TRASH, NOT PURGE, and nothing here says otherwise.** No open-API verb purges an app,
and deleted tables sit in the Base's trash too, so the surface says *deleted, recoverable from
Lark's trash by a human* — never *erased*
(:data:`~larkdocio.base.loss_preview.TRASH_NOT_PURGE`, quoted, not re-authored).

**Two scopes in one family, so the disclosure is per-op rather than per-family.** A **field**
delete is TABLE-scoped: ``table.revision`` moves ``+1`` per field operation (``p0-2-06``), so
``STALE_BASE`` applies to it unchanged and the write-effect oracle has an anchor to read. A
**table** delete is APP-scoped: there is no anchor at all, which
:data:`~larkdocio.base.schema_plan.NO_APP_REVISION_CAS` already states. Collapsing the two into
one sentence would make one of them false, so this module publishes
:data:`REVISION_GUARD_DISCLOSURES` keyed by op and the engine reads it per op.

**The protected-last codes are the server's floor, not this library's.** ``1254034`` — the last
table cannot be deleted — and the last-view code the view family already ships, **quoted rather
than re-authored** — are both **entry-scoped**: Lark's answer is about that object, and it says
nothing about the other entries in the batch, so the batch continues.

**Nothing here is verified by ``code:0``.** A delete that answered ``code:0`` and left the
column in place is reported as not having landed — the same R12 discipline every other schema op
is under, and on a delete it is the difference between "your data is gone" and "your data is
still there and you think it is gone".
"""
from typing import Any, Dict, Optional, Sequence

from lark_oapi.api.bitable.v1 import (
    BatchDeleteAppTableRequest,
    DeleteAppTableFieldRequest,
    DeleteAppTableRequest,
)

from larkdocio.base.field_authoring import FIELD_OPS_RIDE_TABLE_REVISION
from larkdocio.base.loss_preview import (
    OBJECT_GONE_CODES,
    field_delete_loss,
    table_delete_loss,
)
from larkdocio.base.schema_ops import BaseSchemaOpDescriptor, SchemaOpFamily
from larkdocio.base.schema_ops_fields import table_revision
from larkdocio.base.schema_plan import (
    NO_APP_REVISION_CAS,
    SCOPE_APP,
    SCOPE_TABLE,
    SchemaRequest,
)
from larkdocio.common.citations import dev_repo
from larkdocio.common.staleness import REVISION_GUARD_ACTIVE, revision_guard_status

_CAPTURES = "tests/captures/base-study/captures"
_P0 = "dev/base-study/p0-addendum-2026-08-03.md"

#: The family's name, used by the aggregator and quoted in the source repository's ``BASE.md``
#: schema-ops table.
FAMILY_NAME = "destructive"

#: ``1254034``'s actionable half, authored once: what the caller can actually do about it. The
#: shape LD-264's :data:`~larkdocio.base.schema_ops_views.LAST_VIEW_IS_PROTECTED` established.
LAST_TABLE_IS_PROTECTED = (
    "A Base's last table cannot be deleted (`1254034`): Lark keeps every Base on a floor of one "
    "table, so a Base cannot be reduced to zero tables through the API. If deleting the whole "
    "Base is what you meant, that is a different call and it exists: "
    "`larkdocio.base.schema_client.BaseSchemaClient.delete_base(app_token)`, on the WRITE "
    "credentials, which trashes the whole Base — every table, column, record and view — in one "
    "act. It takes no consent token because it is not a plan-gated schema op at all (it is the "
    "same whole-object call `delete_document` and `delete_spreadsheet` are), so read what it "
    "costs before you reach for it: the trash is Lark's own, a human can restore from the "
    "product, there is no API undo, and confirming it landed means addressing the app_token "
    "again — `base_is_gone(exc)` answers both codes. Otherwise, leave this table and delete the "
    "others. This answer is about THIS table only; every other entry in the plan is judged on "
    "its own."
)

_FIELD_READ_BACK = (
    "GET …/tables/{a}/{t}/fields no longer lists the column, AND table.revision has moved — a "
    "code:0 whose anchor did not move is not an applied delete; when the column was a two-way "
    "link, the MIRROR's own table is re-read too and must no longer list it")

_TABLE_READ_BACK = (
    "GET …/apps/{a}/tables no longer lists the table_id, AND the table path itself answers one "
    f"of {OBJECT_GONE_CODES} — the same object-gone oracle the live harness's zero-orphan "
    "check uses, asked of the bitable API and never of Drive metadata")

_BATCH_READ_BACK = (
    "GET …/apps/{a}/tables lists NONE of the returned table_ids in a SINGLE read-back — one "
    "call, one verification, whatever the batch's size")


SCHEMA_OP_FAMILY = SchemaOpFamily(
    name=FAMILY_NAME,
    module=__name__,
    ops=(
        BaseSchemaOpDescriptor(
            name="delete_field",
            endpoint=("/open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields/"
                      ":field_id"),
            http_method="DELETE",
            mutates=True,
            family=FAMILY_NAME,
            settles=False,
            read_back=_FIELD_READ_BACK,
            request_cls=DeleteAppTableFieldRequest,
            evidence=dev_repo(f"{_CAPTURES}/06-06-destructive-ops.json · "
                     f"{_CAPTURES}/p0-2-07-link-deletion-behaviour.json · "
                     f"{_CAPTURES}/p0-2-06-table-revision-granularity.json"),
        ),
        BaseSchemaOpDescriptor(
            name="delete_table",
            endpoint="/open-apis/bitable/v1/apps/:app_token/tables/:table_id",
            http_method="DELETE",
            mutates=True,
            family=FAMILY_NAME,
            settles=False,
            read_back=_TABLE_READ_BACK,
            request_cls=DeleteAppTableRequest,
            evidence=dev_repo(f"{_CAPTURES}/p0-5-02-symmetric-link-deletion.json · "
                     f"{_CAPTURES}/p0-1-06-husk-reduction-test.json (the 1254034 floor)"),
        ),
        BaseSchemaOpDescriptor(
            name="batch_delete_tables",
            endpoint="/open-apis/bitable/v1/apps/:app_token/tables/batch_delete",
            http_method="POST",
            mutates=True,
            family=FAMILY_NAME,
            settles=False,
            read_back=_BATCH_READ_BACK,
            request_cls=BatchDeleteAppTableRequest,
            evidence=dev_repo(f"{_CAPTURES}/p0-1-06-husk-reduction-test.json · "
                     f"{_CAPTURES}/06-06-destructive-ops.json"),
        ),
    ),
)

#: **THE DESTRUCTIVE SET**, declared by the family that ships it. The engine unions this across
#: families rather than inferring destructiveness from a verb — ``batch_delete`` is a ``POST``,
#: the same verb the pinned record *read* uses, so a verb-derived flag would be wrong at once.
DESTRUCTIVE_OPS = frozenset(descriptor.name for descriptor in SCHEMA_OP_FAMILY.ops)

#: Per-op, because this family holds **two scopes**: a column delete rides ``table.revision``
#: and a table delete has no anchor at all. One sentence for both would be false about one.
REVISION_GUARD_DISCLOSURES = {
    "delete_field": FIELD_OPS_RIDE_TABLE_REVISION,
    "delete_table": NO_APP_REVISION_CAS,
    "batch_delete_tables": NO_APP_REVISION_CAS,
}

#: The family default, for anything that asks without naming an op.
REVISION_GUARD_DISCLOSURE = NO_APP_REVISION_CAS


# --------------------------------------------------------------------------- #
# The typed requests                                                           #
# --------------------------------------------------------------------------- #

def delete_field(app_token: str, table_id: str, field_id: str,
                 revision=None) -> SchemaRequest:
    """Delete ONE column. **Destroys every value in it**, and — if it is a two-way link — the
    mirror column in another table with it.

    ``revision`` is the ``table.revision`` the caller planned against; supplying it arms
    ``STALE_BASE`` for this entry, exactly as it does for the non-destructive field ops.
    """
    arguments: Dict[str, Any] = {"app_token": app_token, "table_id": table_id,
                                 "field_id": field_id, "revision": revision}
    guard = revision_guard_status(revision)
    return SchemaRequest(
        op="delete_field", app_token=app_token, table_id=table_id, arguments=arguments,
        describe=f"DELETE column {field_id} in table {table_id}",
        traits={"scope": SCOPE_TABLE,
                "revision_guard": guard,
                "revision_guard_disclosure": FIELD_OPS_RIDE_TABLE_REVISION,
                # The anchor read before the write (only when the guard is armed), the field
                # listing after it, and the anchor again; a two-way link adds the mirror
                # table's own listing, which the read-back really performs.
                "read_cost": 3 if guard == REVISION_GUARD_ACTIVE else 2})


def delete_table(app_token: str, table_id: str) -> SchemaRequest:
    """Delete ONE table. Destroys every column and row in it, and — silently, in every other
    table of the Base — destroys every link pointing INTO it. The two link kinds go differently:
    a one-way link survives and dangles (it keeps the dead table's id while the name drops out),
    while a two-way link does not survive at all, because its twin lives inside the table being
    deleted and the source column goes with it. Deleting a link COLUMN is a different call with
    its own reading (:func:`delete_field`), and neither one's evidence is borrowed for the
    other."""
    return SchemaRequest(
        op="delete_table", app_token=app_token, table_id=table_id,
        arguments={"app_token": app_token, "table_id": table_id},
        describe=f"DELETE table {table_id} in Base {app_token}",
        traits={"scope": SCOPE_APP,
                "revision_guard_disclosure": NO_APP_REVISION_CAS,
                # The table listing, plus the object-gone probe on the table's own path.
                "read_cost": 2})


def batch_delete_tables(app_token: str, table_ids: Sequence[str]) -> SchemaRequest:
    """Delete several tables in ONE call, verified by ONE read-back."""
    table_ids = list(table_ids)
    return SchemaRequest(
        op="batch_delete_tables", app_token=app_token,
        arguments={"app_token": app_token, "table_ids": table_ids},
        describe=f"DELETE {len(table_ids)} table(s) in Base {app_token}",
        traits={"scope": SCOPE_APP,
                "revision_guard_disclosure": NO_APP_REVISION_CAS,
                "read_cost": 1})


# --------------------------------------------------------------------------- #
# The loss previews — the engine asks the family, it does not branch           #
# --------------------------------------------------------------------------- #

def _field_loss(scan, request: SchemaRequest) -> Dict:
    arguments = dict(request.arguments)
    return field_delete_loss(scan, arguments["table_id"], arguments["field_id"])


def _table_loss(scan, request: SchemaRequest) -> Dict:
    return table_delete_loss(scan, [dict(request.arguments)["table_id"]])


def _batch_loss(scan, request: SchemaRequest) -> Dict:
    return table_delete_loss(scan, list(dict(request.arguments)["table_ids"]))


#: ``op name → the loss preview it must produce before it may be applied``. The dry run
#: dispatches over this, so a destructive op cannot exist without one.
LOSS_PREVIEW_HANDLERS = {
    "delete_field": _field_loss,
    "delete_table": _table_loss,
    "batch_delete_tables": _batch_loss,
}


# --------------------------------------------------------------------------- #
# The engine seams — one issue handler and one read-back handler per op        #
# --------------------------------------------------------------------------- #

def _issue(watch, entry):
    arguments = dict(entry.fields or {})
    if entry.op == "delete_field":
        return watch.delete_field(arguments["app_token"], arguments["table_id"],
                                  arguments["field_id"])
    if entry.op == "delete_table":
        return watch.delete_table(arguments["app_token"], arguments["table_id"])
    return watch.batch_delete_tables(arguments["app_token"], arguments["table_ids"])


ISSUE_HANDLERS = {descriptor.name: _issue for descriptor in SCHEMA_OP_FAMILY.ops}


def _field_ids(read_client, app_token, table_id):
    return {getattr(field, "field_id", None)
            for field in (read_client.list_fields(app_token, table_id) or ())}


def _table_ids(read_client, app_token):
    return {getattr(table, "table_id", None)
            for table in (read_client.list_tables(app_token) or ())}


def object_is_gone(read_client, app_token, table_id) -> Optional[bool]:
    """``True`` when the table's own path answers one of :data:`OBJECT_GONE_CODES`.

    The object-gone oracle for an **app-scoped** delete, which has no anchor to read: the table
    is addressed directly rather than looked for in a listing, and only Lark's own gone-codes
    count. ``None`` when the read answered something else entirely — an unknown answer is not
    quietly read as confirmation.
    """
    try:
        read_client.list_fields(app_token, table_id)
    except Exception as exc:            # noqa: BLE001 — the oracle IS the exception's code
        code = getattr(exc, "code", None)
        try:
            code = int(str(code))
        except (TypeError, ValueError):
            return None
        return code in OBJECT_GONE_CODES
    return False


def _read_back(read_client, entry, reply, _created_app_token):
    """``(confirmed, disclosure)`` for one landed delete, read from the server's own state."""
    arguments = dict(entry.fields or {})
    app_token = arguments["app_token"]

    if entry.op == "delete_field":
        table_id = arguments["table_id"]
        planned = arguments.get("revision")
        live = table_revision(read_client, app_token, table_id)
        moved = (live - planned
                 if entry.revision_guard == REVISION_GUARD_ACTIVE
                 and live is not None and planned is not None else None)
        gone = arguments["field_id"] not in _field_ids(read_client, app_token, table_id)
        mirror = (entry.loss_preview or {}).get("mirror") or {}
        mirror_gone = None
        if mirror.get("field_id") and mirror.get("table_id"):
            mirror_gone = mirror["field_id"] not in _field_ids(
                read_client, app_token, mirror["table_id"])
        anchor_ok = True if moved is None else moved >= 1
        disclosure = {
            "how": entry.read_back, "table_id": table_id,
            "field_id": arguments["field_id"], "gone": gone,
            "revision_at_plan": planned, "revision_now": live, "revision_moved": moved,
            "anchor": ("unavailable — the absence read-back stands alone"
                       if moved is None else "table.revision"),
            "mirror_field_id": mirror.get("field_id"),
            "mirror_gone": mirror_gone,
        }
        confirmed = bool(gone and anchor_ok and (mirror_gone is not False))
        return confirmed, disclosure

    if entry.op == "delete_table":
        table_id = arguments["table_id"]
        listed = table_id in _table_ids(read_client, app_token)
        addressed_gone = object_is_gone(read_client, app_token, table_id)
        return (not listed) and addressed_gone is True, {
            "how": entry.read_back, "table_id": table_id, "listed": listed,
            "object_gone": addressed_gone, "gone_codes": list(OBJECT_GONE_CODES)}

    wanted = list(arguments["table_ids"])
    listed = _table_ids(read_client, app_token)
    survivors = [table_id for table_id in wanted if table_id in listed]
    return bool(wanted) and not survivors, {
        "how": entry.read_back, "table_ids": wanted, "still_listed": survivors,
        "read_backs": 1}


READ_BACK_HANDLERS = {name: _read_back for name in ISSUE_HANDLERS}


__all__ = [
    "DESTRUCTIVE_OPS",
    "FAMILY_NAME",
    "ISSUE_HANDLERS",
    "LAST_TABLE_IS_PROTECTED",
    "LOSS_PREVIEW_HANDLERS",
    "READ_BACK_HANDLERS",
    "REVISION_GUARD_DISCLOSURE",
    "REVISION_GUARD_DISCLOSURES",
    "SCHEMA_OP_FAMILY",
    "batch_delete_tables",
    "delete_field",
    "delete_table",
    "object_is_gone",
]
