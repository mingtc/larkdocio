"""larkdocio.base.schema_plan — the Base SCHEMA plan and its disclosures.

**The same gate, a different subject.** The record engine plans over *records* — a
:class:`~larkdocio.base.plan.PlanEntry` is a row, and its guard is ``table.revision``. A schema
op has no row and, the evidence shows, **no anchor at all**. So the plan value here is its own
type, built to the same three rules the two landed engines are built to:

* it is **non-forgeable** — the constructor is guarded by a module-private token, so the only
  way to obtain a :class:`SchemaPlan` is :func:`larkdocio.base.schema_apply.schema_dry_run`, and
  :func:`~larkdocio.base.schema_apply.schema_apply` accepts nothing else. No direct-apply path,
  no second gate, no bypass;
* the **apply-log is the record engine's own** — :class:`~larkdocio.base.plan.ApplyLog`,
  :class:`~larkdocio.base.plan.ApplyLogEntry` and :class:`~larkdocio.base.plan.Refusal` are
  imported and used unchanged, so one run of the Base engine reads the same whatever it wrote;
* every entry **discloses what it is not guarded by**, which on this rung is the whole story.

**THERE IS NO ``app.revision`` COMPARE-AND-SWAP, AND THIS MODULE SAYS SO RATHER THAN IMPLYING
ONE (O3″).** The three probe packs disagree about what ``app.revision`` counts — ``0 → 1`` across
a whole session of 18 field and 3 record creations (opener ``05-08``), ``0 → 14`` across table
creates and deletes (P0 § 5), ``0 → 5`` across one probe table plus two batch tables (P1 § 6).
Those are not three readings of one counting rule; they are three counting rules. A
compare-and-swap built on an anchor nobody can predict would refuse valid plans and pass invalid
ones, and would read to a consumer exactly like the guard the record engine really has. So there
is none — the ops are verified by **read-back** instead, and :data:`NO_APP_REVISION_CAS` is the
one authoring of the absence.

That is a **different fact** from the record engine's :data:`~larkdocio.base.plan.NO_SERVER_SIDE_CAS`,
which is about ``table.revision`` and about the API ignoring precondition keys. Two facts, two
statements, neither absorbed into the other.
"""
import json
from dataclasses import dataclass, field as dataclass_field, replace
from typing import Any, Dict, Optional, Tuple

from larkdocio.base.plan import ApplyLogEntry, Refusal
from larkdocio.common.destination import require_destination
from larkdocio.base.schema_settle import ASYNC_SETTLE_CONTRACT

# The private construction token. Only this module holds it, so a :class:`SchemaPlan` can be
# built solely via :func:`larkdocio.base.schema_apply.schema_dry_run` — the docx
# ``write.preview._PLAN_TOKEN`` / sheets ``plan._PLAN_TOKEN`` / base ``plan._PLAN_TOKEN`` hard
# gate, fourth surface.
_SCHEMA_PLAN_TOKEN = object()


# --------------------------------------------------------------------------- #
# The one statement this rung must not get wrong, authored ONCE                #
# --------------------------------------------------------------------------- #

#: **What an app-scoped structural op is NOT guarded by.** Quoted verbatim by every plan entry,
#: by the apply-log and by ``BASE.md``'s register (in the source repository), so the three cannot drift.
NO_APP_REVISION_CAS = (
    "This operation carries NO revision guard. `app.revision` exists, but the three probe "
    "packs disagree about what it counts — 0 to 1 across a whole session of 18 field and 3 "
    "record creations (capture `05-08`), 0 to 14 across table creates and deletes (P0 "
    "addendum section 5), and 0 to 5 across one probe table plus two batch tables (P1 section "
    "6). That is not one counting rule read three times, so no compare-and-swap is built on "
    "it: a guard on an anchor nobody can predict would refuse valid plans, pass invalid ones, "
    "and read to you exactly like the guard the RECORD engine really has. Structural ops are "
    "verified by READ-BACK instead — the renamed Base re-reads with its new name, the created "
    "table appears in the table list — and `code:0` alone is never accepted as evidence. If "
    "something else changes this Base's shape between your plan and your apply, nothing here "
    "will notice; re-read before you plan, and keep structural changes to a Base you control."
)

#: A schema entry settled its asynchronous op within the budget — or the op was synchronous.
#:
#: **A declared vocabulary member with no producer in this tree.** Measured 2026-09-03: the only
#: occurrences of this name under ``src/``, ``tests/`` and ``scripts/`` are this definition and
#: its ``__all__`` entry — no code assigns it to a refusal reason or any other field, so no
#: reading of a plan or an apply log can carry it. Its sibling :data:`SETTLE_NOT_COMPLETE` is
#: the produced half of the pair (imported and emitted in ``schema_settle``'s consumer,
#: ``schema_apply``). Recorded rather than tested: a test that asserted this constant equals
#: its own literal would prove nothing about a state nothing emits. **Whether the engine
#: SHOULD emit it is an open product question, deliberately not settled here.**
SETTLE_NOT_REQUIRED = "not-required"

#: The refusal reason for a bounded settle that ran out of budget. **Not** an error and **not**
#: a failed write: the copy exists, it is simply not readable yet.
SETTLE_NOT_COMPLETE = "settle-not-complete"

#: An op whose subject is the Base itself or one of its tables. The disclosure above is
#: unconditional for these, because there is no anchor to guard them with. It is also the
#: **default**: a family whose ops are scoped to something smaller declares its own ``scope``
#: trait beside its descriptors (the view family is scoped to a view, which is neither an app
#: nor a row).
SCOPE_APP = "app"

#: An op whose subject is a **column**, and whose anchor therefore exists: ``table.revision``
#: moves ``+1`` per field operation, so ``STALE_BASE`` applies to these unchanged from the
#: record engine. A table-scoped entry carries its own disclosure — the field family authors
#: it — and deliberately **not** :data:`NO_APP_REVISION_CAS`, which would be false about it.
SCOPE_TABLE = "table"


def disclosure_for_op(op: Optional[str]) -> str:
    """What the op called ``op`` is NOT guarded by — its own family's statement, or the
    app-scoped one.

    Looked up rather than hardcoded because the absences are **different facts**: the
    app-scoped one is about ``app.revision`` counting inconsistently, and the view one is about
    there being no anchor to count at all. Collapsing them into one sentence would make one of
    them false.

    Read off the op's own **family module** — the same "ask the family, do not branch per
    family" seam :mod:`larkdocio.base.schema_apply` dispatches its handlers over. The apply-log
    entry needs this lookup even though the *plan* entry already carries the trait, because the
    record engine's ``applied``/``dropped``/``failed`` constructors build the log entry from the
    plan entry's identity fields only and do not copy the disclosure across.

    A family may publish ``REVISION_GUARD_DISCLOSURES`` — **keyed by op** — as well as a single
    ``REVISION_GUARD_DISCLOSURE``, and the per-op map wins. The destructive family needs both
    kinds in one file: a **column** delete rides ``table.revision`` while a **table** delete has
    no anchor at all, and one sentence covering both would be false about one of them.
    """
    import importlib

    from larkdocio.base.schema_ops import family_of

    family = family_of(op)
    if family is None:
        return NO_APP_REVISION_CAS
    module = importlib.import_module(family.module)
    per_op = getattr(module, "REVISION_GUARD_DISCLOSURES", None) or {}
    if op in per_op:
        return per_op[op]
    return getattr(module, "REVISION_GUARD_DISCLOSURE", NO_APP_REVISION_CAS)


# --------------------------------------------------------------------------- #
# The typed requests a plan is made of                                         #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SchemaRequest:
    """One structural change a caller asks for. The base of the six typed requests below.

    ``op`` is the registered descriptor name (:mod:`larkdocio.base.schema_ops`), so a request
    cannot name a call the library does not ship, and ``arguments`` is exactly what the client
    method will be handed — which is what makes the plan a preview rather than a summary.
    """

    op: str = ""
    app_token: Optional[str] = None
    table_id: Optional[str] = None
    arguments: Dict[str, Any] = dataclass_field(default_factory=dict)
    describe: str = ""
    #: **What this request's own family knows about it that the engine does not.** A family
    #: module fills it (scope, the revision guard and its disclosure, its read budget, any
    #: op-specific disclosure such as a cross-table create); :func:`schema_dry_run` copies the
    #: keys onto the plan entry. It is a **dict of declared traits rather than another branch
    #: inside the engine** precisely so a second family does not have to edit a first family's
    #: code to say something true about itself. Empty for the app-and-table family, whose
    #: entries are exactly what the defaults already say.
    traits: Dict[str, Any] = dataclass_field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"op": self.op, "app_token": self.app_token, "table_id": self.table_id,
                "arguments": dict(self.arguments), "describe": self.describe}


def create_base(name: str, folder_token: Optional[str] = None,
                time_zone: Optional[str] = None) -> SchemaRequest:
    """Create a Base named ``name`` in the folder ``folder_token``.

    **The destination is the caller's** — ``folder_token`` is **required** and every spelling of
    "none" is refused **here, at the plan seam**, so a refused request costs zero calls *and*
    never enters a plan. The client seam refuses again for the reason
    :meth:`~larkdocio.base.schema_client.BaseSchemaClient.create_table` gives for its own
    double-check: both are public doors, and a caller coming through either deserves the same
    sentence. The rule and its measurements are on :mod:`larkdocio.common.destination`.

    ``time_zone`` (an IANA name such as ``"Asia/Singapore"``) declares the new Base's own zone.
    **Declare it.** It is the one place Lark accepts a zone
    (:data:`larkdocio.base.date_zone.CREATE_IS_WHERE_A_ZONE_IS_DECLARED`), and a Base created
    without one reports none on every later read — so its date cells are rendered in an assumed
    zone and a date-only value can read back one calendar day early
    (:data:`larkdocio.base.date_zone.POLICY`). Omitted from the request when not supplied, and
    named in :attr:`SchemaRequest.describe` when it is, so the plan previews the declaration.
    """
    require_destination(folder_token, what="a Base")
    arguments = {"name": name, "folder_token": folder_token}
    describe = f"create a Base named {name!r}"
    if time_zone:
        arguments["time_zone"] = time_zone
        describe += f", declaring its time zone {time_zone!r}"
    return SchemaRequest(op="create_app", arguments=arguments, describe=describe)


def rename_base(app_token: str, name: str) -> SchemaRequest:
    """Rename the Base ``app_token`` to ``name``."""
    return SchemaRequest(op="rename_app", app_token=app_token,
                         arguments={"app_token": app_token, "name": name},
                         describe=f"rename Base {app_token} to {name!r}")


def copy_base(app_token: str, name: str, without_content: bool = False,
              folder_token: Optional[str] = None) -> SchemaRequest:
    """Copy the Base ``app_token``. ``without_content=True`` copies the **schema only**.

    ``folder_token`` places the copy in a Drive folder — the same spelling and the same
    **required**-destination rule :func:`create_base` has, so the two creation calls read
    alike, and a copy (which makes a new top-level Base) cannot land in the application's own
    space by omission (:mod:`larkdocio.common.destination`). The
    measurement behind it, including the half it does **not** claim, is in
    :meth:`~larkdocio.base.schema_client.BaseSchemaClient.copy_app`'s docstring (probe
    ``ld387-01``).
    """
    require_destination(folder_token, what="a copy of a Base")
    arguments = {"app_token": app_token, "name": name,
                 "without_content": bool(without_content),
                 "folder_token": folder_token}
    return SchemaRequest(
        op="copy_app", app_token=app_token,
        arguments=arguments,
        describe=(f"copy Base {app_token} to {name!r}"
                  f"{' (schema only)' if without_content else ''}"))


def create_table(app_token: str, name: str, fields=None,
                 primary_field_name=None, default_view_name=None) -> SchemaRequest:
    """Create one table named ``name`` in the Base ``app_token``.

    **A table is never created with a primary column Lark named.** Exactly one of
    ``primary_field_name=`` (one ``Text`` column, under the name you gave) or ``fields=[…]``
    (whose FIRST entry becomes the primary column) is **required**; neither refuses locally with
    :data:`~larkdocio.base.schema_ops_app_table.NAMELESS_PRIMARY_IS_REFUSED`, and both together
    refuse with :data:`~larkdocio.base.schema_ops_app_table.PRIMARY_FIELD_NAME_AND_KIT`. Both
    refusals are decided **here**, before a :class:`SchemaRequest` exists and long before a
    client does, so they cost **zero** API calls structurally.

    ``primary_field_name=`` is **sugar over the same transport**: it is normalised into a
    one-entry kit and gate-checked identically, so a caller passing it gets the request a caller
    passing the equivalent explicit kit gets.

    ``fields`` is the table's **column kit** — a sequence of ``{"field_name", "field_type",
    "ui_type", "properties"}`` definitions, spelled exactly the way
    :func:`larkdocio.base.schema_ops_fields.create_field` spells its arguments — and it lands
    **in the same call as the table**, on a route that never touches the ``/fields`` write
    family.

    **The kit goes THROUGH the field gate, not around it.** Every definition is checked
    **here**, before a :class:`SchemaRequest` even exists, by the same
    :func:`~larkdocio.base.field_vocabulary.check_authorable` and
    :func:`~larkdocio.base.field_authoring.build_property` ``create_field`` calls; an
    unauthorable kind, an uncaptured identity pair, a missing mandatory ``property`` or an
    unknown key **anywhere** in the array refuses the **whole** op, naming the offending entry's
    index and its name, having made **zero** API calls. Omitted, the request and its plan entry
    are byte-identical to what this constructor has always produced.

    **The array's ORDER IS the table's column order, and it is the ONLY point at which column
    order is settable.** Measured with a reversed control: two tables, the
    same three names in opposite ``fields=`` orders, each reading back in its own array's
    order. No create-time position parameter, update-time position parameter, or dedicated
    move/reorder route was found to place or move a column afterward — see
    :func:`~larkdocio.base.schema_ops_fields.create_field`'s own docstring for the enumeration.
    So this array is not merely a column kit; it is the one chance to choose the order.

    ``default_view_name`` names the table's **default view**. It is **not** a key on the
    create body — Lark rejects that outright (``1254001``, probe ``ld344-01``) — so this entry
    becomes a **COMPOSITE of two writes**: create the table, then rename the single view it is
    born with, addressed by the ``default_view_id`` the create's own reply carries. **The
    composite is NOT ATOMIC.** If the create lands and the rename does not, the table exists
    under Lark's own view name and the apply log records the entry **applied-unverified** with
    :class:`~larkdocio.base.errors.TableCreatedViewNotNamed`'s detail — the ``table_id``, the
    ``view_id`` and Lark's unedited denial. Nothing is rolled back and nothing is retried; one
    :func:`larkdocio.base.view_plan.rename_view`-shaped ``update_view`` finishes the job. The
    read-back costs one extra listing, and this constructor **prices it** (``read_cost``) before
    anything is sent. Omitted, the request is byte-identical to what it has always been.
    See :data:`~larkdocio.base.errors.COMPOSITE_IS_NOT_ATOMIC`.
    """
    from larkdocio.base.schema_ops_app_table import check_primary_naming, column_kit_disclosure

    kit = check_primary_naming(fields, primary_field_name)
    arguments: Dict[str, Any] = {"app_token": app_token, "name": name}
    traits: Dict[str, Any] = {}
    if kit:
        # The gate's normalised kit IS the argument: it carries exactly the four documented
        # keys, so it is JSON-serialisable into ``plan.to_json()`` and is valid input to the
        # gate again — which is what makes the client seam's re-check a real second check
        # rather than a laxer one over a private shape.
        arguments["fields"] = [dict(column) for column in kit]
        # One table listing plus one field listing: the created table's OWN column list is the
        # only evidence a kit landed (R12), and the plan prices that before anything is sent.
        traits["read_cost"] = 2
    view_note = ""
    if default_view_name is not None:
        arguments["default_view_name"] = default_view_name
        # One more listing: the view's name is read back from the table's OWN view list, because
        # `code:0` on the rename proves acceptance and nothing else (the view route's own
        # swallow control is why). Priced here, before anything is sent.
        traits["read_cost"] = traits.get("read_cost", 1) + 1
        view_note = (f", renaming its default view to {default_view_name!r} in a SECOND call "
                     f"(not atomic)")
    return SchemaRequest(op="create_table", app_token=app_token, arguments=arguments,
                         describe=(f"create table {name!r} in Base {app_token}"
                                   f"{column_kit_disclosure(kit)}{view_note}"),
                         traits=traits)


def batch_create_tables(app_token: str, names, fields=None,
                        accept_locale_default_primary: bool = False,
                        primary_field_name=None) -> SchemaRequest:
    """Create every table in ``names`` in one call.

    **This verb cannot name a primary column, so it asks you to ACKNOWLEDGE that.** Lark ignores
    a per-table ``fields`` array here, so a name cannot be honoured on this route at all; the
    doctrine *"no table is created with a name Lark chose"* is therefore discharged by making
    the silence explicit. Without ``accept_locale_default_primary=True`` the call refuses
    locally with
    :data:`~larkdocio.base.schema_ops_app_table.BATCH_CREATE_LOCALE_DEFAULT_PRIMARY`; with it,
    the request produced is **byte-identical to the one this constructor has always produced**.
    ``primary_field_name=`` draws the same sentence rather than a bare ``TypeError``.

    **``fields`` is REFUSED here, and the refusal is a measurement.** The batch's ``tables`` are
    the same ``ReqTable`` model the single create uses, so a column kit is transportable — and
    Lark **accepts it, answers ``code:0``, and creates every table without it**, each one with the
    locale-named default primary and none of the kit. That was measured on the shipped path and
    again on a hand-written body through the raw HTTP core, so it is the server's behaviour, and
    forwarding the array would be shipping a silent no-op. Use one :func:`create_table` per table
    when the tables need columns; each is still a single call.
    """
    from larkdocio.base.schema_ops_app_table import (
        check_batch_column_kits,
        check_batch_primary_naming,
    )

    names = list(names)
    # The kit refusal first: it is the more specific answer to a caller who passed one.
    check_batch_column_kits(names, fields)
    check_batch_primary_naming(accept_locale_default_primary, primary_field_name)
    return SchemaRequest(op="batch_create_tables", app_token=app_token,
                         arguments={"app_token": app_token, "names": names},
                         describe=f"create {len(names)} table(s) in Base {app_token}")


def rename_table(app_token: str, table_id: str, name: str) -> SchemaRequest:
    """Rename the table ``table_id`` to ``name``."""
    return SchemaRequest(op="rename_table", app_token=app_token, table_id=table_id,
                         arguments={"app_token": app_token, "table_id": table_id,
                                    "name": name},
                         describe=f"rename table {table_id} to {name!r}")


# --------------------------------------------------------------------------- #
# The plan                                                                     #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SchemaPlanEntry:
    """One structural op the plan will make — or one it refuses, decided before any call.

    The attribute names ``table_id`` / ``record_id`` / ``op`` / ``fields`` / ``before`` /
    ``call_index`` are the record engine's, deliberately: they are what
    :class:`~larkdocio.base.plan.ApplyLogEntry`'s constructors read, so this entry rides the
    landed apply-log unchanged instead of a parallel one. ``record_id`` is always ``None`` — a
    schema op has no row, and inventing one would be a lie that survives into the log.
    """

    request: SchemaRequest = dataclass_field(default_factory=SchemaRequest)
    op: str = ""
    app_token: Optional[str] = None
    table_id: Optional[str] = None
    record_id: Optional[str] = None
    fields: Optional[dict] = None
    before: Optional[dict] = None
    call_index: Optional[int] = None
    refusal: Optional[Refusal] = None
    #: Always ``None`` on this rung. The record engine stamps ``active`` / ``unavailable``
    #: here; an app-scoped op has no anchor to stamp, and :attr:`revision_guard_disclosure`
    #: says why in the entry itself rather than leaving an empty slot to be read as "fine".
    revision_guard: Optional[str] = None
    revision_guard_disclosure: str = NO_APP_REVISION_CAS
    scope: str = SCOPE_APP
    asynchronous: bool = False
    read_back: str = ""
    #: How many **read** calls verifying this entry costs. One for the app-and-table family's
    #: single read-back; a field op re-reads the anchor before and after its write as well.
    read_cost: int = 1
    #: A create that also creates a column **in another table** discloses it here, in the
    #: dry run, before the call. ``None`` for every op that reaches exactly one table.
    cross_table_create: Optional[dict] = None
    #: A conversion states the pair and what a capture showed it did to the cells. ``None``
    #: for every op that does not transform existing values.
    conversion: Optional[dict] = None
    #: **What a DESTRUCTIVE op will destroy, enumerated across the whole app** before anything
    #: happens (:mod:`larkdocio.base.loss_preview`) — both columns of a two-way link delete;
    #: every link pointing into a table being deleted, per kind, since a table delete ends the
    #: two kinds differently (a one-way column survives and dangles, a two-way column does not
    #: survive at all, its twin being inside the doomed table); every Lookup column it will
    #: silently blank; and the cell counts. ``None`` for
    #: every non-destructive op, and never ``None`` for a destructive entry that resolved: a
    #: loss that could not be enumerated is a **refusal**, not an empty preview.
    loss_preview: Optional[dict] = None
    #: **Whether THIS entry, as planned, really destroys data** — a MEASURED boolean for an op
    #: that is destructive only in some shapes, where the answer is not knowable from the op
    #: name. ``None`` means *ask the op registry*, which is the right answer for every op that
    #: destroys by its verb. Set from the entry's own loss preview: an option shrink that drops
    #: an option no record holds carries an explicitly empty preview and ``False`` here, so it
    #: applies without a consent token; the same shrink over a populated option carries the
    #: per-record enumeration and ``True``. See :func:`entry_destroys_data`.
    destroys_data: Optional[bool] = None

    @property
    def is_resolved(self) -> bool:
        """True when this entry will be attempted — i.e. it was not refused at plan time."""
        return self.refusal is None

    def with_revision_guard(self, status: str) -> "SchemaPlanEntry":
        return replace(self, revision_guard=status)

    def to_dict(self) -> dict:
        return {
            "op": self.op,
            "app_token": self.app_token,
            "table_id": self.table_id,
            "record_id": self.record_id,
            "fields": self.fields,
            "before": self.before,
            "call_index": self.call_index,
            "refusal": self.refusal.to_dict() if self.refusal is not None else None,
            "revision_guard": self.revision_guard,
            "revision_guard_disclosure": self.revision_guard_disclosure,
            "scope": self.scope,
            "asynchronous": self.asynchronous,
            "read_back": self.read_back,
            "read_cost": self.read_cost,
            "cross_table_create": self.cross_table_create,
            "conversion": self.conversion,
            "loss_preview": self.loss_preview,
            "destroys_data": entry_destroys_data(self),
            "request": self.request.to_dict(),
        }


def entry_destroys_data(entry) -> bool:
    """Whether ``entry`` — **as planned** — will destroy data. The one question the fence asks.

    Three answers in one place, in this order:

    * an entry that **refused** at plan time destroys nothing, because it will not be attempted;
    * an entry carrying a **measured** verdict (:attr:`SchemaPlanEntry.destroys_data`) is taken at
      its word: that is a conditionally destructive op whose loss preview settled the question;
    * otherwise the **request** decides, through
      :func:`larkdocio.base.schema_ops.request_destroys_data` — which is the op registry for
      everything that destroys by its verb.

    Authored here rather than inside :attr:`SchemaPlan.destructive` so the consent helper asks
    the identical question over the identical entry, and a third opinion cannot appear.
    """
    from larkdocio.base.schema_ops import request_destroys_data

    if getattr(entry, "refusal", None) is not None:
        return False
    measured = getattr(entry, "destroys_data", None)
    if measured is not None:
        return bool(measured)
    return request_destroys_data(entry.request)


@dataclass(frozen=True)
class SchemaApplyLogEntry(ApplyLogEntry):
    """The record engine's log entry, extended with what a **structural** op produces.

    A subclass rather than a second type: every accessor on
    :class:`~larkdocio.base.plan.ApplyLog` — ``applied``, ``refusals``, ``dropped``,
    ``indeterminate``, ``not_attempted`` — keeps working, and a consumer who has read one Base
    apply-log has read this one.
    """

    #: The ``app_token`` a create or a copy produced (``None`` for every other op).
    created_app_token: Optional[str] = None
    #: The ``table_id``s a table create or batch create produced.
    created_table_ids: Tuple[str, ...] = ()
    #: How an asynchronous op settled — :meth:`larkdocio.base.schema_settle.SettleOutcome.to_dict`
    #: — or ``None`` for a synchronous one.
    settle: Optional[dict] = None
    #: What was read back, and whether it confirmed the op. Never ``code:0``.
    read_back: Optional[dict] = None

    def to_dict(self) -> dict:
        blob = super().to_dict()
        blob.update({
            "created_app_token": self.created_app_token,
            "created_table_ids": list(self.created_table_ids),
            "settle": self.settle,
            "read_back": self.read_back,
            "revision_guard_disclosure": disclosure_for_op(self.op),
        })
        return blob


class SchemaPlan:
    """An ordered, previewer-backed batch of :class:`SchemaPlanEntry`.

    The **only** input :func:`larkdocio.base.schema_apply.schema_apply` accepts. It cannot be
    hand-forged: the constructor is guarded by a module-private token, so the sole way to obtain
    one is :func:`larkdocio.base.schema_apply.schema_dry_run`. There is intentionally **no**
    ``from_dict`` — a plan is trusted *because* it came from the previewer.
    """

    __slots__ = ("_entries", "_preview_cost")

    def __init__(self, entries=(), *, preview_cost=None, _token: object = None):
        if _token is not _SCHEMA_PLAN_TOKEN:
            raise TypeError(
                "SchemaPlan objects are produced only by "
                "larkdocio.base.schema_apply.schema_dry_run(...); construct a plan via the "
                "previewer, not directly."
            )
        object.__setattr__(self, "_entries", tuple(entries))
        object.__setattr__(self, "_preview_cost", preview_cost)

    @property
    def entries(self) -> Tuple[SchemaPlanEntry, ...]:
        return self._entries

    @property
    def destructive(self) -> bool:
        """``True`` when an entry this plan **will attempt** can lose data.

        The one question :func:`larkdocio.base.schema_apply.schema_apply` asks before it runs
        anything at all: a destructive plan needs explicit consent, so no delete is reachable
        from a default call.

        A destructive entry that **refused** at plan time does not count — it will not be
        attempted, so there is nothing to consent to and the log is free to record the refusal.
        The fence is over what will happen, not over what was asked for.

        **Nor does an entry whose enumerated loss is EMPTY.** An op that destroys only in some
        shapes carries a measured verdict rather than an assumption: a select-option shrink that
        drops an option no record holds is a schema tidy-up, and demanding a token for it would
        make the fence ceremony instead of a fence (:func:`entry_destroys_data`).
        """
        return any(entry_destroys_data(entry) for entry in self._entries)

    @property
    def loss_previews(self) -> Tuple[dict, ...]:
        """Every enumerated loss in this plan, in plan order."""
        return tuple(entry.loss_preview for entry in self._entries
                     if entry.loss_preview is not None)

    @property
    def loss_preview_cost(self) -> Optional[dict]:
        """What the cross-table enumeration cost: read calls, and the tables inspected."""
        return self._preview_cost

    @property
    def resolved(self) -> Tuple[SchemaPlanEntry, ...]:
        return tuple(entry for entry in self._entries if entry.is_resolved)

    @property
    def refusals(self) -> Tuple[SchemaPlanEntry, ...]:
        return tuple(entry for entry in self._entries if not entry.is_resolved)

    @property
    def api_call_count(self) -> int:
        """How many **write** calls this plan will make — one per resolved entry.

        The read-backs and the copy's settle probes are reads, and they are disclosed
        separately by :attr:`read_calls` rather than folded in here, because a consumer
        approving a plan is approving its writes.
        """
        return len(self.resolved)

    @property
    def read_calls(self) -> int:
        """The **minimum** number of read calls verifying this plan will cost: each resolved
        entry's own read budget, plus one settle probe for each asynchronous op. An op that has
        to be asked more than once costs more, which is the point of the settle being bounded.

        The budget is **per entry** rather than one-per-entry because the families verify
        differently: an app-scoped op is confirmed by a single listing, while a field op also
        re-reads its table's anchor on both sides of the write."""
        return (sum(entry.read_cost for entry in self.resolved)
                + sum(1 for entry in self.resolved if entry.asynchronous))

    @property
    def asynchronous(self) -> Tuple[SchemaPlanEntry, ...]:
        return tuple(entry for entry in self._entries if entry.asynchronous)

    def __iter__(self):
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return (f"SchemaPlan(entries={len(self._entries)}, "
                f"refused={len(self.refusals)}, calls={self.api_call_count}, "
                f"async={len(self.asynchronous)})")

    def to_dict(self) -> dict:
        return {
            "api_call_count": self.api_call_count,
            "read_calls": self.read_calls,
            # The consumer-visible disclosure. Always present, and it states what this rung
            # does NOT guard as plainly as what it does.
            "staleness": {
                "no_app_revision_compare_and_swap": NO_APP_REVISION_CAS,
                "verified_by": "read-back",
            },
            "async_settle": ASYNC_SETTLE_CONTRACT,
            # AC4: what the app-scoped enumeration cost, always present on a plan that made
            # one. A consumer approving a destructive plan is approving the reads too.
            "destructive": self.destructive,
            "loss_preview_cost": self._preview_cost,
            "entries": [entry.to_dict() for entry in self._entries],
        }

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), **kwargs)


__all__ = [
    "NO_APP_REVISION_CAS",
    "SCOPE_APP",
    "SCOPE_TABLE",
    "SETTLE_NOT_COMPLETE",
    "SETTLE_NOT_REQUIRED",
    "SchemaApplyLogEntry",
    "SchemaPlan",
    "SchemaPlanEntry",
    "SchemaRequest",
    "batch_create_tables",
    "copy_base",
    "create_base",
    "create_table",
    "disclosure_for_op",
    "entry_destroys_data",
    "rename_base",
    "rename_table",
]
