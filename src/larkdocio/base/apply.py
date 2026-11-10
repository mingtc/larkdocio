"""larkdocio.base.apply — the plan-gated Base record-write engine.

**The gate.** A **non-forgeable** :class:`~larkdocio.base.plan.Plan` is produced ONLY by the
mandatory :func:`dry_run` previewer, and :func:`apply` accepts a ``Plan`` and nothing else — so
there is no direct-apply path, the shipped shape of both existing engines
(:mod:`larkdocio.sheets.write_apply`, :mod:`larkdocio.write.preview`).

**``STALE_BASE`` is a CLIENT-SIDE read-compare-write, and this module does not pretend
otherwise.** There is no server-side compare-and-swap on a Base: a record ``PUT`` carrying
bogus ``revision`` / ``last_modified_time`` body keys answered ``code:0`` **and applied the
write** (``05-08``). So no precondition key is sent — sending one would be a lie that reads
like safety — and instead the engine **reads ``table.revision``, compares it, then writes**.
:data:`~larkdocio.base.plan.NO_SERVER_SIDE_CAS` states what that buys and what it does not:
the window between the plan and the write is closed; the last microsecond between the compare
and the write is not.

That is also why :func:`apply` requires a **read seam**: a client-side compare-and-swap that
cannot read cannot compare. There is no argument that turns the guard off.

**The write-effect oracle.** ``code:0`` is not evidence a write happened — the Stage discard
answered ``code:0`` with the anchor provably unmoved (``25 → 25``, against a positive control
that moved ``1 → 2``; ``p1-q2-02``). Base hands us the detector for free: the anchor read is
already in the apply path, so every call is followed by one, and **a call that did not move the
anchor is logged ``dropped``, never ``applied``.** Deliberate scope fence: this is a
**detection** requirement, not a retry requirement. The engine reports; it does not guess and
re-send.

**The halt scope is per table.** ``table.revision`` is isolated per table, so a
``stale-base`` refusal stops **that table's** entries — zero writes for it — and every other
table is still judged against its own anchor. A *systemic* exception (a scope denial, a rate
limit, a transport failure, an answer about the table or the app) halts the whole batch, and
every remaining entry is logged ``not-attempted`` naming where and why.

**No exception escapes.** Every step runs inside :mod:`larkdocio.base.disposition`'s boundary,
so the log is one entry per plan entry, in plan order, whatever happened — the invariant this
surface **declares** (:data:`DECLARED_SAFETY_CONTRACT`) against the one authoring in
:mod:`larkdocio.capabilities._contracts`, adding no second id and no second wording.
"""
from typing import Optional

from larkdocio.base.compiler import compile_base, compile_table
from larkdocio.base.disposition import (
    WriteWatch,
    classify_apply_exception,
    disposition_refusal,
)
from larkdocio.base.plan import (
    ApplyLog,
    ApplyLogEntry,
    Plan,
    Refusal,
    TablePlan,
    _PLAN_TOKEN,
)
from larkdocio.base.table import assemble_table
from larkdocio.capabilities._contracts import APPLY_LOG_COMPLETE
from larkdocio.errors import gate_refusals

#: The safety contract this surface **declares** — the house invariant LD-254 authored, by
#: reference. The id is imported, never re-spelled, and the wording lives in exactly one
#: module; this engine earns the declaration by carrying the disposition boundary that makes
#: it true (:mod:`larkdocio.base.disposition`). Publishing it on the ``base-write`` surface of
#: ``capabilities()`` belongs to the story that publishes that surface.
DECLARED_SAFETY_CONTRACT = APPLY_LOG_COMPLETE


# --------------------------------------------------------------------------- #
# dry_run — the mandatory previewer. Offline: zero API calls.                   #
# --------------------------------------------------------------------------- #

def dry_run(draft, *, records_per_call: Optional[int] = None) -> Plan:
    """A draft (:class:`~larkdocio.base.model.TableDraft` or
    :class:`~larkdocio.base.model.BaseDraft`) → the :class:`~larkdocio.base.plan.Plan`
    :func:`apply` will take.

    **Zero API calls.** The diff is computed from the snapshot the caller already holds and the
    values are encoded by the write-shape registry, so everything knowable before any call is decided
    here: a computed-field edit and a value that is not its field's write shape are **plan-time
    refusals** that cost nothing.

    ``records_per_call`` chunks each family's batch call. The default is one call per family
    per table: this repository has **not probed** the API's per-call record ceiling, so the
    engine asserts none — a caller who knows their tenant's limit sets it, and the plan then
    shows exactly which records ride in which call.
    """
    snapshot = getattr(draft, "snapshot", None)
    if snapshot is None or not hasattr(draft, "diff"):
        raise TypeError(
            "dry_run takes a draft over a snapshot — snapshot_table(...).edit() or "
            "snapshot_base(...).edit() — so the plan is built against a read the model can "
            f"vouch for; got {type(draft).__name__}.")

    if hasattr(snapshot, "tables"):
        tables = compile_base(draft.diff(), snapshot, records_per_call=records_per_call)
        app_token = snapshot.app_token
    else:
        table_plan = compile_table(draft.diff(), snapshot, records_per_call=records_per_call)
        tables = (table_plan,) if table_plan.entries else ()
        app_token = snapshot.app_token
    return Plan(app_token=app_token, tables=tables, _token=_PLAN_TOKEN)


# --------------------------------------------------------------------------- #
# apply — the one seam every write passes through                               #
# --------------------------------------------------------------------------- #

def _live_anchor(read_client, app_token, table_id):
    """``(revision, found)`` for one table, read through the ordinary table listing.

    The **only** compare-and-swap anchor bitable exposes, and one integer, so the guard costs a
    single read per table plus one per call (which the write-effect oracle needs anyway).
    """
    for table in (read_client.list_tables(app_token) or ()):
        if getattr(table, "table_id", None) == table_id:
            return getattr(table, "revision", None), True
    return None, False


def _live_cells(read_client, app_token, table_id, context=None):
    """``{record_id: {field_name: rendered value}}`` — the tier-2 precondition read.

    The same two calls L1 makes, through the same assembler, so the comparison is against L1's
    own rendering rather than a second opinion about what a Base cell looks like.
    """
    kwargs = {"context": context} if context is not None else {}
    read = assemble_table(
        table_id=table_id, name="",
        fields=read_client.list_fields(app_token, table_id),
        records=read_client.search_records(app_token, table_id),
        **kwargs)
    names = [spec.field_name for spec in read.fields]
    return {row.record_id: dict(zip(names, row.cells)) for row in read.rows}


def _where(call, table: TablePlan) -> str:
    return (f"{call.kind} on table {table.table_id} ({table.name}) carrying "
            f"{len(call.record_ids)} record(s): {', '.join(call.record_ids)}")


def _stale_refusal(table: TablePlan, live) -> Refusal:
    return Refusal(
        reason=Refusal.STALE_BASE,
        detail=(
            f"table {table.table_id} ({table.name}) moved under this plan: `table.revision` "
            f"was {table.revision!r} when the plan was built and reads {live!r} now, so "
            f"something else wrote to this table in between. ZERO writes were issued for this "
            f"table's entries; entries in OTHER tables are judged against their own anchors, "
            f"because `table.revision` is per-table isolated. Re-read the table, re-plan, and "
            f"re-apply. This compare is CLIENT-SIDE: there is no If-Match on this API, so it "
            f"closes the window between the plan and the write, not the last microsecond "
            f"between the compare and the write."))


def _precondition_refusal(entry, live_cells) -> Optional[Refusal]:
    """Tier 2 for one entry, or ``None`` when nothing drifted."""
    live = live_cells.get(entry.record_id)
    if live is None:
        return Refusal(
            reason=Refusal.PRECONDITION_MISMATCH,
            detail=(f"record {entry.record_id} is no longer in table {entry.table_id}: it was "
                    "read at plan time and is not there now, so the plan's `before` cannot be "
                    "verified and nothing is written for this entry. A Base record delete is "
                    "permanent — there is no trash for a record — so this is a re-plan, not a "
                    "retry."))
    drifted = {name: (before, live.get(name, ""))
               for name, before in (entry.before or {}).items()
               if live.get(name, "") != before}
    if not drifted:
        return None
    moved = "; ".join(f"{name}: plan saw {before!r}, the table now holds {now!r}"
                      for name, (before, now) in drifted.items())
    return Refusal(
        reason=Refusal.PRECONDITION_MISMATCH,
        detail=(f"record {entry.record_id} drifted under this plan (tier 2, the value "
                f"precondition): {moved}. NOTHING was written for this entry; the rest of the "
                f"batch is still processed. This is the tier that covers a table whose anchor "
                f"cannot arm tier 1."))


def _not_attempted(entry, *, where: str, why: str) -> ApplyLogEntry:
    return ApplyLogEntry.not_attempted(entry, refusal=Refusal(
        reason=Refusal.NOT_ATTEMPTED,
        detail=(f"the batch halted at {where} ({why}), so this entry was never attempted and "
                "NOTHING was written for it. Re-run dry_run before applying the remainder: "
                "the Base may have moved.")))


def _issue(watch, call, table, app_token, entries):
    """Make ONE batch call. The only place this module touches the write client."""
    if call.kind == "batch_create":
        return watch.batch_create_records(
            app_token, table.table_id, [entry.fields or {} for entry in entries])
    if call.kind == "batch_update":
        return watch.batch_update_records(
            app_token, table.table_id,
            [(entry.record_id, entry.fields or {}) for entry in entries])
    return watch.batch_delete_records(
        app_token, table.table_id, [entry.record_id for entry in entries])


def _created_ids(reply):
    ids = []
    for record in (reply or ()):
        ids.append(getattr(record, "record_id", None))
    return ids


def apply(plan, *, client, read_client, context=None,
          allow_partial: bool = False) -> ApplyLog:
    """Apply a :class:`~larkdocio.base.plan.Plan`, returning its :class:`ApplyLog`.

    ``client`` is a :class:`~larkdocio.base.write_client.BaseWriteClient` (duck-typed) and
    ``read_client`` a :class:`~larkdocio.base.client.BaseReadClient` (duck-typed): both are
    required, because the compare-and-swap is **client-side** and a guard that cannot read
    cannot compare.

    The log is one entry per plan entry, in plan order, on every run.

    **An entry that did not land RAISES** :class:`~larkdocio.errors.LarkApplyRefusedError`
    unless ``allow_partial=True`` — one spelling on every plan-gated apply this library
    ships. ``stale``, ``dropped``, ``refused``, ``failed`` and
    ``not-attempted`` are all "did not land", so a caller who discarded the log can no longer
    read a batch that wrote nothing as a success. The finished log travels on the exception
    (``err.log`` / ``err.applied`` / ``err.refusals``); nothing is rolled back and which
    entries land is unchanged.
    """
    if not isinstance(plan, Plan):
        raise TypeError(
            "apply() takes a Plan produced by larkdocio.base.apply.dry_run(...) and nothing "
            f"else — a snapshot, a dict or a look-alike is not a plan; got "
            f"{type(plan).__name__}.")
    if client is None or read_client is None:
        raise TypeError(
            "apply() needs BOTH a write client and a read client: `STALE_BASE` is a "
            "CLIENT-SIDE read-compare-write (this API has no If-Match), so the engine must "
            "read `table.revision` before it writes.")

    results = [None] * len(plan.entries)
    per_table = {}
    for position, entry in enumerate(plan.entries):
        per_table.setdefault(entry.table_id, []).append((position, entry))

    halt = None
    table_halts = {}

    for table in plan.tables:
        items = per_table.get(table.table_id, [])
        if halt is not None:
            for position, entry in items:
                if results[position] is None:
                    results[position] = _not_attempted(
                        entry, where=halt["where"], why=halt["reason"])
            continue

        # ---- plan-time refusals: decided before any call, logged as themselves ---- #
        pending = []
        for position, entry in items:
            if entry.refusal is not None:
                results[position] = ApplyLogEntry.refused(entry, refusal=entry.refusal)
            else:
                pending.append((position, entry))
        if not pending:
            continue

        # ---- tier 1: the client-side compare-and-swap ----------------------------- #
        try:
            live, found = _live_anchor(read_client, plan.app_token, table.table_id)
        except Exception as exc:            # noqa: BLE001 — the boundary's whole job
            disposition = classify_apply_exception(exc, wrote=False)
            where = f"the anchor read for table {table.table_id}"
            refusal = disposition_refusal(disposition, exc, where=where)
            for position, entry in pending:
                results[position] = ApplyLogEntry.refused(entry, refusal=refusal)
            if disposition.halts:
                halt = {"index": pending[0][0], "reason": refusal.reason,
                        "detail": refusal.detail, "where": where}
            continue

        if not found:
            where = f"the anchor read for table {table.table_id}"
            refusal = Refusal(
                reason=Refusal.API_ERROR,
                detail=(f"table {table.table_id} is no longer listed in Base "
                        f"{plan.app_token}: it was there when the plan was built and is not "
                        "now, so nothing was written for it. An answer about the TABLE is "
                        "systemic — every remaining call would meet the same condition — so "
                        "the batch HALTED and the remaining entries are logged "
                        "not-attempted."))
            for position, entry in pending:
                results[position] = ApplyLogEntry.refused(entry, refusal=refusal)
            halt = {"index": pending[0][0], "reason": refusal.reason,
                    "detail": refusal.detail, "where": where}
            continue

        if table.revision_guard == "active" and live != table.revision:
            refusal = _stale_refusal(table, live)
            for position, entry in pending:
                results[position] = ApplyLogEntry.stale(entry, refusal=refusal)
            table_halts[table.table_id] = {
                "index": pending[0][0], "reason": refusal.reason, "detail": refusal.detail,
                "not_attempted": 0, "stale": len(pending)}
            continue

        # ---- tier 2: the value precondition -------------------------------------- #
        needs_precondition = [item for item in pending if item[1].before is not None]
        if needs_precondition:
            try:
                live_cells = _live_cells(read_client, plan.app_token, table.table_id, context)
            except Exception as exc:        # noqa: BLE001 — the boundary again
                disposition = classify_apply_exception(exc, wrote=False)
                where = f"the value-precondition read for table {table.table_id}"
                refusal = disposition_refusal(disposition, exc, where=where)
                for position, entry in pending:
                    results[position] = ApplyLogEntry.refused(entry, refusal=refusal)
                if disposition.halts:
                    halt = {"index": pending[0][0], "reason": refusal.reason,
                            "detail": refusal.detail, "where": where}
                continue
            for position, entry in needs_precondition:
                refusal = _precondition_refusal(entry, live_cells)
                if refusal is not None:
                    results[position] = ApplyLogEntry.refused(entry, refusal=refusal)

        # ---- the calls ----------------------------------------------------------- #
        anchor = live
        for call in table.calls:
            riding = [(position, entry) for position, entry in pending
                      if entry.call_index == call.index and results[position] is None]
            if not riding:
                continue
            entries = [entry for _position, entry in riding]
            watch = WriteWatch(client)
            where = _where(call, table)
            try:
                reply = _issue(watch, call, table, plan.app_token, entries)
                post, _found = _live_anchor(read_client, plan.app_token, table.table_id)
            except Exception as exc:        # noqa: BLE001 — no exception escapes apply()
                disposition = classify_apply_exception(exc, wrote=watch.wrote)
                refusal = disposition_refusal(disposition, exc, where=where,
                                              wrote_seams=watch.completed)
                for position, entry in riding:
                    if disposition.outcome == "applied-unverified":
                        results[position] = ApplyLogEntry.applied_unverified(
                            entry, refusal=refusal)
                    elif disposition.outcome == "failed":
                        results[position] = ApplyLogEntry.failed(entry, refusal=refusal)
                    else:
                        results[position] = ApplyLogEntry.refused(entry, refusal=refusal)
                if disposition.halts:
                    halt = {"index": riding[0][0], "reason": refusal.reason,
                            "detail": refusal.detail, "where": where}
                    break
                continue

            if post is None:
                # The write returned and the anchor cannot be read, so the oracle cannot run:
                # applied, with an incomplete verification record. Never called a refusal.
                refusal = Refusal(
                    reason=Refusal.UNVERIFIED_WRITE,
                    detail=(f"{where} RETURNED — the change IS on the Base — but the "
                            "post-write `table.revision` read back as None, so the "
                            "write-effect oracle could not run and this call is recorded "
                            "applied-unverified. The batch HALTED: the compare-and-swap "
                            "anchor is now unknown."))
                for position, entry in riding:
                    results[position] = ApplyLogEntry.applied_unverified(entry,
                                                                         refusal=refusal)
                halt = {"index": riding[0][0], "reason": refusal.reason,
                        "detail": refusal.detail, "where": where}
                break

            if post == anchor:
                # THE WRITE-EFFECT ORACLE. `code:0` and the anchor did not move: the server
                # registered no operation, so this did NOT happen (`p1-q2-02`).
                refusal = Refusal(
                    reason=Refusal.WRITE_NOT_OBSERVED,
                    detail=(f"{where} answered code:0 and `table.revision` did NOT move "
                            f"({anchor!r} → {post!r}), so the server registered no operation "
                            "for it: the write was accepted and discarded. It is reported as "
                            "dropped rather than applied — a code:0 is not evidence a write "
                            "happened. The engine does NOT retry: it reports what it "
                            "observed, and re-sending would be a guess about why the value "
                            "was discarded."))
                for position, entry in riding:
                    results[position] = ApplyLogEntry.dropped(entry, refusal=refusal,
                                                              revision=post)
                anchor = post
                continue

            created = _created_ids(reply) if call.kind == "batch_create" else []
            for offset, (position, entry) in enumerate(riding):
                results[position] = ApplyLogEntry.applied(
                    entry, revision=post,
                    created_record_id=(created[offset]
                                       if offset < len(created) else None))
            anchor = post

        if halt is not None:
            for position, entry in items:
                if results[position] is None:
                    results[position] = _not_attempted(
                        entry, where=halt["where"], why=halt["reason"])

    # Anything still unlogged is an entry a halt in an earlier table never reached.
    for position, entry in enumerate(plan.entries):
        if results[position] is None:
            results[position] = _not_attempted(
                entry,
                where=(halt or {}).get("where", "an earlier entry"),
                why=(halt or {}).get("reason", Refusal.NOT_ATTEMPTED))

    if halt is not None:
        halt["not_attempted"] = sum(1 for entry in results
                                    if entry.outcome == "not-attempted")

    # The one seam every log entry passes through: stamp the plan-time tier-1 status, so an
    # applied write on a revision-0 table is never indistinguishable from a fully guarded one.
    stamped = tuple(record.with_revision_guard(plan.entries[position].revision_guard)
                    for position, record in enumerate(results))
    log = ApplyLog(entries=stamped, halt=halt, table_halts=table_halts)
    return gate_refusals(log, allow_partial=allow_partial,
                         surface="larkdocio.base.apply.apply")


__all__ = ["DECLARED_SAFETY_CONTRACT", "apply", "dry_run"]
