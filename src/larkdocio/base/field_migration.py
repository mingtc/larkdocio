"""larkdocio.base.field_migration — the guided column-type migration.

**The refusal stays; the sequence gets the fence.** ``convert_field`` still refuses
``Text -> Number`` with :class:`~larkdocio.base.field_authoring.UncapturedConversionError`, and
that refusal is right: a cross-storage-type conversion rewrites every value in a column
server-side and permanently, and no committed capture shows what Lark does to the cells. What
this module answers is what a consumer does *next*. Told no, they hand-write

``create Estimate__new (Number)`` → ``copy 11 values`` → ``DELETE Estimate`` →
``rename Estimate__new to Estimate``

— whose middle step is fenced beautifully and whose **sequence is not fenced at all**. The
library's safety machinery sees four unrelated operations and never sees the operation the
consumer is performing, so nothing in the system knows that deleting ``Estimate`` is safe *only
if* the copy round-tripped first. This module makes the sequence the unit: one plan, one
consent, one 1:1 log.

**It owns no client call.** Every write goes through a plan the shipped previewers minted and
an apply the shipped engines own — :func:`~larkdocio.base.schema_apply.schema_dry_run` /
:func:`~larkdocio.base.schema_apply.schema_apply` for the three schema steps,
:func:`~larkdocio.base.apply.dry_run` / :func:`~larkdocio.base.apply.apply` for the value copy.
There is no new seam onto a Base client here, and therefore no new bypass of the plan gate, the
allow-list, the write encoders, the revision guard or the consent fence. What this module owns
is an **order** and a set of **refusals**.

**Consent is the existing primitive, one level up.**
:func:`~larkdocio.base.schema_apply.consent_to_destroy` mints the same
:class:`~larkdocio.base.schema_apply.DestructiveConsent`, with the same private token, bound to
the :class:`FieldMigrationPlan` — and the delete step re-plans against the live Base and
compares its **fresh** loss preview to the one that was consented to, refusing on any
difference. Consent is therefore consent to an enumeration taken immediately before the
destruction, not to a stale one carried forward.

**The values pass through the caller's own process.** Source cells are read as L1 renders them
and **transcoded** into the target kind's write input by the explicit table below; every
transcoded value is then put through :func:`~larkdocio.base.write_cells.encode_cell` at PLAN
time. A value with no transcoding, or one the encoder refuses, refuses the **whole migration**
before anything is sent. Nothing is coerced on a guess and no lossy mode ships:
guessing on your behalf would mean guessing about every value in the column.
"""
import json
from dataclasses import dataclass
from typing import Optional, Tuple

from larkdocio.base.apply import apply as record_apply, dry_run as record_dry_run
from larkdocio.base.cells import FieldSpec
from larkdocio.base.field_vocabulary import check_authorable
from larkdocio.base.model import ReadProof, snapshot_table
from larkdocio.base.plan import ApplyLog, ApplyLogEntry, Refusal
from larkdocio.base.schema_apply import (
    _check_consent,
    consent_to_destroy,
    schema_apply,
    schema_dry_run,
)
from larkdocio.base.schema_ops_destructive import delete_field
from larkdocio.base.schema_ops_fields import create_field, update_field
from larkdocio.base.table import assemble_table
from larkdocio.base.write_cells import BaseWriteRefusal, encode_cell, is_writable
from larkdocio.base.write_vocabulary import is_non_writable
from larkdocio.errors import LarkConfigError

# The private construction token. Only this module holds it, so a :class:`FieldMigrationPlan`
# can be built solely via :func:`plan_field_migration` — the fifth surface under the same hard
# gate as ``write.preview._PLAN_TOKEN`` / ``sheets.plan`` / ``base.plan`` / ``base.schema_plan``.
_MIGRATION_PLAN_TOKEN = object()


# --------------------------------------------------------------------------- #
# The three statements this rung must not get wrong, authored ONCE              #
# --------------------------------------------------------------------------- #

#: **What this operation is not.** Quoted by the plan, by ``BASE.md`` (in the source repository) and by
#: the guide's recipe, so the four cannot drift.
MIGRATION_IS_NOT_A_CONVERSION = (
    "THIS IS NOT A CONVERSION, and the difference is the whole reason it exists. A conversion "
    "is a server-side rewrite of every value in a column that nobody has watched happen — "
    "which is why `convert_field` refuses every pair no capture covers, and why that refusal "
    "is unchanged by this operation. A migration is a CLIENT-SIDE REBUILD: a new column is "
    "authored, every value is read out, re-encoded in your own process and written into the "
    "new column, the copy is read back and compared, and only then is the old column deleted "
    "and the new one renamed. Nothing is transformed in place, nothing is registered as a "
    "conversion pair, and every value that lands passed through code you can read."
)

#: **What it cannot promise.** The sequence spans multiple HTTP calls across two engines.
MIGRATION_IS_NOT_ATOMIC = (
    "A MIGRATION CANNOT BE ATOMIC and nothing here implies it is. It is several HTTP calls "
    "across two engines, and this API offers no transaction to wrap them in. What it promises "
    "instead is an ACCOUNT: one log entry per step, in plan order, every one ending in a typed "
    "disposition, remaining steps logged not-attempted after a halt rather than dropped — and "
    "a halted run's log names the state your table is now in and what a recovery would do. The "
    "destructive step is unreachable until the copy has been read back and compared, so the "
    "failure a partial run leaves you with is a table with an EXTRA column, never one with a "
    "missing one."
)

#: Why an empty source cell is skipped rather than written.
EMPTY_CELLS_ARE_SKIPPED = (
    "An empty source cell is not a value: nothing is written for it, so the migrated column is "
    "empty there too. The record ids are listed so the count is a reading rather than a "
    "surprise."
)


# --------------------------------------------------------------------------- #
# The steps                                                                     #
# --------------------------------------------------------------------------- #

STEP_CREATE_STAGING = "create_staging_column"
STEP_COPY_VALUES = "copy_values"
STEP_VERIFY_COPY = "verify_copy"
STEP_DELETE_SOURCE = "delete_source_column"
STEP_RENAME_STAGING = "rename_staging_column"

#: The five steps, **in apply order**. The consumer never assembles this sequence and never
#: chooses the order; that is the finding this operation answers.
MIGRATION_STEPS: Tuple[str, ...] = (
    STEP_CREATE_STAGING, STEP_COPY_VALUES, STEP_VERIFY_COPY, STEP_DELETE_SOURCE,
    STEP_RENAME_STAGING,
)


# --------------------------------------------------------------------------- #
# The refusals — all local, all before a write client exists                    #
# --------------------------------------------------------------------------- #

class FieldMigrationRefused(LarkConfigError):
    """A migration this library refuses to plan, decided **locally**.

    Under :class:`~larkdocio.errors.LarkConfigError` like every other unsupported-input
    refusal on this surface, so ``except LarkDocIOError`` still catches it.
    """


class UntranscodableValueError(FieldMigrationRefused):
    """A value the target kind has no honest encoding for — or a target kind with no
    transcoding at all. Refuses the **whole** migration, at plan time."""


# --------------------------------------------------------------------------- #
# The transcoders — rendered source text → the target kind's WRITE input        #
# --------------------------------------------------------------------------- #

def _t_string(text: str):
    return text


def _t_number(text: str):
    """A strict numeric parse. ``"3"`` and ``"3.5"`` pass; ``"3 days"`` does not."""
    try:
        return float(text)
    except ValueError:
        raise ValueError("it is not a number") from None


_TRUE = ("true", "yes", "[x]", "✓")
_FALSE = ("false", "no", "[ ]", "")


def _t_bool(text: str):
    lowered = text.strip().lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ValueError("it is not one of true/false")


#: ``target ui_type -> the transcoding from L1's rendered cell text``. Deliberately SMALL: a
#: kind with no entry refuses rather than being guessed at, which is the same posture the
#: conversion refusal it stands beside takes. A link, an attachment, a person, a chat or a
#: location is a reference, not text, and turning rendered text back into one would be exactly
#: the invention this operation exists to avoid.
TRANSCODERS = {
    "Text": _t_string,
    "Barcode": _t_string,
    "Phone": _t_string,
    "Number": _t_number,
    "Progress": _t_number,
    "Currency": _t_number,
    "Rating": _t_number,
    "Checkbox": _t_bool,
}

#: The target kinds a migration can rebuild into, in registry order.
TRANSCODABLE_TARGETS: Tuple[str, ...] = tuple(TRANSCODERS)


# --------------------------------------------------------------------------- #
# The plan                                                                      #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class MigrationStep:
    """One step of the sequence — and one entry of the log.

    The attribute names ``table_id`` / ``record_id`` / ``op`` / ``fields`` / ``before`` /
    ``call_index`` are the record engine's, deliberately: they are what
    :class:`~larkdocio.base.plan.ApplyLogEntry`'s constructors read, so a migration rides the
    landed apply-log unchanged instead of a parallel one.
    """

    index: int = 0
    kind: str = ""
    describe: str = ""
    table_id: Optional[str] = None
    record_id: Optional[str] = None
    fields: Optional[dict] = None
    before: Optional[dict] = None
    #: How many **write** calls this step costs. ``0`` for the verification, which is a read.
    writes: int = 1
    loss_preview: Optional[dict] = None

    @property
    def op(self) -> str:
        return self.kind

    @property
    def call_index(self) -> int:
        return self.index

    def to_dict(self) -> dict:
        return {"index": self.index, "kind": self.kind, "describe": self.describe,
                "table_id": self.table_id, "writes": self.writes,
                "loss_preview": self.loss_preview}


class FieldMigrationPlan:
    """The whole sequence, previewed, before anything is sent.

    Non-forgeable in the shape every other plan on this surface is: the constructor is guarded
    by a module-private token, so the only way to obtain one is :func:`plan_field_migration`,
    and :func:`apply_field_migration` accepts nothing else.
    """

    __slots__ = ("app_token", "table_id", "table_name", "source", "staging_name",
                 "to_field_type", "to_ui_type", "properties", "revision_at_plan",
                 "values", "skipped_empty", "_delete_plan", "steps")

    def __init__(self, *, app_token=None, table_id=None, table_name="", source=None,
                 staging_name="", to_field_type=None, to_ui_type="", properties=None,
                 revision_at_plan=None, values=(), skipped_empty=(), delete_plan=None,
                 steps=(), _token: object = None):
        if _token is not _MIGRATION_PLAN_TOKEN:
            raise TypeError(
                "FieldMigrationPlan objects are produced only by "
                "larkdocio.base.field_migration.plan_field_migration(...); construct a plan "
                "via the planner, not directly.")
        object.__setattr__(self, "app_token", app_token)
        object.__setattr__(self, "table_id", table_id)
        object.__setattr__(self, "table_name", table_name)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "staging_name", staging_name)
        object.__setattr__(self, "to_field_type", to_field_type)
        object.__setattr__(self, "to_ui_type", to_ui_type)
        object.__setattr__(self, "properties", dict(properties or {}))
        object.__setattr__(self, "revision_at_plan", revision_at_plan)
        object.__setattr__(self, "values", tuple(values))
        object.__setattr__(self, "skipped_empty", tuple(skipped_empty))
        object.__setattr__(self, "_delete_plan", delete_plan)
        object.__setattr__(self, "steps", tuple(steps))

    # -- what the consent fence reads ---------------------------------------- #

    @property
    def destructive(self) -> bool:
        """Always ``True``: a migration deletes the source column. There is no shape of this
        operation that does not, which is why consent is never optional here."""
        return True

    @property
    def entries(self):
        """The **delete** dry run's own entries — what
        :func:`~larkdocio.base.schema_apply.consent_to_destroy` validates."""
        return self._delete_plan.entries

    @property
    def loss_previews(self) -> Tuple[dict, ...]:
        return self._delete_plan.loss_previews

    @property
    def loss_preview(self) -> Optional[dict]:
        previews = self.loss_previews
        return previews[0] if previews else None

    @property
    def api_call_count(self) -> int:
        """How many **write** calls the whole sequence will make."""
        return sum(step.writes for step in self.steps)

    def __iter__(self):
        return iter(self.steps)

    def __len__(self) -> int:
        return len(self.steps)

    def __repr__(self) -> str:
        return (f"FieldMigrationPlan(table={self.table_id!r}, "
                f"{self.source.field_name!r} -> {self.to_ui_type}, "
                f"values={len(self.values)}, calls={self.api_call_count})")

    def to_dict(self) -> dict:
        return {
            "app_token": self.app_token,
            "table_id": self.table_id,
            "table_name": self.table_name,
            "source": {"field_id": self.source.field_id,
                       "field_name": self.source.field_name,
                       "type": self.source.type, "ui_type": self.source.ui_type},
            "target": {"field_name": self.source.field_name, "type": self.to_field_type,
                       "ui_type": self.to_ui_type, "properties": dict(self.properties)},
            "staging_column": self.staging_name,
            "revision_at_plan": self.revision_at_plan,
            "values_to_copy": len(self.values),
            "skipped_empty": list(self.skipped_empty),
            "skipped_empty_note": EMPTY_CELLS_ARE_SKIPPED,
            "api_call_count": self.api_call_count,
            "destructive": True,
            "loss_preview": self.loss_preview,
            "not_a_conversion": MIGRATION_IS_NOT_A_CONVERSION,
            "not_atomic": MIGRATION_IS_NOT_ATOMIC,
            "steps": [step.to_dict() for step in self.steps],
        }

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), **kwargs)


# --------------------------------------------------------------------------- #
# plan_field_migration — the mandatory previewer. ZERO writes.                   #
# --------------------------------------------------------------------------- #

def _table_of(read_client, app_token, table_id):
    for table in (read_client.list_tables(app_token) or ()):
        if getattr(table, "table_id", None) == table_id:
            return table
    raise FieldMigrationRefused(
        f"table {table_id!r} is not listed in Base {app_token!r}, so there is nothing to "
        "migrate and nothing was sent.")


def _read_table(read_client, app_token, table_id):
    """``(table, fields, records, rendered)`` — the one read the plan is built on.

    ``rendered`` is L1's own cell text, taken through :func:`~larkdocio.base.table.assemble_table`
    rather than a second opinion about what a Base cell looks like.
    """
    table = _table_of(read_client, app_token, table_id)
    fields = list(read_client.list_fields(app_token, table_id) or ())
    records = list(read_client.search_records(app_token, table_id) or ())
    read = assemble_table(table_id=table_id, name=getattr(table, "name", "") or "",
                          fields=fields, records=records)
    names = [spec.field_name for spec in read.fields]
    rendered = {row.record_id: dict(zip(names, row.cells)) for row in read.rows}
    return table, read, records, rendered


def _staging_name_for(wanted: str, taken) -> str:
    candidate = f"{wanted}__larkdocio_migration"
    suffix = 2
    while candidate in taken:
        candidate = f"{wanted}__larkdocio_migration_{suffix}"
        suffix += 1
    return candidate


def _target_spec(name: str, field_type: int, ui_type: str, properties) -> FieldSpec:
    return FieldSpec(field_name=name, type=field_type, ui_type=ui_type,
                     property=dict(properties or {}) or None)


def plan_field_migration(read_client, app_token: str, table_id: str, *, field_name: str,
                         to_field_type: int, to_ui_type: str,
                         properties: Optional[dict] = None,
                         staging_name: Optional[str] = None) -> FieldMigrationPlan:
    """Preview the whole column-type migration. **Zero writes, and no write client is even
    accepted here.**

    Reads the table once, transcodes every source value into the target kind, enumerates what
    deleting the source column would cost through the shipped loss preview, and returns the
    five-step :class:`FieldMigrationPlan` :func:`apply_field_migration` takes.

    Refuses — locally, before anything is sent — an unauthorable target kind
    (:func:`~larkdocio.base.field_vocabulary.check_authorable`), a target whose cells cannot be
    written, a source whose cells cannot be read back (a Formula, a Lookup and the rest of the
    computed set — a copy nobody can verify is not a migration this library will run), and any
    value the target kind has no honest encoding for.

    ``MIGRATION_IS_NOT_A_CONVERSION`` applies: nothing here converts a column in place, and
    ``convert_field`` / ``CONVERSION_PAIRS`` are untouched.
    """
    # ---- the target kind: the SAME allow-list every create passes ------------- #
    check_authorable(to_field_type, to_ui_type)
    if not is_writable((to_field_type, to_ui_type)):
        raise FieldMigrationRefused(
            f"a column of kind {to_ui_type!r} ({to_field_type} / {to_ui_type}) can be created "
            "and its cells cannot be WRITTEN, so the values could never be copied into it. "
            "Nothing was sent.")
    if to_ui_type not in TRANSCODERS:
        raise UntranscodableValueError(
            f"this library ships no transcoding from a rendered cell into a {to_ui_type!r} "
            f"column, so a migration into one would have to guess what each value meant. The "
            f"target kinds it does rebuild into are: {', '.join(TRANSCODABLE_TARGETS)}. "
            f"{MIGRATION_IS_NOT_A_CONVERSION}")

    table, read, records, rendered = _read_table(read_client, app_token, table_id)
    specs = {spec.field_name: spec for spec in read.fields}
    source = specs.get(field_name)
    if source is None:
        raise FieldMigrationRefused(
            f"table {table_id!r} has no column named {field_name!r}. Re-read the table's "
            "columns and re-plan; nothing was sent.")
    if is_non_writable(source.pair) or not is_writable(source.pair):
        raise FieldMigrationRefused(
            f"the column {field_name!r} ({source.type} / {source.ui_type}) holds values this "
            "library cannot write, so a copy of it cannot be read back and compared — and a "
            "copy nobody can verify is exactly what this operation exists to prevent. Nothing "
            "was sent.")
    if source.field_id == "":
        raise FieldMigrationRefused(
            f"the column {field_name!r} carries no field_id in this read, so neither the "
            "delete nor its loss preview could be addressed. Re-read the table and re-plan.")

    staging = staging_name or _staging_name_for(field_name, set(specs))
    if staging in specs:
        raise FieldMigrationRefused(
            f"a column named {staging!r} already exists in table {table_id!r}; the staging "
            "column must be new, or a migration would write into somebody else's data.")

    # ---- the values: transcoded and ENCODED here, before anything is sent ----- #
    target_spec = _target_spec(staging, to_field_type, to_ui_type, properties)
    transcode = TRANSCODERS[to_ui_type]
    values, skipped, offences = [], [], []
    for record in read.rows:
        text = rendered[record.record_id].get(field_name, "")
        if text == "":
            skipped.append(record.record_id)
            continue
        try:
            encoded = encode_cell(transcode(text), target_spec)
        except ValueError as exc:
            offences.append((record.record_id, text, str(exc)))
            continue
        except BaseWriteRefusal as exc:
            offences.append((record.record_id, text, str(exc)))
            continue
        values.append((record.record_id, text, encoded))

    if offences:
        listed = "; ".join(f"{record_id}: {text!r} — {why}"
                           for record_id, text, why in offences)
        raise UntranscodableValueError(
            f"{len(offences)} value(s) in {field_name!r} have no honest encoding as a "
            f"{to_ui_type} column, so the WHOLE migration refuses before anything is sent: "
            f"{listed}. Guessing on your behalf would mean guessing about every value in the "
            "column — fix or clear the values named above and re-plan. Nothing was sent, and "
            "nothing was destroyed.")

    # ---- the destructive step's loss preview: the SHIPPED one, unchanged ------ #
    revision = getattr(table, "revision", None)
    delete_plan = schema_dry_run(
        [delete_field(app_token, table_id, source.field_id, revision=revision)],
        read_client=read_client)
    entry = delete_plan.entries[0]
    if entry.refusal is not None:
        raise FieldMigrationRefused(
            f"what deleting {field_name!r} would cost could not be enumerated, so the "
            f"migration refuses before anything is sent: {entry.refusal.detail}")

    steps = (
        MigrationStep(index=0, kind=STEP_CREATE_STAGING, table_id=table_id,
                      describe=(f"create the staging column {staging!r} ({to_ui_type}) in "
                                f"table {table_id}"),
                      fields={"field_name": staging, "ui_type": to_ui_type}),
        MigrationStep(index=1, kind=STEP_COPY_VALUES, table_id=table_id,
                      describe=(f"copy {len(values)} re-encoded value(s) from {field_name!r} "
                                f"into {staging!r} ({len(skipped)} empty cell(s) skipped)"),
                      fields={"values": len(values), "skipped_empty": len(skipped)}),
        MigrationStep(index=2, kind=STEP_VERIFY_COPY, table_id=table_id, writes=0,
                      describe=(f"read {staging!r} back and compare every value against "
                                f"{field_name!r} — the delete below is unreachable until this "
                                "passes"),
                      fields={"values": len(values)}),
        MigrationStep(index=3, kind=STEP_DELETE_SOURCE, table_id=table_id,
                      describe=f"DELETE the source column {field_name!r} in table {table_id}",
                      fields={"field_id": source.field_id, "field_name": field_name},
                      loss_preview=entry.loss_preview),
        MigrationStep(index=4, kind=STEP_RENAME_STAGING, table_id=table_id,
                      describe=f"rename {staging!r} to {field_name!r}",
                      fields={"field_name": field_name}),
    )
    return FieldMigrationPlan(
        app_token=app_token, table_id=table_id,
        table_name=getattr(table, "name", "") or "", source=source, staging_name=staging,
        to_field_type=to_field_type, to_ui_type=to_ui_type, properties=properties,
        revision_at_plan=revision, values=tuple(values), skipped_empty=tuple(skipped),
        delete_plan=delete_plan, steps=steps, _token=_MIGRATION_PLAN_TOKEN)


# --------------------------------------------------------------------------- #
# apply_field_migration — the runner. Every write goes through a shipped apply.  #
# --------------------------------------------------------------------------- #

def _refused(step, reason, detail) -> ApplyLogEntry:
    return ApplyLogEntry.refused(step, refusal=Refusal(reason=reason, detail=detail))


def _not_attempted(step, *, where, why) -> ApplyLogEntry:
    return ApplyLogEntry.not_attempted(step, refusal=Refusal(
        reason=Refusal.NOT_ATTEMPTED,
        detail=(f"the migration halted at {where} ({why}), so this step was never attempted "
                f"and NOTHING was sent for it. {MIGRATION_IS_NOT_ATOMIC}")))


def _live_revision(read_client, app_token, table_id):
    for table in (read_client.list_tables(app_token) or ()):
        if getattr(table, "table_id", None) == table_id:
            return getattr(table, "revision", None)
    return None


def _field_by_name(read_client, app_token, table_id, name):
    from larkdocio.base.table import field_spec

    for field in (read_client.list_fields(app_token, table_id) or ()):
        spec = field_spec(field)
        if spec.field_name == name:
            return spec
    return None


def _same_value(sent, seen) -> bool:
    """Did the value we sent survive the round trip?

    Numbers are compared **numerically** — Lark answers a Number cell as a float whatever went
    in — and everything else by equality. Nothing is normalised beyond that: a comparison that
    forgave a difference would be the copy check waving through the failure it exists to catch.
    """
    if isinstance(sent, bool) or isinstance(seen, bool):
        return bool(sent) == bool(seen) and isinstance(sent, bool) == isinstance(seen, bool)
    if isinstance(sent, (int, float)) and isinstance(seen, (int, float)):
        return float(sent) == float(seen)
    return sent == seen


def _one_page(records):
    return {"items": list(records), "has_more": False, "page_token": None}


def _recovery(plan, read_client, *, where) -> dict:
    """What state the table is in **now**, read from the server, and what a recovery would do."""
    names = []
    try:
        names = [getattr(field, "field_name", None)
                 for field in (read_client.list_fields(plan.app_token, plan.table_id) or ())]
    except Exception:                    # noqa: BLE001 — a recovery note never raises
        names = []
    source_present = plan.source.field_name in names
    staging_present = plan.staging_name in names
    if source_present and staging_present:
        what = (f"your data is INTACT in {plan.source.field_name!r}. The staging column "
                f"{plan.staging_name!r} was left behind and holds whatever the copy managed "
                "to write; delete it (a normal delete_field, behind its own loss preview and "
                "consent) and re-plan the migration, or investigate why the copy did not "
                "round-trip before trying again.")
    elif source_present:
        what = (f"your data is INTACT in {plan.source.field_name!r} and no staging column "
                "exists: the migration stopped before it changed anything. Re-plan and "
                "re-apply.")
    elif staging_present:
        what = (f"the source column is GONE and the values are in {plan.staging_name!r}, "
                f"which has not been renamed yet. Rename it to "
                f"{plan.source.field_name!r} — that is the one step left — before anything "
                "else reads this table.")
    else:
        what = ("NEITHER column is listed. Re-read the table before doing anything else: this "
                "is not a state this sequence produces on its own, so something else has "
                "changed the table.")
    return {
        "halted_at": where,
        "table_id": plan.table_id,
        "columns_now": [name for name in names if name],
        "source_column": plan.source.field_name,
        "source_column_present": source_present,
        "staging_column": plan.staging_name,
        "staging_column_present": staging_present,
        "values_planned": len(plan.values),
        "what_a_recovery_would_do": what,
        "not_atomic": MIGRATION_IS_NOT_ATOMIC,
    }


def _schema_leg(request, *, schema_client, read_client, plan=None, consent=None):
    """One schema step, through the shipped previewer and the shipped apply. Returns its
    :class:`~larkdocio.base.plan.ApplyLog` entry.

    ``plan`` is passed when the caller already minted one — the destructive step does, because
    its consent is bound to that plan object and re-planning here would break the binding it
    exists to enforce.
    """
    if plan is None:
        plan = schema_dry_run([request], read_client=read_client)
    # allow_partial: this leg CONSUMES the log — it turns a refused step into the migration's
    # own typed halt below, which is a stronger account than a bare raise from inside a
    # multi-step sequence. The refusal is not swallowed; it becomes this engine's own.
    log = schema_apply(plan, client=schema_client, read_client=read_client, consent=consent,
                       allow_partial=True)
    return log.entries[0]


def apply_field_migration(plan, *, schema_client, client, read_client,
                          consent=None) -> ApplyLog:
    """Run a :class:`FieldMigrationPlan`, returning the record engine's
    :class:`~larkdocio.base.plan.ApplyLog` — one entry per step, in plan order, on every run.

    ``schema_client`` is a :class:`~larkdocio.base.schema_client.BaseSchemaClient`, ``client`` a
    :class:`~larkdocio.base.write_client.BaseWriteClient` and ``read_client`` a
    :class:`~larkdocio.base.client.BaseReadClient` (all duck-typed). All three are required:
    the sequence authors a column, writes rows and verifies both by reading.

    ``consent`` is the existing :class:`~larkdocio.base.schema_apply.DestructiveConsent`, minted
    from **this** plan by :func:`~larkdocio.base.schema_apply.consent_to_destroy`. Without it
    this refuses before any call. ``MIGRATION_IS_NOT_ATOMIC`` applies.
    """
    if not isinstance(plan, FieldMigrationPlan):
        raise TypeError(
            "apply_field_migration() takes a FieldMigrationPlan produced by "
            "larkdocio.base.field_migration.plan_field_migration(...) and nothing else; got "
            f"{type(plan).__name__}.")
    if schema_client is None or client is None or read_client is None:
        raise TypeError(
            "apply_field_migration() needs all THREE clients: a schema client to author and "
            "delete the columns, a write client to copy the values, and a read client — "
            "because every step here is verified by a read, and the copy is compared against "
            "the source before anything is destroyed.")
    # THE CONSENT FENCE, the existing one, before anything else and before any call.
    _check_consent(plan, consent)

    results: list = [None] * len(plan.steps)
    halt = None

    def _halt(position, where, reason, detail):
        nonlocal halt
        halt = {"index": position, "where": where, "reason": reason, "detail": detail,
                "recovery": _recovery(plan, read_client, where=where)}

    # ---- step 0: STALE_BASE for the whole plan, then the staging column ------- #
    live = _live_revision(read_client, plan.app_token, plan.table_id)
    if (plan.revision_at_plan is not None and live is not None
            and live != plan.revision_at_plan):
        results[0] = ApplyLogEntry.stale(plan.steps[0], refusal=Refusal(
            reason=Refusal.STALE_BASE,
            detail=(f"table {plan.table_id} moved under this migration plan: "
                    f"`table.revision` was {plan.revision_at_plan!r} when the plan was built "
                    f"and reads {live!r} now, so something else changed this table in "
                    "between. ZERO writes were issued — not one step of the sequence ran. "
                    "Re-read the table, re-plan the migration, mint fresh consent, and "
                    "re-apply.")))
        _halt(0, plan.steps[0].describe, Refusal.STALE_BASE, results[0].refusal.detail)
    else:
        results[0] = _run_create(plan, schema_client, read_client, live)
        if results[0].outcome != "applied":
            _halt(0, plan.steps[0].describe, (results[0].refusal or Refusal()).reason,
                  getattr(results[0].refusal, "detail", ""))

    # ---- step 1: the value copy, through the RECORD engine -------------------- #
    if halt is None:
        results[1] = _run_copy(plan, client, read_client)
        if results[1].outcome != "applied":
            _halt(1, plan.steps[1].describe, (results[1].refusal or Refusal()).reason,
                  getattr(results[1].refusal, "detail", ""))

    # ---- step 2: the verification the delete is unreachable without ----------- #
    if halt is None:
        results[2] = _run_verify(plan, read_client)
        if results[2].outcome != "applied":
            _halt(2, plan.steps[2].describe, (results[2].refusal or Refusal()).reason,
                  getattr(results[2].refusal, "detail", ""))

    # ---- step 3: the delete, re-planned and re-previewed immediately before --- #
    if halt is None:
        results[3] = _run_delete(plan, schema_client, read_client)
        if results[3].outcome != "applied":
            _halt(3, plan.steps[3].describe, (results[3].refusal or Refusal()).reason,
                  getattr(results[3].refusal, "detail", ""))

    # ---- step 4: the rename ---------------------------------------------------- #
    if halt is None:
        results[4] = _run_rename(plan, schema_client, read_client)
        if results[4].outcome != "applied":
            _halt(4, plan.steps[4].describe, (results[4].refusal or Refusal()).reason,
                  getattr(results[4].refusal, "detail", ""))

    for position, step in enumerate(plan.steps):
        if results[position] is None:
            results[position] = _not_attempted(
                step, where=(halt or {}).get("where", "an earlier step"),
                why=(halt or {}).get("reason", Refusal.NOT_ATTEMPTED))

    if halt is not None:
        halt["not_attempted"] = sum(1 for entry in results
                                    if entry.outcome == "not-attempted")
    return ApplyLog(entries=tuple(results), halt=halt)


def _run_create(plan, schema_client, read_client, revision) -> ApplyLogEntry:
    step = plan.steps[0]
    request = create_field(plan.app_token, plan.table_id, plan.staging_name,
                           plan.to_field_type, ui_type=plan.to_ui_type,
                           properties=plan.properties or None, revision=revision)
    landed = _schema_leg(request, schema_client=schema_client, read_client=read_client)
    if landed.outcome == "applied":
        return ApplyLogEntry.applied(step)
    return ApplyLogEntry(outcome=landed.outcome, table_id=step.table_id, op=step.op,
                         fields=step.fields, call_index=step.call_index,
                         refusal=landed.refusal)


def _run_copy(plan, client, read_client) -> ApplyLogEntry:
    """The value copy — the record engine's own previewer and apply, nothing else."""
    step = plan.steps[1]
    if not plan.values:
        return ApplyLogEntry.applied(step)
    table, read, records, _rendered = _read_table(read_client, plan.app_token, plan.table_id)
    snapshot = snapshot_table(read, app_token=plan.app_token,
                              revision=getattr(table, "revision", None),
                              read_proof=ReadProof.from_pages([_one_page(records)]))
    if plan.staging_name not in {spec.field_name for spec in snapshot.fields}:
        return _refused(step, Refusal.WRITE_NOT_OBSERVED,
                        f"the staging column {plan.staging_name!r} is not in the table's "
                        "schema after its create was confirmed, so there is nowhere to copy "
                        "the values to. NOTHING was written and nothing was destroyed.")
    draft = snapshot.edit()
    for record_id, _text, encoded in plan.values:
        draft.set(record_id, plan.staging_name, encoded)
    # allow_partial: the copies that did NOT land are exactly what this step reports (and
    # halts the migration on), so the log is read here rather than raised past.
    log = record_apply(record_dry_run(draft), client=client, read_client=read_client,
                       allow_partial=True)
    bad = [entry for entry in log.entries if entry.outcome != "applied"]
    if bad:
        detail = "; ".join(f"{entry.record_id}: {entry.outcome}"
                           f"{' — ' + entry.refusal.detail if entry.refusal else ''}"
                           for entry in bad)
        return _refused(step, Refusal.WRITE_NOT_OBSERVED,
                        f"{len(bad)} of {len(log.entries)} value copies did not land, so the "
                        f"migration HALTED before anything was destroyed: {detail}")
    return ApplyLogEntry.applied(step)


def _run_verify(plan, read_client) -> ApplyLogEntry:
    """AC4's gate: the delete below is unreachable until every value has been read back."""
    step = plan.steps[2]
    raw = {}
    for record in (read_client.search_records(plan.app_token, plan.table_id) or ()):
        raw[getattr(record, "record_id", None)] = dict(getattr(record, "fields", None) or {})
    mismatches, missing = [], []
    for record_id, text, encoded in plan.values:
        if record_id not in raw:
            missing.append(record_id)
            continue
        seen = raw[record_id].get(plan.staging_name)
        if plan.staging_name not in raw[record_id] or not _same_value(encoded, seen):
            mismatches.append((record_id, text, encoded, seen))
    landed = sum(1 for record_id in raw
                 if plan.staging_name in raw[record_id]
                 and raw[record_id].get(plan.staging_name) not in (None, "", [], {}))
    if mismatches or missing or landed != len(plan.values):
        parts = []
        if mismatches:
            parts.append("; ".join(
                f"{record_id}: source {text!r} was written as {encoded!r} and the column "
                f"does not hold it (it reads {seen!r})"
                for record_id, text, encoded, seen in mismatches))
        if missing:
            parts.append(f"records no longer in the table: {missing}")
        if landed != len(plan.values):
            parts.append(f"the staging column holds {landed} value(s) and the copy wrote "
                         f"{len(plan.values)}; the column does not hold what was sent")
        return _refused(
            step, Refusal.PRECONDITION_MISMATCH,
            f"THE COPY DID NOT ROUND-TRIP, so NOTHING is destroyed and the source column "
            f"{plan.source.field_name!r} is untouched: {'. '.join(parts)}. The delete was "
            "never attempted. Read the staging column, fix what this names, and re-plan.")
    return ApplyLogEntry.applied(step)


def _run_delete(plan, schema_client, read_client) -> ApplyLogEntry:
    """The destructive step: re-planned, re-previewed and compared to what was consented to."""
    step = plan.steps[3]
    revision = _live_revision(read_client, plan.app_token, plan.table_id)
    request = delete_field(plan.app_token, plan.table_id, plan.source.field_id,
                           revision=revision)
    step_plan = schema_dry_run([request], read_client=read_client)
    fresh = step_plan.entries[0]
    if fresh.refusal is not None:
        return _refused(step, fresh.refusal.reason, fresh.refusal.detail)
    if fresh.loss_preview != plan.loss_preview:
        return _refused(
            step, Refusal.PRECONDITION_MISMATCH,
            "what deleting this column costs has CHANGED since you consented to it, so the "
            "delete refuses and nothing is destroyed. Consent is consent to an enumerated "
            "loss; the enumeration taken immediately before the delete does not match the one "
            "you read. Re-plan the migration, read the new preview and consent to that. The "
            "staging column is in place and holds the copied values.")
    landed = _schema_leg(request, schema_client=schema_client, read_client=read_client,
                         plan=step_plan, consent=consent_to_destroy(step_plan))
    if landed.outcome == "applied":
        return ApplyLogEntry.applied(step)
    return ApplyLogEntry(outcome=landed.outcome, table_id=step.table_id, op=step.op,
                         fields=step.fields, call_index=step.call_index,
                         refusal=landed.refusal)


def _run_rename(plan, schema_client, read_client) -> ApplyLogEntry:
    step = plan.steps[4]
    revision = _live_revision(read_client, plan.app_token, plan.table_id)
    staging = _field_by_name(read_client, plan.app_token, plan.table_id, plan.staging_name)
    if staging is None:
        return _refused(step, Refusal.WRITE_NOT_OBSERVED,
                        f"the staging column {plan.staging_name!r} is no longer listed, so it "
                        "cannot be renamed. The source column has already been deleted — read "
                        "the recovery note on this log's halt before doing anything else.")
    request = update_field(plan.app_token, plan.table_id, staging.field_id,
                           plan.source.field_name, plan.to_field_type,
                           ui_type=plan.to_ui_type, properties=plan.properties or None,
                           revision=revision)
    landed = _schema_leg(request, schema_client=schema_client, read_client=read_client)
    if landed.outcome == "applied":
        return ApplyLogEntry.applied(step)
    return ApplyLogEntry(outcome=landed.outcome, table_id=step.table_id, op=step.op,
                         fields=step.fields, call_index=step.call_index,
                         refusal=landed.refusal)


__all__ = [
    "EMPTY_CELLS_ARE_SKIPPED",
    "MIGRATION_IS_NOT_ATOMIC",
    "MIGRATION_IS_NOT_A_CONVERSION",
    "MIGRATION_STEPS",
    "STEP_COPY_VALUES",
    "STEP_CREATE_STAGING",
    "STEP_DELETE_SOURCE",
    "STEP_RENAME_STAGING",
    "STEP_VERIFY_COPY",
    "TRANSCODABLE_TARGETS",
    "TRANSCODERS",
    "FieldMigrationPlan",
    "FieldMigrationRefused",
    "MigrationStep",
    "UntranscodableValueError",
    "apply_field_migration",
    "plan_field_migration",
]
