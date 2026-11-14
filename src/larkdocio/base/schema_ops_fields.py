"""larkdocio.base.schema_ops_fields — the **field** schema-op family.

One family module, registered into :data:`larkdocio.base.schema_ops.FAMILY_MODULES` by adding
its dotted name there. It knows nothing about the app-and-table family and that family knows
nothing about it, which is the point: each family is one new file and one new line.

**Three ops, and ONE of them has a destructive shape.** Create a column, edit a column's name or
property, and convert a column's kind. ``DELETE …/fields/{f}`` is **deliberately absent** — the
destructive family owns it behind a cross-table loss preview and an explicit-consent fence.

What is *not* absent, and was for one release, is the destructiveness inside ``update_field``:
``PUT …/fields/{f}`` REPLACES a select column's option set, so a body that omits an option the
table's records hold **destroys those cells** (``ld462-01``: 2 of 3 records emptied on a
SingleSelect, values stripped per cell on a MultiSelect). That is one shape of one op, not a
property of the op — a rename, a currency format and a date format cannot lose a byte — so this
family declares it as a **shape** (:data:`DESTRUCTIVE_SHAPES`) and publishes the preview for it
(:data:`LOSS_PREVIEW_HANDLERS`). From there the shrink travels ``delete_field``'s own road:
``read_client`` required, a per-record loss preview, a refusal on any read that cannot be
completed, and ``consent_to_destroy(plan)`` before it may apply. One consent doctrine, one blast
radius, no second gate.

**Field ops are TABLE-scoped, and that is a different rung from the app-scoped ops.** An
app-scoped structural op has no usable anchor at all and discloses the absence. A **field** op
has one: ``table.revision`` moves by exactly ``+1`` per field operation, measured, so
``STALE_BASE`` applies here unchanged from the record engine — the shared marker core is
imported, never re-derived — and the plan entry carries
:data:`~larkdocio.base.field_authoring.FIELD_OPS_RIDE_TABLE_REVISION` instead of the app rung's
disclosure of an absence.

**Nothing here is verified by ``code:0``.** Each op's read-back is two facts read from the
server's own state: the column reads back with the identity that was asked for, **and** the
table's anchor moved. A call that answered ``code:0`` and left the anchor where it was is
reported as not having landed.

**The refusals are all local, and all before a client exists.** The allow-list
(:mod:`larkdocio.base.field_vocabulary`, imported and never re-listed), the captured property
shapes and the conversion pair table (:mod:`larkdocio.base.field_authoring`) each refuse in the
request constructor, so an unshippable request never becomes a plan entry and never costs a
transport call.
"""
from typing import Any, Dict, Optional

from lark_oapi.api.bitable.v1 import (
    AppTableField,
    CreateAppTableFieldRequest,
    UpdateAppTableFieldRequest,
)

from larkdocio.base.field_authoring import (
    FIELD_OPS_RIDE_TABLE_REVISION,
    FORMULA_EVALUATION_WHAT,
    build_property,
    check_conversion,
    check_select_option_update,
    cross_table_create,
    is_select_option_replacement,
)
from larkdocio.base.field_vocabulary import check_authorable
from larkdocio.base.loss_preview import select_option_shrink_loss
from larkdocio.base.schema_ops import BaseSchemaOpDescriptor, SchemaOpFamily
from larkdocio.base.schema_plan import SCOPE_TABLE, SchemaRequest
from larkdocio.common.citations import dev_repo
from larkdocio.common.staleness import REVISION_GUARD_ACTIVE, revision_guard_status

_CAPTURES = "tests/captures/base-study/captures"

#: The family's name, used by the aggregator and quoted in the source repository's ``BASE.md``
#: schema-ops table.
FAMILY_NAME = "field"

_READ_BACK = ("GET …/tables/{a}/{t}/fields lists the column with the identity that was asked "
              "for, AND table.revision has moved — a code:0 with an unmoved anchor is not an "
              "applied write")


SCHEMA_OP_FAMILY = SchemaOpFamily(
    name=FAMILY_NAME,
    module=__name__,
    ops=(
        BaseSchemaOpDescriptor(
            name="create_field",
            endpoint="/open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields",
            http_method="POST",
            mutates=True,
            family=FAMILY_NAME,
            settles=False,
            read_back=_READ_BACK,
            request_cls=CreateAppTableFieldRequest,
            evidence=dev_repo(f"{_CAPTURES}/05-04-field-zoo-create-results.json · "
                     f"{_CAPTURES}/p0-2-01-interconnection-field-create.json"),
        ),
        BaseSchemaOpDescriptor(
            name="update_field",
            endpoint=("/open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields/"
                      ":field_id"),
            http_method="PUT",
            mutates=True,
            family=FAMILY_NAME,
            settles=False,
            read_back=_READ_BACK,
            request_cls=UpdateAppTableFieldRequest,
            evidence=dev_repo(f"{_CAPTURES}/p1-q2-02-true-identity-retries.json"),
        ),
        BaseSchemaOpDescriptor(
            name="convert_field",
            endpoint=("/open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields/"
                      ":field_id"),
            http_method="PUT",
            mutates=True,
            family=FAMILY_NAME,
            settles=False,
            read_back=_READ_BACK,
            request_cls=UpdateAppTableFieldRequest,
            evidence=dev_repo(f"{_CAPTURES}/p1-q2-02-true-identity-retries.json (the one captured "
                     f"pair: Text → Barcode, same storage type)"),
        ),
    ),
)


# --------------------------------------------------------------------------- #
# The typed requests — every refusal happens HERE, before a client exists       #
# --------------------------------------------------------------------------- #

def _traits(revision, ui_type: Optional[str] = None) -> dict:
    # A Formula create rides the same table.revision anchor as every other field op, AND
    # carries a second sentence: the measured-limit disclosure. Attached here, on the same
    # already-declared trait every field op sets, exactly the way the DuplexLink mirror
    # disclosure attaches on its own (narrower) trait — no new DECLARABLE_TRAITS entry needed.
    disclosure = FIELD_OPS_RIDE_TABLE_REVISION
    if ui_type == "Formula":
        disclosure = f"{disclosure} {FORMULA_EVALUATION_WHAT}"
    return {
        "scope": SCOPE_TABLE,
        "revision_guard": revision_guard_status(revision),
        "revision_guard_disclosure": disclosure,
        # One anchor read before the write (only when the guard is active), one after, and one
        # field listing. Stated rather than assumed, so the plan's read budget is honest.
        "read_cost": 3 if revision_guard_status(revision) == REVISION_GUARD_ACTIVE else 2,
    }


def create_field(app_token: str, table_id: str, field_name: str, field_type: int,
                 ui_type: Optional[str] = None, properties: Optional[dict] = None,
                 source_table_name: Optional[str] = None,
                 revision=None) -> SchemaRequest:
    """Create one column. Refuses **locally** an un-authorable kind or an uncaptured shape.

    ``field_type`` and ``ui_type`` are checked **as a PAIR**, not one coordinate at a time: an
    identity no shipped registry carries — ``field_type=1`` with ``ui_type="Checkbox"``, where
    ``1`` is Text and Checkbox is ``7`` — is refused here with
    :class:`~larkdocio.base.field_vocabulary.UncapturedFieldPairError`, before a client is
    touched. :func:`~larkdocio.base.field_vocabulary.check_authorable` states the accepted
    trade-off that refusal carries.

    ``source_table_name`` is used only to predict the mirror column's name for a two-way link,
    which is why it is optional: without it the cross-table create is still disclosed, only the
    predicted name is withheld.

    **No ``position=`` / ``index=`` / ``after=`` parameter is offered here, deliberately, and
    this is not an oversight to "helpfully" fix later.** A dozen create-time position-shaped
    spellings (an index, a position, an insertion point named by an existing column, a
    query-string variant) were measured: every one is **accepted with a
    success code and ignored** — the new column always lands at the end — and five
    update-time equivalents rename a column without moving it, identically to an invented-key
    control. A parameter the endpoint accepts and silently ignores is not a parameter; it is
    the exact lie this library refuses to ship. **Column order is settable at exactly one
    point**: the ``fields=[…]`` array on
    :func:`~larkdocio.base.schema_plan.create_table` /
    :meth:`~larkdocio.base.schema_client.BaseSchemaClient.create_table`, whose order **is**
    the column order, at creation time only.
    """
    check_authorable(field_type, ui_type)
    if ui_type is not None:
        build_property(ui_type, **(properties or {}))
    arguments: Dict[str, Any] = {
        "app_token": app_token, "table_id": table_id, "field_name": field_name,
        "field_type": field_type, "ui_type": ui_type, "properties": dict(properties or {}),
        "revision": revision,
    }
    return SchemaRequest(
        op="create_field", app_token=app_token, table_id=table_id, arguments=arguments,
        describe=(f"create column {field_name!r} ({ui_type or field_type}) in table "
                  f"{table_id}"),
        traits={**_traits(revision, ui_type),
                "cross_table_create": cross_table_create(ui_type, field_name, properties,
                                                         source_table_name)})


def update_field(app_token: str, table_id: str, field_id: str, field_name: str,
                 field_type: int, ui_type: Optional[str] = None,
                 properties: Optional[dict] = None, revision=None) -> SchemaRequest:
    """Edit a column's **name** or **property** — never its kind.

    The allow-list is applied to any ``ui_type`` in the body because the server applies it to
    the ``PUT`` route identically to the ``POST`` one: the block is the vocabulary, not the
    verb. Changing the kind is :func:`convert_field`, which is gated on the pair table.

    **A SELECT column is fenced here, on the request's own shape.** ``PUT
    …/fields/{f}`` REPLACES the option set and matches on the option ``id``, so a body that
    omits the options — or carries them without their ids — re-mints every id and orphans every
    cell that pointed at an old one. Measured 6 of 6, on ``SingleSelect`` and ``MultiSelect``
    alike; see
    :data:`~larkdocio.base.field_authoring.SELECT_OPTION_ID_IS_THE_CELL_ANCHOR`. The refusal is
    structural and local: it never asks whether the column is populated, because that is not
    knowable without reading the table and an unknown blast radius is not a safe one.
    """
    check_authorable(field_type, ui_type)
    check_select_option_update(field_type, ui_type, properties)
    if ui_type is not None and properties:
        build_property(ui_type, **properties)
    arguments: Dict[str, Any] = {
        "app_token": app_token, "table_id": table_id, "field_id": field_id,
        "field_name": field_name, "field_type": field_type, "ui_type": ui_type,
        "properties": dict(properties or {}), "revision": revision,
    }
    return SchemaRequest(
        op="update_field", app_token=app_token, table_id=table_id, arguments=arguments,
        describe=_describe_update(table_id, field_id, field_name, properties),
        traits=_traits(revision))


def _describe_update(table_id, field_id, field_name, properties) -> str:
    """What the plan entry says this update does — and it no longer says *rename* when the body
    carries an option set. A ``dry_run`` that printed *"edit column … to name …"* for a
    whole-option-set replacement was the plan lying about the operation it had priced."""
    base = f"edit column {field_id} in table {table_id} to name {field_name!r}"
    options = (properties or {}).get("options")
    if not options:
        return base
    kept = sum(1 for option in options if option.get("id"))
    return (f"edit column {field_id} in table {table_id}: name {field_name!r} AND replace its "
            f"option set with {len(options)} select options ({kept} ids preserved, "
            f"{len(options) - kept} added)")


def convert_field(app_token: str, table_id: str, field_id: str, field_name: str,
                  field_type: int, *, from_ui_type: str, to_ui_type: str,
                  properties: Optional[dict] = None, revision=None) -> SchemaRequest:
    """Convert a column's kind — **only** for a pair a capture carries.

    Every other pair raises :class:`~larkdocio.base.field_authoring.UncapturedConversionError`
    here, before a client is reachable, so an unlisted conversion costs zero transport calls.

    **The two coordinates are checked SEPARATELY here, and deliberately so.** ``field_type`` is
    the SOURCE column's storage type and ``to_ui_type`` is the TARGET's kind — two different
    columns — so they are not a column identity, and the pair check
    :func:`~larkdocio.base.field_vocabulary.check_authorable` applies to a *create* would be
    asking a question neither coordinate answers. What gates this route is
    :func:`~larkdocio.base.field_authoring.check_conversion`, whose pair table is itself
    capture-derived, and the identity that reaches the wire is the captured pair's own
    (``pair.field_type``), never the caller's.
    """
    check_authorable(ui_type=to_ui_type)
    check_authorable(field_type=field_type)
    pair = check_conversion(from_ui_type, to_ui_type)
    arguments: Dict[str, Any] = {
        "app_token": app_token, "table_id": table_id, "field_id": field_id,
        "field_name": field_name, "field_type": pair.field_type,
        "from_ui_type": from_ui_type, "to_ui_type": to_ui_type,
        "properties": dict(properties or {}), "revision": revision,
    }
    return SchemaRequest(
        op="convert_field", app_token=app_token, table_id=table_id, arguments=arguments,
        describe=(f"convert column {field_id} in table {table_id} from {from_ui_type} to "
                  f"{to_ui_type}"),
        traits={**_traits(revision), "conversion": {
            "from": from_ui_type, "to": to_ui_type, "cell_effect": pair.cell_effect,
            "evidence": [dev_repo(f"{_CAPTURES}/{name}") for name in pair.captures]}})


# --------------------------------------------------------------------------- #
# The request bodies — assembled from the pinned SDK's typed builders           #
# --------------------------------------------------------------------------- #

def _field_body(field_name, field_type, ui_type, properties):
    builder = AppTableField.builder().field_name(field_name).type(field_type)
    if ui_type is not None:
        builder = builder.ui_type(ui_type)
        prop = build_property(ui_type, **(properties or {}))
        if prop is not None:
            builder = builder.property(prop)
    return builder.build()


def build_create_request(app_token, table_id, field_name, field_type, ui_type=None,
                         properties=None) -> CreateAppTableFieldRequest:
    """The ``POST …/fields`` request, from the pinned SDK's builders and nothing else."""
    return CreateAppTableFieldRequest.builder() \
        .app_token(app_token) \
        .table_id(table_id) \
        .request_body(_field_body(field_name, field_type, ui_type, properties)) \
        .build()


def build_update_request(app_token, table_id, field_id, field_name, field_type, ui_type=None,
                         properties=None) -> UpdateAppTableFieldRequest:
    """The ``PUT …/fields/{f}`` request — the same body shape on a field-scoped path.

    **The select fence is re-applied here, deliberately.** This builder is the route
    :meth:`~larkdocio.base.schema_client.BaseSchemaClient.update_field` takes, and that call
    never passes through a plan — so a fence that lived only in :func:`update_field` would leave
    the shorter, more tempting route holding the data-loss. One check, two call sites, no
    duplicated text.
    """
    check_select_option_update(field_type, ui_type, properties)
    return UpdateAppTableFieldRequest.builder() \
        .app_token(app_token) \
        .table_id(table_id) \
        .field_id(field_id) \
        .request_body(_field_body(field_name, field_type, ui_type, properties)) \
        .build()


# --------------------------------------------------------------------------- #
# The engine seams — one issue handler and one read-back handler per op         #
# --------------------------------------------------------------------------- #

def _issue_create(watch, entry):
    a = dict(entry.fields or {})
    return watch.create_field(a["app_token"], a["table_id"], a["field_name"],
                              a["field_type"], ui_type=a.get("ui_type"),
                              properties=a.get("properties"))


def _issue_update(watch, entry):
    a = dict(entry.fields or {})
    return watch.update_field(a["app_token"], a["table_id"], a["field_id"], a["field_name"],
                              a["field_type"], ui_type=a.get("ui_type"),
                              properties=a.get("properties"))


def _issue_convert(watch, entry):
    a = dict(entry.fields or {})
    return watch.convert_field(a["app_token"], a["table_id"], a["field_id"], a["field_name"],
                               a["field_type"], from_ui_type=a["from_ui_type"],
                               to_ui_type=a["to_ui_type"],
                               properties=a.get("properties"))


#: ``op name → the one call it makes``. Consulted by the schema engine, so a family adds its
#: calls without editing the engine.
ISSUE_HANDLERS = {
    "create_field": _issue_create,
    "update_field": _issue_update,
    "convert_field": _issue_convert,
}


def table_revision(read_client, app_token, table_id):
    """The live ``table.revision``, or ``None`` when the table is no longer listed."""
    for table in (read_client.list_tables(app_token) or ()):
        if getattr(table, "table_id", None) == table_id:
            return getattr(table, "revision", None)
    return None


def _read_back(read_client, entry, reply, _created_app_token):
    """``(confirmed, disclosure)`` for one field op, read from the server's own state.

    Two facts, never a ``code:0``: the column reads back with the identity that was asked for,
    and the table's anchor moved. When the anchor is unavailable — the ``0`` sentinel — the
    identity read-back stands alone and the disclosure says so, rather than passing an op that
    was never verified.
    """
    a = dict(entry.fields or {})
    app_token, table_id = a["app_token"], a["table_id"]
    wanted_name = a["field_name"]
    wanted_ui = a.get("to_ui_type", a.get("ui_type"))

    live = table_revision(read_client, app_token, table_id)
    planned = a.get("revision")
    moved = None
    if entry.revision_guard == REVISION_GUARD_ACTIVE and live is not None:
        moved = live - planned

    listed = [field for field in (read_client.list_fields(app_token, table_id) or ())
              if getattr(field, "field_name", None) == wanted_name]
    identity_ok = bool(listed) and (
        wanted_ui is None or getattr(listed[0], "ui_type", None) == wanted_ui)

    anchor_ok = True if moved is None else moved >= 1
    disclosure = {
        "how": entry.read_back,
        "table_id": table_id,
        "field_name": wanted_name,
        "ui_type": wanted_ui,
        "identity_confirmed": identity_ok,
        "revision_at_plan": planned,
        "revision_now": live,
        "revision_moved": moved,
        "anchor": ("unavailable — the identity read-back stands alone"
                   if moved is None else "table.revision"),
    }
    return bool(identity_ok and anchor_ok), disclosure


#: ``op name → the read-back it is verified by``. One entry per op, same seam as the issues.
READ_BACK_HANDLERS = {name: _read_back for name in ISSUE_HANDLERS}


# --------------------------------------------------------------------------- #
# The ONE destructive shape in this family — declared, previewed, consented     #
# --------------------------------------------------------------------------- #

def _replaces_select_options(request) -> bool:
    """Whether this ``update_field`` request REPLACES a select column's option set.

    The discriminator is :func:`~larkdocio.base.field_authoring.is_select_option_replacement` —
    the same one the LD-339 shape fence uses — so the fence and the preview cannot disagree about
    what a select option write is. No read, no client: this only decides whether the *question*
    of a loss arises.
    """
    arguments = dict(getattr(request, "arguments", None) or {})
    return is_select_option_replacement(arguments.get("field_type"), arguments.get("ui_type"),
                                        arguments.get("properties"))


def _option_shrink_loss(scan, request: SchemaRequest) -> Dict:
    arguments = dict(request.arguments)
    return select_option_shrink_loss(scan, arguments["table_id"], arguments["field_id"],
                                     (arguments.get("properties") or {}).get("options"))


#: **THE CONDITIONALLY DESTRUCTIVE SET**, declared by the family that ships it — the shape half
#: of what ``DESTRUCTIVE_OPS`` declares by verb. ``update_field`` is not a destructive op: three
#: of its four shapes cannot lose a byte, and putting it in the destructive set would make every
#: column rename demand a read client and a consent token. The fourth shape — a select column's
#: option set, REPLACED — destroys the cells of every option it omits (``ld462-01``), so it is
#: declared here and travels the identical road from there: ``read_client`` required, a
#: per-record ``loss_preview``, ``LOSS_MUST_BE_ENUMERABLE`` on any read it cannot complete, and
#: ``consent_to_destroy(plan)`` before it may be applied.
DESTRUCTIVE_SHAPES = {"update_field": _replaces_select_options}

#: ``op name → the loss preview it must produce before it may be applied``, for the shapes above.
#: The engine dispatches over this exactly as it does for the destructive family, so the shrink
#: has no second gate of its own.
LOSS_PREVIEW_HANDLERS = {"update_field": _option_shrink_loss}


__all__ = [
    "DESTRUCTIVE_SHAPES",
    "FAMILY_NAME",
    "ISSUE_HANDLERS",
    "LOSS_PREVIEW_HANDLERS",
    "READ_BACK_HANDLERS",
    "SCHEMA_OP_FAMILY",
    "build_create_request",
    "build_update_request",
    "convert_field",
    "create_field",
    "table_revision",
    "update_field",
]
