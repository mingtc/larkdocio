"""larkdocio.base.schema_apply — the plan-gated Base SCHEMA engine.

**The gate, unchanged in kind.** A **non-forgeable** :class:`~larkdocio.base.schema_plan.SchemaPlan`
is produced ONLY by the mandatory :func:`schema_dry_run` previewer, and :func:`schema_apply`
accepts a ``SchemaPlan`` and nothing else — so there is no direct-apply path, no second gate and
no bypass, the shipped shape of all three existing engines
(:mod:`larkdocio.write.preview`, :mod:`larkdocio.sheets.write_apply`,
:mod:`larkdocio.base.apply`).

**No compare-and-swap, and the absence is DISCLOSED (O3″).** ``app.revision`` counts something
the three probe packs cannot agree on, so no guard is built on it and every plan entry carries
:data:`~larkdocio.base.schema_plan.NO_APP_REVISION_CAS` saying so. What replaces it is not
nothing: **every structural op is verified by a READ-BACK.** ``code:0`` is never accepted as
evidence — R12 again, and on this rung it bites hardest, because a structural call that was
accepted and did nothing would leave a consumer building on a table that is not there.

**The copy settles; it does not sleep.** ``copy_app`` is the one asynchronous op on the whole
Base surface. Its read-back is unreachable until the copy exists, so the engine spends a
**bounded, response-driven** settle first (:mod:`larkdocio.base.schema_settle`) and then reads
back. A copy that has not settled inside the budget is logged ``applied-unverified``: the copy
**is** on the tenant — the write returned — and only its verification record is missing.

**No exception escapes.** Every step runs inside :mod:`larkdocio.base.disposition`'s boundary,
so the log is one entry per plan entry, in plan order, whatever happened — the invariant this
surface **declares** against the one authoring in :mod:`larkdocio.capabilities._contracts`,
adding no second id and no second wording.

**The copy carries whatever it carries.** A copied Base can hold a ``Lookup`` (19), a ``Stage``
(24) and a **Button** column — none of which this library authors, and Button by a standing product ruling. The
copy path therefore **filters nothing, warns about nothing and special-cases nothing**: it is a
server-side clone, and a read-back of one may legitimately contain an unregistered pair whose
documented degrade is ``str(value)``. That is the correct behaviour, not a gap to close.
"""
from dataclasses import replace
from typing import Iterable, Optional

from larkdocio.base.disposition import (
    ReadVouch,
    WriteWatch,
    attempted_write,
    classify_apply_exception,
    disposition_refusal,
    plan_wide_platform_anomaly,
    platform_anomaly_halted,
    platform_anomaly_not_attempted,
)
from larkdocio.base.loss_preview import (
    LOSS_MUST_BE_ENUMERABLE,
    SCAN_COST_DISCLOSURE,
    LossNotEnumerable,
    scan_app,
)
from larkdocio.base.plan import ApplyLog, Refusal
from larkdocio.base.schema_ops import (
    destructive_ops,
    registered_families,
    request_destroys_data,
    schema_op,
    schema_ops,
)
from larkdocio.base.schema_plan import (
    NO_APP_REVISION_CAS,
    SCOPE_APP,
    SETTLE_NOT_COMPLETE,
    SchemaApplyLogEntry,
    SchemaPlan,
    SchemaPlanEntry,
    SchemaRequest,
    _SCHEMA_PLAN_TOKEN,
)
from larkdocio.base.schema_settle import DEFAULT_SETTLE_ATTEMPTS, settle
from larkdocio.capabilities._contracts import APPLY_LOG_COMPLETE
from larkdocio.common.staleness import REVISION_GUARD_ACTIVE
from larkdocio.errors import LarkConfigError, gate_refusals

#: The safety contract this surface **declares** — the house invariant the capability registry authors, by
#: reference. The id is imported, never re-spelled. Publishing it on a ``capabilities()``
#: surface belongs to the story that publishes that surface; this engine earns the
#: declaration by carrying the disposition boundary that makes it true.
DECLARED_SAFETY_CONTRACT = APPLY_LOG_COMPLETE

#: The client methods the schema engine **writes** through — projected off the registry rather
#: than hand-listed, so a family registered later cannot be forgotten here (which would make the
#: engine claim "nothing landed" about a call that landed something).
SCHEMA_WRITE_SEAMS = frozenset(descriptor.name for descriptor in schema_ops())

#: The read seams the verification spends: the settle probe and the two read-backs. Declared so
#: the read/write split over the seam is exhaustive and provably so.
SCHEMA_READ_SEAMS = frozenset({"get_app", "list_tables", "list_views", "get_view"})


#: The plan-entry attributes a **family** may declare for its own ops. Named as data so an
#: unknown trait is a loud failure rather than a silently ignored claim.
DECLARABLE_TRAITS = frozenset({
    "scope", "revision_guard", "revision_guard_disclosure", "read_cost",
    "cross_table_create", "conversion",
})


# --------------------------------------------------------------------------- #
# THE EXPLICIT-CONSENT FENCE — no destructive op from a default call            #
# --------------------------------------------------------------------------- #

# The private mint token. Only this module holds it, so a :class:`DestructiveConsent` can be
# built solely through :func:`consent_to_destroy` — the same shape the plan gate itself uses,
# one level in.
_CONSENT_TOKEN = object()


class DestructiveConsentRequired(LarkConfigError, ValueError):
    """A plan that can lose data was applied without consent for **this** plan.

    Raised **before any call**, like the plan-type gate above it: a missing consent is not a
    per-entry failure to log, it is a caller who has not yet read what the delete costs.
    """


class DestructiveConsent:
    """Consent to the enumerated loss of ONE plan.

    Bound to the plan object it was minted from, so consent cannot be carried from a plan a
    caller read to a plan they did not: two dry runs over the same requests are two different
    losses, because the Base may have moved between them.
    """

    __slots__ = ("plan", "losses")

    def __init__(self, plan, losses, *, _token: object = None):
        if _token is not _CONSENT_TOKEN:
            raise TypeError(
                "DestructiveConsent objects are produced only by "
                "larkdocio.base.schema_apply.consent_to_destroy(plan); a look-alike is not "
                "consent.")
        object.__setattr__(self, "plan", plan)
        object.__setattr__(self, "losses", tuple(losses))


def _consentable_plan_types():
    """The plan types consent may be minted over — **one function, one token, one class**.

    A :class:`~larkdocio.base.field_migration.FieldMigrationPlan` is here because the guided
    column-type migration is a **destructive plan one level up**: its delete step is the very
    ``delete_field`` dry run this function already validates, so admitting it at this one door
    is the opposite of adding a second consent primitive. Imported lazily because the migration
    module composes this one.
    """
    from larkdocio.base.field_migration import FieldMigrationPlan

    return (SchemaPlan, FieldMigrationPlan)


def _actionable_lines(entries) -> str:
    """The offending entries' own fix text, one line each, ready to LEAD the message.

    The per-entry :class:`~larkdocio.base.plan.Refusal` already names the exact call to make —
    it is the best text this surface produces, and it was previously reachable only by writing a
    second script to print it. So it is **hoisted verbatim** into the raised exception rather
    than summarised: the caller who prints only the exception learns the fix.

    Two details matter. The refusal's own text already ends with
    :data:`~larkdocio.base.loss_preview.LOSS_MUST_BE_ENUMERABLE`, which the message appends
    **once** at the end — so the trailing copy is lifted off here rather than left to land in
    the middle of the message, where it would push the fix behind the doctrine again. And an
    entry with **no** refusal to hoist (a destructive entry carrying no loss preview) still gets
    an actionable line, derived from the entry's own description, so neither branch degrades to
    "go and look".
    """
    lines = []
    for entry in entries:
        refusal = getattr(entry, "refusal", None)
        detail = (refusal.detail or "") if refusal is not None else ""
        if detail:
            detail = detail.replace(LOSS_MUST_BE_ENUMERABLE, "").strip()
        else:
            detail = (
                f"{getattr(entry.request, 'describe', '') or entry.op} is a DESTRUCTIVE "
                "operation carrying no enumerated loss, so there is nothing to consent to. "
                "Re-run schema_dry_run with read_client=BaseReadClient(...) and read the "
                "entry's loss_preview before consenting. Nothing was planned and nothing was "
                "sent.")
        lines.append(f"- {detail}")
    return "\n".join(lines)


def consent_to_destroy(plan) -> DestructiveConsent:
    """Consent to everything ``plan``'s dry run enumerated — the ONE way a delete may run.

    Takes the :class:`~larkdocio.base.schema_plan.SchemaPlan` ``schema_dry_run`` produced, or
    the :class:`~larkdocio.base.field_migration.FieldMigrationPlan` ``plan_field_migration``
    produced — whose enumerated loss **is** its delete step's, unchanged. Same class, same
    private token, same refusals either way.

    Refuses to mint over a destructive entry that carries **no** loss preview: consent is
    consent to an enumerated loss, and an entry whose enumeration refused has none to consent
    to. Re-plan and read the refusal instead.

    **Which entries count is asked of the REQUEST, not of the op name**
    (:func:`~larkdocio.base.schema_ops.request_destroys_data`), because one shipped op destroys in
    exactly one shape: an ``update_field`` that replaces a select column's option set. So a
    select-option shrink whose loss refused cannot be consented to either, and a plain column
    rename in the same plan still costs nothing.
    """
    if not isinstance(plan, _consentable_plan_types()):
        raise DestructiveConsentRequired(
            "consent_to_destroy() takes the SchemaPlan that schema_dry_run() produced, or the "
            "FieldMigrationPlan that plan_field_migration() produced — the plan carrying the "
            "loss preview you are consenting to; got "
            f"{type(plan).__name__}.")
    unpreviewed = [entry for entry in plan.entries
                   if request_destroys_data(entry.request) and entry.refusal is None
                   and entry.loss_preview is None]
    if unpreviewed:
        raise DestructiveConsentRequired(
            f"{_actionable_lines(unpreviewed)}\n"
            f"Consent was refused: these destructive entries carry no loss preview: "
            f"{[entry.op for entry in unpreviewed]}. Nothing was planned and nothing was sent. "
            f"{LOSS_MUST_BE_ENUMERABLE}")
    refused = [entry for entry in plan.entries
               if request_destroys_data(entry.request) and entry.refusal is not None]
    if refused:
        raise DestructiveConsentRequired(
            f"{_actionable_lines(refused)}\n"
            f"Consent was refused: these destructive entries REFUSED at plan time and there is "
            f"nothing to consent to: {[entry.op for entry in refused]}. Fix what the line(s) "
            f"above name and re-run schema_dry_run. Nothing was planned and nothing was sent. "
            f"{LOSS_MUST_BE_ENUMERABLE}")
    return DestructiveConsent(plan, plan.loss_previews, _token=_CONSENT_TOKEN)


def _safe_route_lines(plan) -> str:
    """The ordering advice the plan's own previews carry, hoisted to the refusal.

    A preview may name **the safe way to get what the caller wanted** — an option shrink names
    *remap the records off the option, then shrink* — and that sentence is worth nothing sitting
    inside a preview the caller has not printed yet. So it leads the refusal, the same reasoning
    :func:`_actionable_lines` is built on. Deduplicated and empty for a plan whose previews name
    no alternative route (a column or table delete has none: the loss IS the operation).
    """
    lines = []
    for loss in plan.loss_previews:
        route = (loss or {}).get("remap_first")
        if route and route not in lines:
            lines.append(route)
    return ("\n" + "\n".join(f"- {route}" for route in lines)) if lines else ""


def _check_consent(plan, consent) -> None:
    """The fence itself. A non-destructive plan never reaches it."""
    if not plan.destructive:
        return
    if not isinstance(consent, DestructiveConsent):
        raise DestructiveConsentRequired(
            "this plan contains an operation that DESTROYS DATA, so it cannot be applied from "
            "a default call: pass consent=larkdocio.base.schema_apply.consent_to_destroy(plan) "
            "after reading each entry's loss_preview, which names every column and every table "
            "the delete reaches — including tables you did not name, and every RECORD an option "
            f"shrink empties.{_safe_route_lines(plan)}\nNothing was sent. "
            f"{LOSS_MUST_BE_ENUMERABLE}")
    if consent.plan is not plan:
        raise DestructiveConsentRequired(
            "this consent was minted for a DIFFERENT plan. A loss preview describes the Base "
            "as it was when that plan was built, so consent does not carry across: re-run "
            "schema_dry_run, read the new preview, and consent to that plan. Nothing was sent.")


def _declared_traits(request: SchemaRequest) -> dict:
    """A request's own family traits, validated against :data:`DECLARABLE_TRAITS`."""
    traits = dict(getattr(request, "traits", None) or {})
    unknown = sorted(set(traits) - DECLARABLE_TRAITS)
    if unknown:
        raise ValueError(
            f"{request.op!r} declares plan traits the engine does not carry: {unknown}. A "
            f"family declares only {sorted(DECLARABLE_TRAITS)}; anything else would be a "
            "claim nothing reads.")
    return traits


def _family_handlers(attribute: str) -> dict:
    """``{op name: handler}`` merged across every registered family, or ``{}``.

    Each family module may publish ``ISSUE_HANDLERS`` / ``READ_BACK_HANDLERS``; a family that
    publishes neither is served by this module's own dispatch below. That is what lets a new
    family ship its calls **in its own file** instead of editing this one.
    """
    import importlib

    handlers = {}
    for family in registered_families():
        handlers.update(getattr(importlib.import_module(family.module), attribute, {}) or {})
    return handlers


# --------------------------------------------------------------------------- #
# schema_dry_run — the mandatory previewer. Offline: zero API calls.            #
# --------------------------------------------------------------------------- #

def _loss_refusal(detail: str) -> Refusal:
    return Refusal(reason=Refusal.LOSS_NOT_ENUMERABLE, detail=detail)


def schema_dry_run(requests: Iterable[SchemaRequest], *, read_client=None) -> SchemaPlan:
    """Typed structural requests → the :class:`SchemaPlan` :func:`schema_apply` will take.

    **Zero API calls for a non-destructive plan** — unchanged. An unregistered op is a
    plan-time refusal costing nothing, and every entry is stamped with its own descriptor's
    asynchrony and read-back rule, so the plan a consumer approves says how each op will be
    verified before a single request goes out.

    **A DESTRUCTIVE plan pays for reads, and says how many.** A delete's blast radius is not
    table-scoped on this API, so the previewer scans the whole app — every table's columns —
    and attaches a :attr:`~larkdocio.base.schema_plan.SchemaPlanEntry.loss_preview` naming every
    column and every table the delete reaches. ``read_client`` is therefore **required** for a
    destructive request; without it, and whenever the scan cannot be completed, the entry
    **refuses** with zero writes rather than planning a delete whose cost nobody can see. That
    is the Sheets structural rung's invariant with a wider scope, not a new rule.

    **A destructive SHAPE pays the same price as a destructive VERB.** Whether an entry needs a
    loss preview is asked of the **request** rather than of the op name
    (:func:`~larkdocio.base.schema_ops.request_destroys_data`), because one shipped op destroys in
    exactly one shape: an ``update_field`` that REPLACES a select column's option set drops the
    cells of any option it omits. Such an entry demands ``read_client`` and refuses without it,
    exactly as ``delete_field`` does — and its preview then answers the question the op name
    could not, *does this actually destroy anything?*, so a shrink that drops an option no record
    holds carries an explicitly empty preview and applies with no consent token. Every other
    ``update_field`` — a rename, a currency format, a date format — still costs zero reads.

    The scan is made **once per plan**, however many destructive entries ride it, and its cost
    is disclosed on the plan.
    """
    if isinstance(requests, SchemaRequest):
        requests = (requests,)
    requests = list(requests)
    destructive = destructive_ops()
    loss_handlers = _family_handlers("LOSS_PREVIEW_HANDLERS")

    scans: dict = {}
    scan_failures: dict = {}

    def _scan_for(app_token):
        """The app's schema, scanned once per plan and remembered — including its refusal."""
        if app_token in scan_failures:
            raise scan_failures[app_token]
        if app_token not in scans:
            try:
                scans[app_token] = scan_app(read_client, app_token)
            except LossNotEnumerable as exc:
                scan_failures[app_token] = exc
                raise
        return scans[app_token]

    entries = []
    for index, request in enumerate(requests):
        if not isinstance(request, SchemaRequest):
            raise TypeError(
                "schema_dry_run takes the typed requests in larkdocio.base.schema_plan — "
                "create_base(...), rename_base(...), copy_base(...), create_table(...), "
                "batch_create_tables(...), rename_table(...) — so the plan names ops the "
                f"library actually ships; got {type(request).__name__}.")
        try:
            descriptor = schema_op(request.op)
        except KeyError:
            entries.append(SchemaPlanEntry(
                request=request, op=request.op, app_token=request.app_token,
                table_id=request.table_id, fields=dict(request.arguments),
                refusal=Refusal(
                    reason=Refusal.INVALID_REQUEST,
                    detail=(f"{request.op!r} is not a registered Base schema op, so nothing "
                            "is planned for it and no call is made. The shipped set is: "
                            f"{', '.join(d.name for d in schema_ops())}."))))
            continue
        # ---- the CROSS-TABLE loss preview, for the ops that destroy ---------- #
        loss = None
        refusal = None
        destroys = None
        if request_destroys_data(request):
            if read_client is None:
                refusal = _loss_refusal(
                    f"{request.describe} is a DESTRUCTIVE operation and no read client was "
                    f"given, so nothing could be read and its loss could not be enumerated. "
                    f"Pass read_client=BaseReadClient(...) to schema_dry_run. Nothing was "
                    f"planned and nothing was sent. {LOSS_MUST_BE_ENUMERABLE}")
            else:
                try:
                    loss = loss_handlers[descriptor.name](
                        _scan_for(request.app_token), request)
                except LossNotEnumerable as exc:
                    refusal = _loss_refusal(
                        f"{request.describe} REFUSED before anything was sent: {exc.shortfall} "
                        f"{LOSS_MUST_BE_ENUMERABLE}")
            # An op that destroys only in some SHAPES gets its verdict from its own enumeration,
            # and the default when a preview does not say is **True** — a fence that guessed
            # "harmless" would be the defect this stamp exists to close.
            if loss is not None and descriptor.name not in destructive:
                destroys = bool(loss.get("destroys", True))

        entries.append(SchemaPlanEntry(
            request=request,
            op=descriptor.name,
            app_token=request.app_token,
            table_id=request.table_id,
            fields=dict(request.arguments),
            call_index=index,
            asynchronous=descriptor.settles,
            read_back=descriptor.read_back,
            loss_preview=loss,
            destroys_data=destroys,
            refusal=refusal,
            # A family declares what the engine cannot know about its own ops — its scope, its
            # anchor and disclosure, its read budget, its op-specific disclosures. Unknown keys
            # are a family bug, so they raise here rather than being silently dropped.
            **_declared_traits(request),
        ))

    # Disclosed only when a scan actually completed: a refused scan's own refusal says what
    # could not be read, and claiming a cost for a scan that did not finish would be a number
    # standing in for an answer.
    cost = None
    if scans:
        cost = {
            "read_calls": sum(scan.read_calls for scan in scans.values()),
            "tables_inspected": sorted({table_id for scan in scans.values()
                                        for table_id in scan.tables_inspected}),
            "what": SCAN_COST_DISCLOSURE,
        }
    return SchemaPlan(entries=entries, preview_cost=cost, _token=_SCHEMA_PLAN_TOKEN)


# --------------------------------------------------------------------------- #
# The one call each entry makes                                                 #
# --------------------------------------------------------------------------- #

def _issue(watch, entry: SchemaPlanEntry):
    """Make ONE schema call. The only place this module touches the schema client."""
    handler = _family_handlers("ISSUE_HANDLERS").get(entry.op)
    if handler is not None:
        return handler(watch, entry)
    arguments = dict(entry.fields or {})
    if entry.op == "create_app":
        return watch.create_app(arguments["name"], arguments.get("folder_token"),
                                arguments.get("time_zone"))
    if entry.op == "rename_app":
        return watch.rename_app(arguments["app_token"], arguments["name"])
    if entry.op == "copy_app":
        return watch.copy_app(arguments["app_token"], arguments["name"],
                              arguments.get("without_content", False),
                              arguments.get("folder_token"))
    if entry.op == "create_table":
        return watch.create_table(arguments["app_token"], arguments["name"])
    if entry.op == "batch_create_tables":
        return watch.batch_create_tables(arguments["app_token"], arguments["names"])
    return watch.rename_table(arguments["app_token"], arguments["table_id"],
                              arguments["name"])


def _token_of(reply) -> Optional[str]:
    return getattr(reply, "app_token", None)


# --------------------------------------------------------------------------- #
# The read-back — never code:0                                                  #
# --------------------------------------------------------------------------- #

def _table_index(read_client, app_token) -> dict:
    return {getattr(table, "table_id", None): getattr(table, "name", None)
            for table in (read_client.list_tables(app_token) or ())}


def _read_back(read_client, entry: SchemaPlanEntry, reply, created_app_token):
    """``(confirmed, disclosure)`` for one landed op, read from the server's own state.

    One listing per entry, never a spot check and never a ``code:0``. A ``batch_create`` is
    verified by **one** read-back covering **every** id it returned, which is what makes the
    batch a single verifiable unit rather than N optimistic ones.

    A family with its own read-back publishes it in ``READ_BACK_HANDLERS`` beside its
    descriptors — the view family's comparison is a *semantic* one over a persisted filter, not
    a name lookup in a listing — and is dispatched to here.
    """
    handler = _family_handlers("READ_BACK_HANDLERS").get(entry.op)
    if handler is not None:
        return handler(read_client, entry, reply, created_app_token)
    arguments = dict(entry.fields or {})
    if entry.op in ("create_app", "rename_app"):
        token = created_app_token or arguments["app_token"]
        app = read_client.get_app(token)
        seen = getattr(app, "name", None)
        return seen == arguments["name"], {
            "how": entry.read_back, "app_token": token, "name": seen,
            "expected": arguments["name"]}

    if entry.op == "copy_app":
        tables = _table_index(read_client, created_app_token)
        return bool(tables), {
            "how": entry.read_back, "app_token": created_app_token,
            "table_ids": sorted(t for t in tables if t)}

    if entry.op == "create_table":
        tables = _table_index(read_client, arguments["app_token"])
        return reply in tables, {
            "how": entry.read_back, "table_ids": [reply], "listed": reply in tables}

    if entry.op == "batch_create_tables":
        tables = _table_index(read_client, arguments["app_token"])
        created = list(reply or ())
        missing = [table_id for table_id in created if table_id not in tables]
        return bool(created) and not missing, {
            "how": entry.read_back, "table_ids": created, "missing": missing,
            "read_backs": 1}

    tables = _table_index(read_client, arguments["app_token"])
    seen = tables.get(arguments["table_id"])
    return seen == arguments["name"], {
        "how": entry.read_back, "table_id": arguments["table_id"], "name": seen,
        "expected": arguments["name"]}


def _not_observed(entry, disclosure) -> Refusal:
    return Refusal(
        reason=Refusal.WRITE_NOT_OBSERVED,
        detail=(f"{entry.request.describe} answered code:0 and the READ-BACK does not show "
                f"it: {disclosure}. On this API a `code:0` is not evidence a write happened — "
                "unrecognised input is silently ignored — so this is reported as dropped "
                "rather than applied. The engine does NOT retry: it reports what it observed, "
                "and re-sending would be a guess about why the call had no effect."))


def _live_anchor(read_client, entry: SchemaPlanEntry):
    """A **table-scoped** entry's live ``table.revision``, or ``None``.

    The only anchor this surface has. An app-scoped entry never reaches here: it declares no
    revision guard, because `app.revision` counts something no two probe packs agree on.
    """
    for table in (read_client.list_tables(entry.app_token) or ()):
        if getattr(table, "table_id", None) == entry.table_id:
            return getattr(table, "revision", None)
    return None


def _stale_refusal(entry, planned, live) -> Refusal:
    return Refusal(
        reason=Refusal.STALE_BASE,
        detail=(
            f"table {entry.table_id} moved under this plan: `table.revision` was {planned!r} "
            f"when the plan was built and reads {live!r} now, so something else changed this "
            f"table in between. ZERO writes were issued for this entry. Re-read the table, "
            f"re-plan and re-apply. This compare is CLIENT-SIDE — there is no If-Match on this "
            f"API — so it closes the window between the plan and the write, not the last "
            f"microsecond between the compare and the write itself."))


def _not_attempted(entry, *, where: str, why: str, anomaly=None) -> SchemaApplyLogEntry:
    """One skipped entry, TYPED and EXPLAINED — the tail the house log-completeness invariant
    (:data:`~larkdocio.capabilities._contracts.APPLY_LOG_COMPLETE`) promises.

    ``anomaly`` is the halt's own ``platform_anomaly`` record when the batch stopped on the
    plan-wide anomaly (LD-338): the skipped entry then names **that** as the cause, because "the
    batch halted at X (api-error)" leaves a reader to wonder whether their entry was the problem
    — and it was never sent.
    """
    if anomaly is not None:
        detail = platform_anomaly_not_attempted(where, anomaly.get("code"))
    else:
        detail = (f"the batch halted at {where} ({why}), so this entry was never attempted and "
                  "NOTHING was sent for it. Re-run schema_dry_run before applying the "
                  "remainder: the Base may have moved, and this rung has no revision guard "
                  "that would notice.")
    return SchemaApplyLogEntry.not_attempted(entry, refusal=Refusal(
        reason=Refusal.NOT_ATTEMPTED, detail=detail))


def _vouched_ids(read_client, plan) -> set:
    """The table ids this run's READ side has vouched for. Adds NO call, ever.

    Two read-side artifacts, both already paid for: the :class:`ReadVouch` proxy's record of the
    listings the engine itself made, and the dry run's own cross-table scan.
    """
    vouched = set(read_client.vouched_table_ids)
    vouched.update((plan.loss_preview_cost or {}).get("tables_inspected") or ())
    return vouched


# --------------------------------------------------------------------------- #
# schema_apply — the one seam every schema write passes through                 #
# --------------------------------------------------------------------------- #

def schema_apply(plan, *, client, read_client, consent=None,
                 settle_attempts: int = DEFAULT_SETTLE_ATTEMPTS, sleep=None,
                 allow_partial: bool = False) -> ApplyLog:
    """Apply a :class:`~larkdocio.base.schema_plan.SchemaPlan`, returning the record engine's
    :class:`~larkdocio.base.plan.ApplyLog`.

    ``client`` is a :class:`~larkdocio.base.schema_client.BaseSchemaClient` (duck-typed) and
    ``read_client`` a :class:`~larkdocio.base.client.BaseReadClient` (duck-typed): **both** are
    required, because every op here is verified by a read-back and the one asynchronous op is
    settled by a read. An engine that cannot read cannot verify, and this rung has no revision
    guard to fall back on.

    The log is one entry per plan entry, in plan order, on every run.

    **An entry that did not land RAISES** :class:`~larkdocio.errors.LarkApplyRefusedError`
    unless ``allow_partial=True`` — the same spelling the record engine and the docx and
    sheets engines take. A ``dropped`` structural op (``code:0``
    that changed nothing, which only the read-back can see) is exactly the silent half-success
    this ruling exists to stop being mistaken for a clean run.
    """
    if not isinstance(plan, SchemaPlan):
        raise TypeError(
            "schema_apply() takes a SchemaPlan produced by "
            "larkdocio.base.schema_apply.schema_dry_run(...) and nothing else — a list of "
            "requests, a dict or a look-alike is not a plan; got "
            f"{type(plan).__name__}.")
    if client is None or read_client is None:
        raise TypeError(
            "schema_apply() needs BOTH a schema client and a read client: there is no "
            "`app.revision` compare-and-swap on this rung, so every structural op is verified "
            "by a READ-BACK — and the one asynchronous op is settled by a read.")
    # THE CONSENT FENCE. Before anything else, and before any call: a plan that can lose data
    # is not applied from a default call.
    _check_consent(plan, consent)

    # Every read below goes through the VOUCH proxy: it adds no call, it only remembers which
    # table ids the listings the engine already makes came back with. That set is the evidence
    # behind the plan-wide platform-anomaly claim at the end of this function (LD-337).
    read_client = ReadVouch(read_client)

    results = [None] * len(plan.entries)
    #: One record per write call ISSUED — the post-hoc evidence "every entry refused, the same
    #: way". Kept here because a log entry keeps the refusal's prose, not Lark's code.
    attempts = []
    halt = None

    for position, entry in enumerate(plan.entries):
        if halt is not None:
            results[position] = _not_attempted(entry, where=halt["where"],
                                               why=halt["reason"],
                                               anomaly=halt.get("platform_anomaly"))
            continue
        if entry.refusal is not None:
            results[position] = SchemaApplyLogEntry.refused(entry, refusal=entry.refusal)
            continue

        where = entry.request.describe

        # ---- STALE_BASE, for the entries that HAVE an anchor ---------------- #
        # A table-scoped op rides `table.revision` exactly as the record engine does: re-read
        # it immediately before the write and refuse, with zero writes, if it moved. An
        # app-scoped op declares no guard and skips this entirely — there is no anchor to
        # compare, which its own entry discloses rather than implies away.
        if entry.revision_guard == REVISION_GUARD_ACTIVE:
            planned = (entry.fields or {}).get("revision")
            try:
                live = _live_anchor(read_client, entry)
            except Exception as exc:        # noqa: BLE001 — the boundary, before any write
                disposition = classify_apply_exception(exc, wrote=False)
                refusal = disposition_refusal(disposition, exc,
                                              where=f"the anchor read for {where}",
                                              wrote_seams=())
                results[position] = SchemaApplyLogEntry.refused(entry, refusal=refusal)
                if disposition.halts:
                    halt = {"index": position, "reason": refusal.reason,
                            "detail": refusal.detail, "where": where}
                continue
            if live is not None and planned is not None and live != planned:
                results[position] = SchemaApplyLogEntry.stale(
                    entry, refusal=_stale_refusal(entry, planned, live))
                continue

        watch = WriteWatch(client, seams=SCHEMA_WRITE_SEAMS)
        try:
            reply = _issue(watch, entry)
        except Exception as exc:            # noqa: BLE001 — the boundary's whole job
            disposition = classify_apply_exception(exc, wrote=watch.wrote)
            refusal = disposition_refusal(disposition, exc, where=where,
                                          wrote_seams=watch.completed)
            attempts.append(attempted_write(position, entry.table_id,
                                            disposition=disposition, exc=exc))
            if disposition.outcome == "applied-unverified":
                results[position] = SchemaApplyLogEntry.applied_unverified(
                    entry, refusal=refusal)
            elif disposition.outcome == "failed":
                results[position] = SchemaApplyLogEntry.failed(entry, refusal=refusal)
            else:
                results[position] = SchemaApplyLogEntry.refused(entry, refusal=refusal)
            if disposition.halts:
                halt = {"index": position, "reason": refusal.reason,
                        "detail": refusal.detail, "where": where}
            elif position + 1 < len(plan.entries):
                # ---- THE PLATFORM-ANOMALY PREFIX HALT (LD-338) ------------- #
                # The classifier's own verdict on this exception stands (D4′ is untouched: an
                # api-error is still entry-scoped, and `disposition.halts` is still False). What
                # is decided HERE, one level up, is a PLAN question the classifier cannot see:
                # every call this plan has attempted refused identically on ids this run's own
                # read client listed, so the remaining calls would answer the same way. The
                # predicate is the plan-wide one, evaluated over the PREFIX in hand — same
                # threshold, same six conditions, no second rule to drift. It reads only what
                # the loop already holds and makes NO call; a tail-less prefix (this was the
                # last entry) is left alone, because a batch that ran to the end did continue.
                prefix = plan_wide_platform_anomaly(
                    attempts, vouched_table_ids=_vouched_ids(read_client, plan))
                if prefix is not None:
                    halt = {"index": position, "reason": refusal.reason,
                            "detail": refusal.detail, "where": where,
                            "platform_anomaly": prefix.to_dict()}
            continue

        # The call RETURNED, so something may have landed: recorded as an attempt with no
        # refusal, which is what disqualifies this run from the plan-wide anomaly verdict.
        attempts.append(attempted_write(position, entry.table_id))

        created_app_token = _token_of(reply)
        created_table_ids = ()
        if entry.op == "create_table" and reply:
            created_table_ids = (reply,)
        elif entry.op == "batch_create_tables":
            created_table_ids = tuple(reply or ())

        # ---- the settle, for the one asynchronous op ------------------------ #
        settle_blob = None
        if entry.asynchronous:
            token = created_app_token
            try:
                outcome = settle(lambda: read_client.get_app(token),
                                 attempts=settle_attempts, sleep=sleep)
            except Exception as exc:        # noqa: BLE001 — the boundary again
                disposition = classify_apply_exception(exc, wrote=True)
                refusal = disposition_refusal(disposition, exc,
                                              where=f"the settle probe for {where}",
                                              wrote_seams=watch.completed)
                results[position] = replace(
                    SchemaApplyLogEntry.applied_unverified(entry, refusal=refusal),
                    created_app_token=created_app_token)
                if disposition.halts:
                    halt = {"index": position, "reason": refusal.reason,
                            "detail": refusal.detail, "where": where}
                continue
            settle_blob = outcome.to_dict()
            if not outcome.settled:
                refusal = Refusal(
                    reason=SETTLE_NOT_COMPLETE,
                    detail=(f"{where} RETURNED — the copy IS on the tenant — but it had not "
                            f"settled after {outcome.attempts} bounded attempt(s): "
                            f"{outcome.detail}"))
                results[position] = replace(
                    SchemaApplyLogEntry.applied_unverified(entry, refusal=refusal),
                    created_app_token=created_app_token, settle=settle_blob)
                continue

        # ---- the read-back: the ONLY evidence this rung accepts -------------- #
        try:
            confirmed, disclosure = _read_back(read_client, entry, reply, created_app_token)
        except Exception as exc:            # noqa: BLE001 — the boundary, third time
            disposition = classify_apply_exception(exc, wrote=True)
            refusal = disposition_refusal(disposition, exc,
                                          where=f"the read-back for {where}",
                                          wrote_seams=watch.completed)
            results[position] = replace(
                SchemaApplyLogEntry.applied_unverified(entry, refusal=refusal),
                created_app_token=created_app_token,
                created_table_ids=created_table_ids, settle=settle_blob)
            if disposition.halts:
                halt = {"index": position, "reason": refusal.reason,
                        "detail": refusal.detail, "where": where}
            continue

        if not confirmed:
            results[position] = replace(
                SchemaApplyLogEntry.dropped(entry, refusal=_not_observed(entry, disclosure)),
                created_app_token=created_app_token,
                created_table_ids=created_table_ids, settle=settle_blob,
                read_back=disclosure)
            continue

        results[position] = replace(
            SchemaApplyLogEntry.applied(entry),
            created_app_token=created_app_token, created_table_ids=created_table_ids,
            settle=settle_blob, read_back=disclosure)

    for position, entry in enumerate(plan.entries):
        if results[position] is None:
            results[position] = _not_attempted(
                entry,
                where=(halt or {}).get("where", "an earlier entry"),
                why=(halt or {}).get("reason", Refusal.NOT_ATTEMPTED),
                anomaly=(halt or {}).get("platform_anomaly"))

    if halt is not None:
        halt["not_attempted"] = sum(1 for entry in results
                                    if entry.outcome == "not-attempted")

    # ---- the PLAN-WIDE platform-anomaly disclosure (LD-337) ----------------- #
    # Only knowable HERE: "every entry refused with the same code" cannot be evaluated while the
    # first refusal is being built. The two read-side artifacts that can vouch for an id are the
    # dry run's own cross-table scan and this run's listings; neither is re-read, and no call is
    # added. The disclosure is APPENDED to each matching detail after that detail was formatted
    # — `protected_last_advice`'s precedent, chosen for the same reason.
    anomaly = plan_wide_platform_anomaly(
        attempts, vouched_table_ids=_vouched_ids(read_client, plan))
    if anomaly is not None:
        # If the run HALTED on this anomaly (LD-338), the `CONTINUED` aftermath these details
        # were formatted with is now false — the batch stopped. It is re-stated, in place, before
        # the disclosure is appended: Lark's own code and msg are never touched.
        halted_here = halt is not None and "platform_anomaly" in halt
        for position in anomaly.positions:
            logged = results[position]
            detail = logged.refusal.detail
            if halted_here:
                detail = platform_anomaly_halted(detail)
            results[position] = replace(
                logged,
                refusal=replace(logged.refusal,
                                detail=f"{detail} {anomaly.disclosure}"))

    log = ApplyLog(entries=tuple(results), halt=halt,
                   platform_anomaly=None if anomaly is None else anomaly.to_dict())
    return gate_refusals(log, allow_partial=allow_partial,
                         surface="larkdocio.base.schema_apply.schema_apply")


__all__ = [
    "DECLARED_SAFETY_CONTRACT",
    "DestructiveConsent",
    "DestructiveConsentRequired",
    "SCHEMA_READ_SEAMS",
    "SCHEMA_WRITE_SEAMS",
    "consent_to_destroy",
    "schema_apply",
    "schema_dry_run",
]
