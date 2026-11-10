"""larkdocio.base.plan — the Base write PLAN and its apply-log (LD-259).

**The value objects the gate is made of**, in the shipped shape of both existing engines
(:mod:`larkdocio.sheets.plan`, :mod:`larkdocio.write.preview`): a typed :class:`Refusal`, a
:class:`PlanEntry` per record the plan acts on, a **non-forgeable** :class:`Plan` produced only
by :func:`larkdocio.base.apply.dry_run`, and an :class:`ApplyLog` that is one entry per plan
entry, in plan order, on every run.

**There is NO server-side compare-and-swap on a Base, and this module says so in the shipped
text rather than implying otherwise.** A record ``PUT`` carrying bogus ``revision`` /
``last_modified_time`` body keys answered ``code:0`` **and applied the write** (opener
``05-08``, ``precondition_key_probe``): the API silently ignores preconditions it does not
know, which is R12 wearing its most dangerous costume. So the guard here is a **client-side
read-compare-write** on ``table.revision`` — the engine reads the anchor, compares it, then
writes — and :data:`NO_SERVER_SIDE_CAS` is the one authoring of what that does and does not
buy. Sending a precondition key would be a lie that reads like safety, and no code path here
sends one.

**The anchor is per TABLE, so the plan is per table.** ``table.revision`` is isolated per
table (``05-08``: the untouched second table stayed at ``0`` while the edited one advanced
``18 → 19``, and the *app* revision did not move at all), which is what makes a halt scoped to
one table coherent — the other tables' entries are still judged against their own anchors.

**Tier 1 is never silently off.** ``table.revision`` reads ``0`` on a freshly created Base and
the standing Scratch Base read ``0`` before moving to ``14`` and then ``30``, so **revision-0
is a STATE, not a property of a particular Base**. The classification is the shared core's
(:mod:`larkdocio.common.staleness`, imported and **unchanged**): any non-positive anchor is
``unavailable``. The marker is derived **inside** :class:`Plan` construction, so no code path
can produce a plan that lacks it, and every entry states whether the **tier-2 value
precondition** covers it.

**One batch moves the anchor once.** :data:`BATCH_BUMPS_ANCHOR_ONCE` is the contract, read off
``p0-2-06``: a plan's snapshot→apply compare is a single integer compare **regardless of batch
size**, and an expectation of "+N per row" would be wrong.
"""
import json
from dataclasses import dataclass, field as dataclass_field, replace
from types import MappingProxyType
from typing import Dict, Optional, Tuple

from larkdocio.common.staleness import (
    REVISION_GUARD_ACTIVE,
    REVISION_GUARD_UNAVAILABLE,
    revision_guard_status,
)

# The private construction token. Only this module holds it, so a :class:`Plan` can be built
# solely via :func:`larkdocio.base.apply.dry_run` — the docx ``write.preview._PLAN_TOKEN`` /
# sheets ``plan._PLAN_TOKEN`` hard gate, third surface.
_PLAN_TOKEN = object()


# --------------------------------------------------------------------------- #
# The two statements this surface must not get wrong, authored ONCE            #
# --------------------------------------------------------------------------- #

#: **What ``STALE_BASE`` is, and what it is not.** Quoted verbatim by the plan's own JSON and
#: by ``BASE.md`` (in the source repository), so the three cannot drift — and worded so that no
#: reader can take it for an atomicity claim, because the engine cannot deliver one.
NO_SERVER_SIDE_CAS = (
    "There is NO server-side compare-and-swap on a Base: a record PUT carrying bogus "
    "`revision` and `last_modified_time` body keys answered `code:0` AND applied the write "
    "(opener capture `05-08`), so the API silently ignores preconditions it does not "
    "recognise. There is no `If-Match` and no conditional write of any kind. `STALE_BASE` is "
    "therefore a CLIENT-SIDE read-compare-write: the engine re-reads `table.revision` "
    "immediately before the batch and refuses, with zero writes, if it moved since the plan "
    "was built. That closes the window between the plan and the write; it does NOT close the "
    "last microsecond between the compare and the write itself, and this library will not "
    "imply that it does."
)

#: **The batch contract**, read off ``p0-2-06``. The reason a plan compares one integer.
BATCH_BUMPS_ANCHOR_ONCE = (
    "`table.revision` is a per-table OP counter, not a row counter: a field create is +1, a "
    "3-record `batch_update` is +1 (not +3), and a field delete is +1 (capture `p0-2-06`). So "
    "a plan's snapshot-to-apply compare is a single integer compare regardless of batch size, "
    "and one batch call is expected to advance the anchor by exactly +1 per batch, not per "
    "row."
)


# --------------------------------------------------------------------------- #
# Tier 2 — the value precondition                                              #
# --------------------------------------------------------------------------- #

#: Tier 2 covers this entry: the cells it writes (or the record it deletes) are re-read
#: immediately before the batch and any drift refuses :data:`Refusal.PRECONDITION_MISMATCH`.
VALUE_PRECONDITION_ENFORCED = "enforced"
#: Tier 2 does **not** exist for this entry — a created record has no ``before`` to compare.
VALUE_PRECONDITION_NONE = "none"

#: The tier-2 blurb every plan carries. The per-entry truth is each entry's own
#: ``value_precondition``.
_TIER2_SUMMARY = (
    "enforced on every entry that has a plan-time `before` — an edited record's written cells "
    "and a deleted record's existence are re-read immediately before the batch (one records "
    "read per table, the same read L1 makes) and any drift refuses precondition-mismatch for "
    "that entry alone; a CREATED record has no `before`, so it has no second tier"
)


def revision_guard_semantics(revision) -> dict:
    """The complete, JSON-serializable staleness disclosure for one table's plan-time anchor —
    ``{"status", "detail", "tiers"}``.

    ONE source for the marker, the WHY and the two-tier summary, so the plan, the apply-log and
    ``BASE.md`` (in the source repository) cannot drift apart. Both statuses carry a non-empty
    ``detail``: a marker with no WHY is a riddle.
    """
    status = revision_guard_status(revision)
    if status == REVISION_GUARD_UNAVAILABLE:
        detail = (
            f"tier 1 (the client-side `table.revision` compare-and-swap) is UNAVAILABLE: the "
            f"plan-time anchor read back as {revision!r}. A freshly created Base reads 0 and "
            f"the standing Scratch Base read 0 before moving to 14 and then 30 — revision-0 is "
            f"a STATE, not a property of a particular Base — and comparing 0 == 0 before a "
            f"write cannot observe an advance, so it would be silently inert. tier 2 (the "
            f"value precondition) STILL enforces: {_TIER2_SUMMARY}. Entries whose "
            f"value_precondition is 'none' have NO second tier on this table. The guard "
            f"self-heals: the next plan built on a positive anchor marks itself 'active'."
        )
    else:
        detail = (
            f"tier 1 (the client-side `table.revision` compare-and-swap) is ACTIVE on the "
            f"plan-time anchor revision={revision!r}: apply re-reads `table.revision` "
            f"immediately before this table's batch and refuses stale-base — with ZERO writes "
            f"for this table — if it advanced. tier 2 (the value precondition) also enforces: "
            f"{_TIER2_SUMMARY}."
        )
    return {
        "status": status,
        "detail": detail,
        "tiers": {
            "tier1_revision_compare_and_swap": status,
            "tier2_value_precondition": _TIER2_SUMMARY,
        },
    }


# --------------------------------------------------------------------------- #
# Refusal — one typed reason + a mandatory WHY                                 #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Refusal:
    """Why one entry was refused — a typed reason plus an inspectable, non-empty detail."""

    reason: str
    detail: Optional[str] = None

    #: The client-side compare-and-swap tripped: ``table.revision`` moved between the plan and
    #: the write. Refuses **that table's** entries with zero writes; other tables are judged
    #: against their own anchors (D4′).
    STALE_BASE = "stale-base"
    #: Tier 2: a cell this entry writes (or the record it deletes) drifted from the plan's
    #: capture. Entry-scoped — the rest of the batch is still processed.
    PRECONDITION_MISMATCH = "precondition-mismatch"
    #: A plan-time refusal: the edit names a computed / opaque field. Decided by the diff, with
    #: the reason quoted from :mod:`larkdocio.base.write_vocabulary`; costs zero API calls.
    NON_WRITABLE_FIELD = "non-writable-field"
    #: A plan-time refusal: the value is not the field's write shape (the encoder said so
    #: before anything was sent).
    INVALID_REQUEST = "invalid-request"
    #: Lark answered about this call — an entry-scoped API error; the batch continues.
    API_ERROR = "api-error"
    #: The app lacks a required SCOPE. Systemic: the batch HALTS (LD-206, inherited verbatim).
    PERMISSION_DENIED = "permission-denied"
    #: Lark's rate limit survived the transport's own pacing. Systemic.
    RATE_LIMITED = "rate-limited"
    #: The call failed BELOW Lark, so whether it landed is INDETERMINATE. Systemic.
    TRANSPORT_FAILURE = "transport-failure"
    #: Something un-modelled raised inside the per-entry step. Systemic, indeterminate.
    UNEXPECTED_ERROR = "unexpected-error"
    #: The write returned but a post-write step failed: the change IS on the Base and its
    #: verification record is not. Systemic — the anchor is now unknown.
    UNVERIFIED_WRITE = "unverified-write"
    #: **The write-effect oracle.** The call answered ``code:0`` and ``table.revision`` did NOT
    #: move, so the server registered no operation for it (the Stage discard, ``p1-q2-02``:
    #: ``code:0``, ``25 → 25``, against a positive control that moved ``1 → 2``). Reported,
    #: never retried, and never logged as applied.
    WRITE_NOT_OBSERVED = "write-not-observed"
    #: **A destructive schema op whose loss could not be enumerated.** The cross-table scan a
    #: delete's preview needs could not be completed — a table list that cannot be proven read
    #: to the end, a column read that errored, a table the credential cannot see — so the op
    #: refuses with ZERO writes. The Sheets structural rung's invariant, widened from one sheet
    #: to the whole app; the sentence is
    #: :data:`larkdocio.base.loss_preview.LOSS_MUST_BE_ENUMERABLE`.
    LOSS_NOT_ENUMERABLE = "loss-not-enumerable"
    #: **The attachment out-of-band leg failed** — an upload, a download or a hash comparison
    #: on the drive media family, not on the bitable API. Its own reason rather than
    #: ``API_ERROR``, because a media endpoint is a different service answering a different
    #: question: folding it in would tell a consumer that Lark judged their *record* when it
    #: judged their *file*. Entry-scoped — this entry's file says nothing about the next
    #: entry's. The sentence lives with the leg
    #: (:data:`larkdocio.base.media.MEDIA_REFUSAL_REASON`).
    MEDIA_LEG_FAILURE = "media-leg-failure"
    #: The batch (or this table's leg of it) halted earlier; this entry was never attempted.
    NOT_ATTEMPTED = "not-attempted"

    def to_dict(self) -> dict:
        return {"reason": self.reason, "detail": self.detail}

    @classmethod
    def from_dict(cls, d: dict) -> "Refusal":
        return cls(reason=d["reason"], detail=d.get("detail"))


# --------------------------------------------------------------------------- #
# RefusalReason — the vocabulary, ON THE EXPORT SURFACE                         #
#                                                                              #
# LD-457, the sibling of the sheets export: `reason` is a plain string, so the  #
# only spelling a consumer's `==` can match is the wire value, and neither the  #
# reason vocabulary nor `Refusal` itself was reachable from `larkdocio.base`.   #
# `Refusal`'s attributes stay the authoring site; this is their exported        #
# projection, enumerated against the class by a guard in the source repository, not in  #
# the wheel: `tests/test_refusal_reason_vocabulary.py`.                         #
# --------------------------------------------------------------------------- #


class RefusalReason:
    """The Base refusal-reason vocabulary — **import it, never type it**.

    Every value is the exact string :attr:`Refusal.reason` carries, so a guard written
    against it fires::

        from larkdocio.base import RefusalReason

        if entry.refusal is not None and entry.refusal.reason == RefusalReason.STALE_BASE:
            ...   # re-read, re-plan, re-apply — the refusal is recoverable

    Each reason's meaning and blast radius (entry-scoped or halting) is documented on
    :class:`Refusal`, whose attributes these mirror one for one. Plain strings, deliberately
    not an enum: a serialized plan already carries the raw value, and an existing comparison
    against it keeps working unchanged.
    """

    __slots__ = ()

    #: The client-side compare-and-swap tripped — this table moved between plan and write.
    STALE_BASE = Refusal.STALE_BASE
    PRECONDITION_MISMATCH = Refusal.PRECONDITION_MISMATCH
    NON_WRITABLE_FIELD = Refusal.NON_WRITABLE_FIELD
    INVALID_REQUEST = Refusal.INVALID_REQUEST
    API_ERROR = Refusal.API_ERROR
    PERMISSION_DENIED = Refusal.PERMISSION_DENIED
    RATE_LIMITED = Refusal.RATE_LIMITED
    TRANSPORT_FAILURE = Refusal.TRANSPORT_FAILURE
    UNEXPECTED_ERROR = Refusal.UNEXPECTED_ERROR
    UNVERIFIED_WRITE = Refusal.UNVERIFIED_WRITE
    WRITE_NOT_OBSERVED = Refusal.WRITE_NOT_OBSERVED
    LOSS_NOT_ENUMERABLE = Refusal.LOSS_NOT_ENUMERABLE
    MEDIA_LEG_FAILURE = Refusal.MEDIA_LEG_FAILURE
    NOT_ATTEMPTED = Refusal.NOT_ATTEMPTED


#: ``{NAME: wire value}`` for every Base refusal reason — the enumerable form, for a consumer
#: that logs, groups or routes on the reason rather than comparing one.
REFUSAL_REASONS = MappingProxyType({
    name: value
    for name, value in vars(RefusalReason).items()
    if name.isupper() and isinstance(value, str)
})


# --------------------------------------------------------------------------- #
# The plan                                                                     #
# --------------------------------------------------------------------------- #

#: The three record ops a diff compiles to, in the order a plan runs them: creates first (so a
#: caller reading the log meets the new ids before anything references them), then updates,
#: then deletes.
CALL_KINDS: Tuple[str, ...] = ("batch_create", "batch_update", "batch_delete")


@dataclass(frozen=True)
class PlannedCall:
    """ONE API call, and exactly which records ride in it.

    The failure granularity a consumer must reason about is the CALL, not the record: Lark
    judges a ``batch_update`` as a whole, so an entry-scoped refusal refuses every entry in
    that call. Making the grouping visible in the plan is what lets a consumer see that before
    approving it.
    """

    index: int
    table_id: str
    kind: str
    record_ids: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {"index": self.index, "table_id": self.table_id, "kind": self.kind,
                "record_ids": list(self.record_ids)}


@dataclass(frozen=True)
class PlanEntry:
    """One record the plan acts on — or one it refuses, decided before any call.

    ``record_id`` is a real Lark id for an edit / delete and the model's **local** id for a
    create (``new:1``), which is the handle the apply-log reports the server's assigned id
    against.
    """

    table_id: str
    table_name: str
    record_id: str
    op: str
    fields: Optional[dict] = None
    before: Optional[dict] = None
    call_index: Optional[int] = None
    call_kind: Optional[str] = None
    refusal: Optional[Refusal] = None
    revision_guard: Optional[str] = None
    value_precondition: str = VALUE_PRECONDITION_NONE
    cross_table: Tuple[dict, ...] = ()

    @property
    def is_resolved(self) -> bool:
        """True when this entry will be attempted — i.e. it was not refused at plan time."""
        return self.refusal is None

    def with_revision_guard(self, status: str) -> "PlanEntry":
        return replace(self, revision_guard=status)

    def to_dict(self) -> dict:
        return {
            "table_id": self.table_id,
            "table_name": self.table_name,
            "record_id": self.record_id,
            "op": self.op,
            "fields": self.fields,
            "before": self.before,
            "call_index": self.call_index,
            "call_kind": self.call_kind,
            "refusal": self.refusal.to_dict() if self.refusal is not None else None,
            "revision_guard": self.revision_guard,
            "value_precondition": self.value_precondition,
            "cross_table": [dict(effect) for effect in self.cross_table],
        }


@dataclass(frozen=True)
class TablePlan:
    """One table's leg of a plan, carrying **its own** anchor.

    The guard status is a **derived property**, never a stored slot: there is no way to hand a
    table plan a marker that disagrees with its own anchor.
    """

    table_id: str
    name: str
    revision: Optional[int]
    entries: Tuple[PlanEntry, ...] = ()
    calls: Tuple[PlannedCall, ...] = ()
    unchanged: int = 0

    @property
    def revision_guard(self) -> str:
        return revision_guard_status(self.revision)

    @property
    def revision_guard_detail(self) -> str:
        return revision_guard_semantics(self.revision)["detail"]

    @property
    def revision_guard_tiers(self) -> dict:
        return revision_guard_semantics(self.revision)["tiers"]

    @property
    def expected_anchor_advance(self) -> int:
        """How far this table's anchor should move if every planned call lands: **+1 per
        call**, never per row (:data:`BATCH_BUMPS_ANCHOR_ONCE`)."""
        return len(self.calls)

    def to_dict(self) -> dict:
        semantics = revision_guard_semantics(self.revision)
        return {
            "table_id": self.table_id,
            "name": self.name,
            "revision": self.revision,
            "revision_guard": semantics["status"],
            "revision_guard_detail": semantics["detail"],
            "revision_guard_tiers": semantics["tiers"],
            "expected_anchor_advance": self.expected_anchor_advance,
            "unchanged": self.unchanged,
            "calls": [call.to_dict() for call in self.calls],
            "entries": [entry.to_dict() for entry in self.entries],
        }


class Plan:
    """An ordered, previewer-backed batch of :class:`PlanEntry`, grouped per table.

    The **only** input :func:`larkdocio.base.apply.apply` accepts. It cannot be hand-forged:
    the constructor is guarded by a module-private token, so the sole way to obtain one is
    :func:`larkdocio.base.apply.dry_run`. There is intentionally **no** ``from_dict`` — a plan
    is trusted *because* it came from the previewer.

    Every entry is stamped, **here**, with its own table's tier-1 status: doing it at the one
    seam every plan must pass through is what makes "no plan lacks the marker" structural
    rather than a convention each compiler leg has to remember.
    """

    __slots__ = ("_app_token", "_tables")

    def __init__(self, entries=None, *, app_token=None, tables=(), _token: object = None):
        if _token is not _PLAN_TOKEN:
            raise TypeError(
                "Plan objects are produced only by larkdocio.base.apply.dry_run(...); "
                "construct a plan via the previewer, not directly."
            )
        stamped = []
        for table in tables:
            guard = revision_guard_status(table.revision)
            stamped.append(replace(
                table,
                entries=tuple(entry.with_revision_guard(guard) for entry in table.entries)))
        object.__setattr__(self, "_app_token", app_token)
        object.__setattr__(self, "_tables", tuple(stamped))

    # ---- reading the plan -------------------------------------------------- #

    @property
    def app_token(self):
        return self._app_token

    @property
    def tables(self) -> Tuple[TablePlan, ...]:
        return self._tables

    def table(self, table_id: str) -> TablePlan:
        for table in self._tables:
            if table.table_id == table_id:
                return table
        raise KeyError(table_id)

    @property
    def entries(self) -> Tuple[PlanEntry, ...]:
        return tuple(entry for table in self._tables for entry in table.entries)

    @property
    def calls(self) -> Tuple[PlannedCall, ...]:
        return tuple(call for table in self._tables for call in table.calls)

    @property
    def api_call_count(self) -> int:
        """How many write calls this plan will make. The read calls the guard spends are
        disclosed separately by :func:`larkdocio.base.apply.apply`'s own log."""
        return len(self.calls)

    @property
    def resolved(self) -> Tuple[PlanEntry, ...]:
        return tuple(entry for entry in self.entries if entry.is_resolved)

    @property
    def refusals(self) -> Tuple[PlanEntry, ...]:
        return tuple(entry for entry in self.entries if not entry.is_resolved)

    def expected_anchor_advance(self, table_id: str) -> int:
        return self.table(table_id).expected_anchor_advance

    def __iter__(self):
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def __repr__(self) -> str:
        guards = ",".join(f"{t.table_id}:{t.revision_guard}" for t in self._tables)
        return (f"Plan(entries={len(self.entries)}, refused={len(self.refusals)}, "
                f"calls={self.api_call_count}, revision_guard=[{guards}])")

    def to_dict(self) -> dict:
        return {
            "app_token": self._app_token,
            "api_call_count": self.api_call_count,
            # The consumer-visible staleness disclosure. Always present, and it states the
            # LIMIT of the guarantee as plainly as the guarantee.
            "staleness": {
                "no_server_side_compare_and_swap": NO_SERVER_SIDE_CAS,
                "batch_contract": BATCH_BUMPS_ANCHOR_ONCE,
                "per_table": {t.table_id: t.revision_guard for t in self._tables},
            },
            "calls": [call.to_dict() for call in self.calls],
            "tables": [table.to_dict() for table in self._tables],
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), **kwargs)


# --------------------------------------------------------------------------- #
# The apply-log                                                                #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ApplyLogEntry:
    """The record of ONE processed plan entry — its **disposition**.

    ========================= ============ ==================================================
    ``outcome``               landed?      meaning
    ========================= ============ ==================================================
    ``applied``               **yes**      the call went through and the anchor moved.
    ``applied-unverified``    **yes**      the write returned, a post-write step failed.
    ``dropped``               **no**       the call answered ``code:0`` and the anchor did
                                           NOT move: the server registered no operation
                                           (``p1-q2-02``). Never reported as applied.
    ``stale``                 no           the client-side compare-and-swap tripped for this
                                           table (:data:`Refusal.STALE_BASE`) — zero writes.
    ``refused``               no           a typed refusal: decided at plan time, by tier 2,
                                           or an entry-scoped API error at apply time.
    ``failed``                **unknown**  the attempt leaves whether it landed INDETERMINATE.
    ``not-attempted``         no           the batch (or this table's leg) halted earlier.
    ========================= ============ ==================================================
    """

    outcome: str
    table_id: Optional[str] = None
    record_id: Optional[str] = None
    op: Optional[str] = None
    fields: Optional[dict] = None
    before: Optional[dict] = None
    revision: Optional[int] = None
    refusal: Optional[Refusal] = None
    revision_guard: Optional[str] = None
    call_index: Optional[int] = None
    #: The server's assigned ``record_id`` for a created record (``None`` for every other op,
    #: and for a create whose call did not land).
    created_record_id: Optional[str] = None

    @classmethod
    def applied(cls, entry: PlanEntry, *, revision=None, created_record_id=None):
        return cls(outcome="applied", table_id=entry.table_id, record_id=entry.record_id,
                   op=entry.op, fields=entry.fields, before=entry.before, revision=revision,
                   call_index=entry.call_index, created_record_id=created_record_id)

    @classmethod
    def dropped(cls, entry: PlanEntry, *, refusal: Refusal, revision=None):
        """``code:0`` with the anchor unmoved — the write-effect oracle's verdict."""
        return cls(outcome="dropped", table_id=entry.table_id, record_id=entry.record_id,
                   op=entry.op, fields=entry.fields, before=entry.before, revision=revision,
                   refusal=refusal, call_index=entry.call_index)

    @classmethod
    def stale(cls, entry: PlanEntry, *, refusal: Refusal):
        return cls(outcome="stale", table_id=entry.table_id, record_id=entry.record_id,
                   op=entry.op, fields=entry.fields, before=entry.before, refusal=refusal,
                   call_index=entry.call_index)

    @classmethod
    def refused(cls, entry: PlanEntry, *, refusal: Refusal):
        return cls(outcome="refused", table_id=entry.table_id, record_id=entry.record_id,
                   op=entry.op, fields=entry.fields, before=entry.before, refusal=refusal,
                   call_index=entry.call_index)

    @classmethod
    def failed(cls, entry: PlanEntry, *, refusal: Refusal):
        return cls(outcome="failed", table_id=entry.table_id, record_id=entry.record_id,
                   op=entry.op, fields=entry.fields, before=entry.before, refusal=refusal,
                   call_index=entry.call_index)

    @classmethod
    def applied_unverified(cls, entry: PlanEntry, *, refusal: Refusal):
        return cls(outcome="applied-unverified", table_id=entry.table_id,
                   record_id=entry.record_id, op=entry.op, fields=entry.fields,
                   before=entry.before, refusal=refusal, call_index=entry.call_index)

    @classmethod
    def not_attempted(cls, entry: PlanEntry, *, refusal: Refusal):
        return cls(outcome="not-attempted", table_id=entry.table_id,
                   record_id=entry.record_id, op=entry.op, fields=entry.fields,
                   before=entry.before, refusal=refusal, call_index=entry.call_index)

    @property
    def is_applied(self) -> bool:
        """True when the change **landed** — ``applied`` or ``applied-unverified``.

        ``dropped`` is deliberately NOT here: the anchor did not move, so the server
        registered no operation.
        """
        return self.outcome in ("applied", "applied-unverified")

    @property
    def is_verified(self) -> bool:
        return self.outcome == "applied"

    @property
    def is_indeterminate(self) -> bool:
        return self.outcome == "failed"

    def with_revision_guard(self, status: str) -> "ApplyLogEntry":
        return replace(self, revision_guard=status)

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "table_id": self.table_id,
            "record_id": self.record_id,
            "op": self.op,
            "fields": self.fields,
            "before": self.before,
            "revision": self.revision,
            "refusal": self.refusal.to_dict() if self.refusal is not None else None,
            "revision_guard": self.revision_guard,
            "call_index": self.call_index,
            "created_record_id": self.created_record_id,
        }


@dataclass(frozen=True)
class ApplyLog:
    """The 1:1, in-order record of an :func:`larkdocio.base.apply.apply` run.

    One entry per plan entry, in plan order, on every run — including one that hit an
    exception, halted, or both. :attr:`halt` is the batch-level disclosure and
    :attr:`table_halts` the **per-table** one, because a ``stale-base`` refusal stops that
    table's entries and leaves the others to be judged against their own anchors (D4′).

    :attr:`platform_anomaly` is the third, **plan-wide** disclosure (LD-337): set only when every
    attempted entry refused with the same code the classification table does not know, on table
    ids this run's read client itself listed. It defaults to ``None`` and is **absent from**
    :meth:`to_dict` rather than serialized as null — this class is **shared with the record
    engine**, which never sets it, and a shared log's serialized shape must not move for a slot
    one of its engines does not use.
    """

    entries: Tuple[ApplyLogEntry, ...] = ()
    halt: Optional[dict] = None
    table_halts: Dict[str, dict] = dataclass_field(default_factory=dict)
    platform_anomaly: Optional[dict] = None

    def __iter__(self):
        """Iterate the entries (LD-458) — ``for entry in log:`` on every apply-log this
        library ships."""
        return iter(self.entries)

    def __len__(self) -> int:
        """How many entries — 1:1 with the plan, in plan order, on every run."""
        return len(self.entries)

    @property
    def applied(self) -> Tuple[ApplyLogEntry, ...]:
        return tuple(e for e in self.entries if e.is_applied)

    @property
    def refusals(self) -> Tuple[ApplyLogEntry, ...]:
        return tuple(e for e in self.entries if not e.is_applied)

    @property
    def dropped(self) -> Tuple[ApplyLogEntry, ...]:
        """Every entry whose call answered ``code:0`` without moving the anchor."""
        return tuple(e for e in self.entries if e.outcome == "dropped")

    @property
    def indeterminate(self) -> Tuple[ApplyLogEntry, ...]:
        return tuple(e for e in self.entries if e.is_indeterminate)

    @property
    def not_attempted(self) -> Tuple[ApplyLogEntry, ...]:
        return tuple(e for e in self.entries if e.outcome == "not-attempted")

    @property
    def stale(self) -> Tuple[ApplyLogEntry, ...]:
        return tuple(e for e in self.entries if e.outcome == "stale")

    @property
    def halted(self) -> bool:
        return self.halt is not None

    def of_table(self, table_id: str) -> Tuple[ApplyLogEntry, ...]:
        return tuple(e for e in self.entries if e.table_id == table_id)

    @property
    def families(self) -> Dict[str, int]:
        """The per-family view of what **landed** — ``{op: count}`` over :attr:`applied` only.

        ``len(self.applied)`` is one number spanning two engines' worth of very different
        verbs: a schema-registry build reads back as ``46 applied`` (45 ``create_field`` + 1
        ``delete_field``) and a record run's 46 span creates, updates and deletes. This
        disaggregates it, **inventing no vocabulary**: the keys are the ops the entries
        themselves carry — ``{"create", "update", "delete"}`` on the record engine
        (``compiler._OPS``) and the descriptor names (``create_field`` / ``delete_field`` / …)
        on the schema engine — and an op this accessor has never seen is reported **as itself**,
        never bucketed or dropped.

        Counted over :attr:`applied` **only**, deliberately, for two reasons: the ask is about
        the ``applied`` number, and it sidesteps the ``op="refused"`` trap — the record compiler
        stores a *disposition* in the ``op`` slot for a plan-time refusal (``compiler.py``), and
        such an entry is never ``applied``, so a bogus ``refused`` family cannot appear. The
        counts therefore **reconcile exactly**: ``sum(families.values()) == len(applied)``, with
        no entry double-counted and none dropped.

        A computed convenience, not a stored slot: it is **absent from** :meth:`to_dict` — a
        shared log's serialized shape must not move for a slot one of its engines does not use
        (LD-337).
        """
        counts: Dict[str, int] = {}
        for entry in self.applied:
            counts[entry.op] = counts.get(entry.op, 0) + 1
        return counts

    def to_dict(self) -> dict:
        blob = {
            "entries": [e.to_dict() for e in self.entries],
            "halt": self.halt,
            "table_halts": dict(self.table_halts),
        }
        # ABSENT, not null: see the class docstring. The record engine's serialized log stays
        # byte-identical to what it was before the slot existed.
        if self.platform_anomaly is not None:
            blob["platform_anomaly"] = self.platform_anomaly
        return blob

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), **kwargs)


__all__ = [
    "ApplyLog",
    "ApplyLogEntry",
    "BATCH_BUMPS_ANCHOR_ONCE",
    "CALL_KINDS",
    "NO_SERVER_SIDE_CAS",
    "Plan",
    "PlanEntry",
    "PlannedCall",
    "REVISION_GUARD_ACTIVE",
    "REVISION_GUARD_UNAVAILABLE",
    "Refusal",
    "TablePlan",
    "VALUE_PRECONDITION_ENFORCED",
    "VALUE_PRECONDITION_NONE",
    "revision_guard_semantics",
    "revision_guard_status",
]
