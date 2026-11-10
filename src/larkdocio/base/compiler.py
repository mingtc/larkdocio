"""larkdocio.base.compiler — the typed diff → batch requests (LD-259).

**Where a diff becomes calls.** :mod:`larkdocio.base.diff` types what happens to every record;
this module turns that into the **batch** calls a Base write is actually made of, and it makes
the grouping **visible in the plan**: how many API calls, and which records ride in which one.
That is not cosmetic — Lark judges a ``batch_update`` as a whole, so the call is the failure
granularity a consumer has to reason about, and a plan that hid it would hide exactly the thing
they need to approve.

**Values are encoded by LD-256's registry, never here.** Every cell goes through
:func:`larkdocio.base.write_cells.encode_fields`, so a write shape is authored in exactly one
place and a value the registry refuses becomes a **plan-time refusal** — decided before any
call, costing zero API calls.

**No call is made from this module.** It is pure, offline and deterministic: the same diff
compiles to the same plan, in the same order, every time. Creates come first, then updates,
then deletes.
"""
from dataclasses import replace
from typing import Optional, Sequence, Tuple

from larkdocio.base import diff as base_diff
from larkdocio.base.plan import (
    CALL_KINDS,
    PlanEntry,
    PlannedCall,
    Refusal,
    TablePlan,
    VALUE_PRECONDITION_ENFORCED,
    VALUE_PRECONDITION_NONE,
)
from larkdocio.base.write_cells import BaseWriteRefusal, encode_fields

#: ``disposition -> (op, call kind)``. ``unchanged`` is deliberately absent: a record nothing
#: happens to is not an entry, and the count is disclosed on the table plan instead.
_OPS = {
    base_diff.CREATED: ("create", "batch_create"),
    base_diff.EDITED: ("update", "batch_update"),
    base_diff.DELETED: ("delete", "batch_delete"),
}


def _chunks(items: Sequence, size: Optional[int]):
    if not items:
        return []
    if not size or size <= 0:
        return [list(items)]
    return [list(items[i:i + size]) for i in range(0, len(items), size)]


def _effect_dicts(disposition) -> Tuple[dict, ...]:
    return tuple({
        "field_name": effect.field_name,
        "pair": list(effect.pair),
        "table_id": effect.table_id,
        "table_name": effect.table_name,
        "effect": effect.effect,
        "dangling_target": effect.dangling_target,
    } for effect in disposition.cross_table)


def _refusal_for_non_writable(disposition) -> Refusal:
    parts = "; ".join(
        f"{refusal.field_name} ({refusal.pair[0]} / {refusal.pair[1]}): {refusal.reason}"
        for refusal in disposition.refusals)
    return Refusal(
        reason=Refusal.NON_WRITABLE_FIELD,
        detail=(f"record {disposition.record_id} writes a field that cannot be written, so "
                f"nothing is planned for it and no call is made. {parts}"))


def compile_table(table_diff, snapshot, *, records_per_call=None,
                  call_offset: int = 0) -> TablePlan:
    """One table's :class:`~larkdocio.base.diff.TableDiff` → one :class:`TablePlan`.

    ``snapshot`` is the :class:`~larkdocio.base.model.BaseTableSnapshot` the diff was taken
    against — the schema the encoders need, and the source of a deleted record's ``before``.
    ``call_offset`` is where this table's calls start in the whole plan's numbering, so an
    entry's ``call_index`` is unique across a multi-table plan.
    """
    specs = tuple(snapshot.fields)
    entries = []
    unchanged = 0
    per_kind = {kind: [] for _op, kind in _OPS.values()}

    for disposition in table_diff.dispositions:
        record_id = disposition.record_id
        if disposition.disposition == base_diff.UNCHANGED:
            unchanged += 1
            continue
        if disposition.disposition == base_diff.REFUSED:
            entries.append(PlanEntry(
                table_id=table_diff.table_id, table_name=table_diff.name,
                record_id=record_id, op="refused",
                before={c.field_name: c.before for c in disposition.changes},
                refusal=_refusal_for_non_writable(disposition),
                value_precondition=VALUE_PRECONDITION_NONE,
                cross_table=_effect_dicts(disposition)))
            continue

        op, kind = _OPS[disposition.disposition]
        if op == "delete":
            entry = PlanEntry(
                table_id=table_diff.table_id, table_name=table_diff.name,
                record_id=record_id, op=op,
                before=snapshot.record(record_id).as_dict(),
                value_precondition=VALUE_PRECONDITION_ENFORCED)
        else:
            written = {change.field_name: change.after for change in disposition.changes}
            try:
                payload = encode_fields(written, specs)
            except BaseWriteRefusal as exc:
                entries.append(PlanEntry(
                    table_id=table_diff.table_id, table_name=table_diff.name,
                    record_id=record_id, op="refused",
                    before={c.field_name: c.before for c in disposition.changes},
                    refusal=Refusal(reason=Refusal.INVALID_REQUEST, detail=str(exc)),
                    value_precondition=VALUE_PRECONDITION_NONE,
                    cross_table=_effect_dicts(disposition)))
                continue
            entry = PlanEntry(
                table_id=table_diff.table_id, table_name=table_diff.name,
                record_id=record_id, op=op, fields=payload,
                before=({change.field_name: change.before for change in disposition.changes}
                        if op == "update" else None),
                value_precondition=(VALUE_PRECONDITION_ENFORCED if op == "update"
                                    else VALUE_PRECONDITION_NONE),
                cross_table=_effect_dicts(disposition))
        per_kind[kind].append(len(entries))       # the entry's position, not the entry
        entries.append(entry)

    # ---- the calls, and the back-reference every entry carries ---------------- #
    calls = []
    index = call_offset
    for kind in CALL_KINDS:
        for chunk in _chunks(per_kind[kind], records_per_call):
            calls.append(PlannedCall(
                index=index, table_id=table_diff.table_id, kind=kind,
                record_ids=tuple(entries[position].record_id for position in chunk)))
            for position in chunk:
                entries[position] = replace(entries[position], call_index=index,
                                            call_kind=kind)
            index += 1

    return TablePlan(table_id=table_diff.table_id, name=table_diff.name,
                     revision=table_diff.revision, entries=entries,
                     calls=tuple(calls), unchanged=unchanged)


def compile_base(base_diff_, snapshot, *, records_per_call=None) -> Tuple[TablePlan, ...]:
    """A whole-Base diff → one :class:`TablePlan` per table that has something to do.

    A table with no entry is left out: it has no call, no anchor to compare and nothing to
    log, and carrying it would put an empty leg in front of every consumer reading the plan.
    """
    tables = []
    offset = 0
    for table_diff in base_diff_.tables:
        table_plan = compile_table(
            table_diff, snapshot.table(table_diff.table_id),
            records_per_call=records_per_call, call_offset=offset)
        if not table_plan.entries:
            continue
        offset += len(table_plan.calls)
        tables.append(table_plan)
    return tuple(tables)
