"""LD-342 — ApplyLog gains a per-family view of what LANDED.

The consumer's `46 applied` = 45 adds + 1 delete: accurate but alarming. This adds a
**computed** `families` accessor — a mapping of the entry's own `op` string to how many
**applied** entries carried it — so a log self-explains without the library inventing an op
vocabulary. It is a property over `entries`, the way `applied` / `dropped` / `of_table`
already are: no new field, no constructor change, no existing accessor re-typed.

Scope facts pinned here (see the issue § Problem):
  * one class, two engines — record (`op` ∈ {create,update,delete}) and schema (descriptor
    names like `create_field` / `delete_field`);
  * the `op="refused"` trap — the record compiler stores a *disposition* in the op slot for a
    plan-time refusal; such an entry is never `applied`, and `families` counts over `applied`
    ONLY, so the trap is sidestepped by construction;
  * an op the accessor has never seen is reported **as itself** — nothing swallowed, nothing
    dropped, the total still reconciles.
"""

from larkdocio.base.plan import ApplyLog, ApplyLogEntry


def _applied(op):
    return ApplyLogEntry(outcome="applied", op=op)


def _refused(op):
    return ApplyLogEntry(outcome="refused", op=op)


def _record_log():
    """A record-engine shape: creates + updates + deletes in one run, plus a refusal."""
    return ApplyLog(entries=(
        _applied("create"), _applied("create"),
        _applied("update"),
        _applied("delete"),
        _refused("refused"),          # the trap: a disposition in the op slot
        ApplyLogEntry(outcome="dropped", op="update"),
    ))


def _schema_log():
    """The consumer's shape: many create_field + one delete_field — must read 45 adds + 1 delete."""
    return ApplyLog(entries=tuple(
        [_applied("create_field") for _ in range(45)] + [_applied("delete_field")]
    ))


# ---- AC1: the counts exist, are additive, computed over entries -------------------------

def test_families_is_a_computed_mapping_over_applied_entries():
    log = _record_log()
    assert log.families == {"create": 2, "update": 1, "delete": 1}


def test_families_on_empty_log_is_empty_and_reconciles():
    log = ApplyLog()
    assert log.families == {}
    assert sum(log.families.values()) == len(log.applied) == 0


def test_pre_existing_accessors_unchanged_on_the_same_log():
    log = _record_log()
    # applied still answers exactly what it answered before this issue.
    assert len(log.applied) == 4
    assert len(log.refusals) == 2          # the refused entry + the dropped entry
    assert len(log.dropped) == 1
    assert log.families is not None


# ---- AC2: no invented vocabulary; the refused trap; unknown op reported as itself -------

def test_refused_disposition_in_op_slot_never_becomes_a_family():
    # op="refused" is a disposition, not an op; it is not applied, so it must not appear.
    log = _record_log()
    assert "refused" not in log.families


def test_unknown_op_is_reported_as_itself_not_swallowed():
    log = ApplyLog(entries=(_applied("create"), _applied("frobnicate")))
    assert log.families == {"create": 1, "frobnicate": 1}


def test_keys_are_the_ops_the_entries_carry_verbatim():
    # schema engine writes descriptor names; families echoes them, inventing nothing.
    log = _schema_log()
    assert set(log.families) == {"create_field", "delete_field"}


# ---- AC3: the totals reconcile on BOTH engines ------------------------------------------

def test_record_engine_totals_reconcile_to_len_applied():
    log = _record_log()
    assert sum(log.families.values()) == len(log.applied)


def test_schema_engine_shape_reads_as_45_adds_and_1_delete_not_46():
    log = _schema_log()
    assert log.families == {"create_field": 45, "delete_field": 1}
    assert sum(log.families.values()) == len(log.applied) == 46


# ---- AC4: the shared-model discipline holds — to_dict does not move ---------------------

def test_to_dict_is_unchanged_no_families_key():
    log = _record_log()
    blob = log.to_dict()
    assert set(blob) == {"entries", "halt", "table_halts"}
    assert "families" not in blob


def test_to_dict_byte_identical_to_the_pre_accessor_shape():
    # A record-engine log's serialized blob is exactly entries+halt+table_halts, in that order.
    log = ApplyLog(entries=(_applied("create"),))
    assert log.to_dict() == {
        "entries": [_applied("create").to_dict()],
        "halt": None,
        "table_halts": {},
    }
