"""LD-148 — THE INVARIANT: **no exception escapes ``apply()``**, and EVERY entry ends in a
typed, logged disposition (dogfood round-2 **T27**, the Blocker).

The bug: a batch write left the target **partially applied and the apply-log incomplete**
because a raw transport exception escaped the per-entry loop. With a
``RichCellWriteRequest.mention(open_id=<nonexistent>)`` placed after ≥1 other entry,
``apply()`` raised ``larkdocio.errors.LarkAPIError: Code 90204, Msg: id not found``
**uncaught, mid-batch**: the entries before the mention had landed, the ones after it never
ran, and **no disposition was recorded for any of them**. Every *modelled* failure (rich-cell
target, staleness, precondition, unknown tab) was already a typed refusal — but the client
call sat **outside** any try/except, so a transport exception aborted the loop and skipped the
log write for the failing entry AND the remainder.

What this module pins (the maintainer-blessed contract, `progress.md`):

* **AC1 — no exception escapes.** An exception-injection matrix over **every** entry kind
  (value / rich incl. mention / dropdown / structural insert·delete·append / merge·unmerge /
  tab add·copy·delete) × **failure position** (first / mid / last) × **exception class**
  (entry-scoped Lark code, rate limit, transport, config, unknown) — ``apply()`` **returns
  normally** every time.
* **AC2 — entry-scoped → typed refusal, batch CONTINUES** (the sheets per-entry doctrine).
* **AC3 — systemic → HALT**, and every remaining entry is logged ``not-attempted``.
* **AC4 — the apply-log completeness invariant as its own test**: the log is 1:1 with the
  plan, in order, under **every** failure mode.
* **AC5 — plan-time mention validation**: ``dry_run`` proves mention ``open_id``s exist in ONE
  read call; an id Lark **proves** nonexistent refuses ``unknown-mention`` at plan time, and a
  validation that cannot run is **DISCLOSED** in the plan (never silently skipped).
* **AC6 — the round-2 repro is a permanent test** (``test_t27_repro_*``).

The live evidence behind the mention-validation design (probed read-only 2026-07-28 with the
WRITE app, log_id ``20260728152453A52E092131CF9A78E884``): ``GET
/open-apis/contact/v3/users/batch`` answers a **nonexistent** ``open_id`` with code
``99992351`` and an ``error.field_violations[]`` entry naming that exact id — so
non-existence is **positively attributable**. A *real* id answers code ``0`` with
``items: []`` when the app lacks the contact *detail* scope — so "absent from items" is NOT
evidence of non-existence. The validation is therefore **falsification-based**: it refuses
only ids Lark proves do not exist.
"""
import ast
import inspect
import json
import random
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio.errors import (
    LarkAPIError,
    LarkConfigError,
    LarkDocIOError,
    LarkRateLimitError,
)
from larkdocio.sheets import ops as sheets_ops
from larkdocio.sheets.write_client import SheetsWriteClient
from larkdocio.sheets.write_range import parse_write_range
from larkdocio.sheets.write_apply import (
    ENTRY_SCOPED,
    FILE_LIFECYCLE_SEAMS,
    MENTION_VALIDATION_ACTIVE,
    MENTION_VALIDATION_NOT_APPLICABLE,
    MENTION_VALIDATION_UNAVAILABLE,
    READ_SEAMS,
    SYSTEMIC,
    WRITE_SEAMS,
    ApplyLog,
    ApplyLogEntry,
    WriteWatch,
    classify_apply_exception,
    AddTab,
    AppendDimension,
    AppendRowsWithValues,
    CopyTab,
    DeleteCols,
    DeleteRows,
    DeleteTab,
    DropdownRuleWriteRequest,
    FormulaWriteRequest,
    InsertColsAt,
    InsertRowsAt,
    MergeCells,
    Refusal,
    RichCellWriteRequest,
    UnmergeCells,
    ValueWriteRequest,
    apply,
    dry_run,
)
apply = reading_the_log(apply)

from test_sheets_destructive_safe_apply import FakeAllOpsGateway, _victim_tab

TOKEN = "shtxxxLD148"
SID = "555c22"

BAD_OPEN_ID = "ou_0000000000000000000000000000dead"
GOOD_OPEN_ID = "ou_examplebot0000000000000000000001"


def _api_90204():
    """The exact exception the round-2 session saw escape ``apply()``."""
    return LarkAPIError(
        "sheets values put failed: Code: 90204, Msg: id not found",
        code=90204, msg="id not found",
    )


class InjectingGateway(FakeAllOpsGateway):
    """``FakeAllOpsGateway`` + **exception injection on any client seam**.

    ``inject`` maps a client method name → a list of exceptions consumed one per call
    (``None`` = let the call through). This is the offline stand-in for a transport that
    answers a Lark error code / dies at the socket, and it is what makes "no exception
    escapes" provable without touching the network.
    """

    def __init__(self, *, inject=None, user_ids=None, no_validator=False, **kwargs):
        super().__init__(**kwargs)
        self.inject = {k: list(v) for k, v in (inject or {}).items()}
        self.calls = []               # every seam call, in order
        self.user_id_calls = []
        #: ``None`` ⇒ the lookup itself raises (unavailable); else the ids proven invalid.
        self.user_ids = user_ids
        self.no_validator = no_validator
        #: mirror ``FakeSheetGateway``: a value-write reply that omits ``revision``, forcing
        #: the engine's post-write ``metainfo`` fallback read (the seam a post-write failure
        #: is injected at).
        self.omit_put_revision = False

    def put_values(self, spreadsheet_token, a1_range, values):
        reply = super().put_values(spreadsheet_token, a1_range, values)
        return {"revision": None} if self.omit_put_revision else reply

    def _maybe_raise(self, name):
        self.calls.append(name)
        queue = self.inject.get(name)
        if not queue:
            return
        exc = queue.pop(0)
        if exc is not None:
            raise exc

    def __getattribute__(self, name):
        # Wrap every seam method the engine may call, so an injection can fire from any
        # position in an op leg (before its write, at its write, or on a post-write read).
        if name == "validate_user_ids" and object.__getattribute__(self, "no_validator"):
            # Model a client seam that simply has no mention-id check (the duck-typed
            # gateways the offline suites inject) — `getattr(client, ..., None)` → None.
            raise AttributeError("validate_user_ids")
        attr = object.__getattribute__(self, name)
        if name in _SEAM_METHODS and callable(attr):
            def wrapped(*a, **kw):
                self._maybe_raise(name)
                return attr(*a, **kw)
            return wrapped
        return attr

    def validate_user_ids(self, open_ids):
        self.user_id_calls.append(list(open_ids))
        if self.user_ids is None:
            raise LarkAPIError("contact lookup denied: Code: 99991672, Msg: no permission",
                               code=99991672, msg="no permission")
        invalid = [i for i in open_ids if i in self.user_ids]
        return {"checked": list(open_ids), "resolved": {}, "invalid": invalid}


#: Every duck-typed seam method the engine calls on a client (reads + writes).
_SEAM_METHODS = frozenset({
    "read_revision", "read_values", "read_sheet_geometry", "query_tabs",
    "put_values", "set_data_validation", "insert_dimension_range",
    "delete_dimension_range", "append_dimension", "append_values",
    "merge_cells", "unmerge_cells", "batch_update_sheets",
})


# =========================================================================== #
# AC6 — the round-2 T27 repro, encoded offline with an injected transport.      #
# =========================================================================== #

def _t27_batch():
    """The T27 shape: a bad mention sitting AFTER valid entries, with more entries after
    it — 2 before, the mention, 4 after (the report's exact arithmetic)."""
    return [
        ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["before-1"]]),
        ValueWriteRequest.for_a1(f"{SID}!A2:A2", [["before-2"]]),
        RichCellWriteRequest.mention(f"{SID}!A3:A3", BAD_OPEN_ID),
        ValueWriteRequest.for_a1(f"{SID}!A4:A4", [["after-1"]]),
        ValueWriteRequest.for_a1(f"{SID}!A5:A5", [["after-2"]]),
        ValueWriteRequest.for_a1(f"{SID}!A6:A6", [["after-3"]]),
        ValueWriteRequest.for_a1(f"{SID}!A7:A7", [["after-4"]]),
    ]


def _t27_gateway():
    """A sheet where the mention target's ``put_values`` answers ``90204 id not found``.

    ``read_values`` on every target succeeds (the plan's before-capture), and the mention's
    own write is the 3rd ``put_values`` call of the batch — the injection queue therefore
    lets the first two writes through and raises on the third.
    """
    return InjectingGateway(
        revision=7,
        values={f"{SID}!A{r}:A{r}": [[f"slot-{r}"]] for r in range(1, 8)},
        inject={"put_values": [None, None, _api_90204()]},
        user_ids=set(),      # the plan-time validation is intentionally blind here …
    )


def test_t27_repro_apply_does_not_raise_and_logs_every_entry():
    """**THE BLOCKER, encoded.** A 90204 on the mention's write must NOT escape ``apply()``,
    and the apply-log must carry a disposition for **all 7** input entries."""
    g = _t27_gateway()
    plan = dry_run(_t27_batch(), g, TOKEN)
    assert len(plan.entries) == 7

    log = apply(plan, g)   # pre-fix: raises LarkAPIError(90204) right here

    assert len(log.entries) == 7, "the apply-log must be 1:1 with the plan"
    assert [e.outcome for e in log.entries] == [
        "applied", "applied", "refused", "applied", "applied", "applied", "applied",
    ]


def test_t27_repro_the_bad_mention_is_a_typed_entry_scoped_refusal():
    """The 90204 becomes a typed per-entry refusal naming the code — not a crash."""
    g = _t27_gateway()
    log = apply(dry_run(_t27_batch(), g, TOKEN), g)

    bad = log.entries[2]
    assert bad.outcome == "refused"
    assert bad.refusal.reason == Refusal.API_ERROR == "api-error"
    assert "90204" in bad.refusal.detail
    assert "id not found" in bad.refusal.detail


def test_t27_repro_the_four_entries_after_the_bad_mention_still_apply():
    """The report's "4 after it never ran" becomes "4 after it applied" — the maintainer-blessed
    per-entry doctrine: an entry-scoped error refuses and the batch CONTINUES."""
    g = _t27_gateway()
    log = apply(dry_run(_t27_batch(), g, TOKEN), g)

    assert [e.outcome for e in log.entries[3:]] == ["applied"] * 4
    written = [a1 for (kind, a1) in g.writes if kind == "put"]
    assert written == [f"{SID}!A{r}:A{r}" for r in (1, 2, 4, 5, 6, 7)]
    assert f"{SID}!A3:A3" not in written, "the refused mention must not have written"


def test_t27_repro_the_log_alone_reconstructs_exactly_what_happened():
    """The reason T27 is a **Blocker**: a consumer must be able to reconstruct the batch's
    fate from the log alone. Serialize it and read the whole story back out of the JSON."""
    g = _t27_gateway()
    log = apply(dry_run(_t27_batch(), g, TOKEN), g)
    wire = json.loads(log.to_json())

    assert len(wire["entries"]) == 7
    assert wire["halt"] is None, "an entry-scoped error must not halt the batch"
    landed = [e["target"] for e in wire["entries"] if e["outcome"] == "applied"]
    assert landed == [f"{SID}!A{r}:A{r}" for r in (1, 2, 4, 5, 6, 7)]
    (failed,) = [e for e in wire["entries"] if e["outcome"] == "refused"]
    assert failed["target"] == f"{SID}!A3:A3"
    assert failed["refusal"]["reason"] == "api-error"
    assert failed["refusal"]["detail"], "a typed reason with no WHY is a riddle (LD-131)"


# =========================================================================== #
# The op-family matrix: one builder + its WRITE seam per entry kind.            #
#                                                                              #
# `seam` is the client method the family's apply leg WRITES through — injecting #
# there is injecting "the write failed"; injecting on a read seam is injecting  #
# "a guard/verification read failed". Both arms are exercised below.            #
# =========================================================================== #

_KINDS = {
    "value": (lambda: ValueWriteRequest.for_a1(f"{SID}!C1:C1", [["v"]]), "put_values"),
    # LD-149 — the FORMULA family writes through `put_values` like a value, but reads by
    # render mode on both sides of it, so its post-write verification legs are extra places an
    # exception can surface. The invariant must hold there too.
    "formula": (
        lambda: FormulaWriteRequest.for_a1(f"{SID}!C9:C9", "=SUM(A1:A2)"), "put_values"),
    "rich-hyperlink": (
        lambda: RichCellWriteRequest.hyperlink(f"{SID}!C2:C2", "https://x.example", text="X"),
        "put_values"),
    "rich-mention": (
        lambda: RichCellWriteRequest.mention(f"{SID}!C3:C3", GOOD_OPEN_ID), "put_values"),
    "rich-styled-runs": (
        lambda: RichCellWriteRequest.styled_runs(f"{SID}!C4:C4", [{"text": "x", "bold": True}]),
        "put_values"),
    "rich-multi-select": (
        lambda: RichCellWriteRequest.multi_select(f"{SID}!C5:C5", ["Red", "Green"]),
        "put_values"),
    "dropdown": (
        lambda: DropdownRuleWriteRequest.list_rule(f"{SID}!C6:C6", ["Red", "Green"]),
        "set_data_validation"),
    "structural-insert-rows": (
        lambda: InsertRowsAt(SID, before_row=2, count=1), "insert_dimension_range"),
    "structural-insert-cols": (
        lambda: InsertColsAt(SID, before_col=2, count=1), "insert_dimension_range"),
    "structural-delete-rows": (
        lambda: DeleteRows(SID, first=2, last=3), "delete_dimension_range"),
    "structural-delete-cols": (
        lambda: DeleteCols(SID, first=2, last=2), "delete_dimension_range"),
    "structural-append-dim": (
        lambda: AppendDimension(SID, "ROWS", 2), "append_dimension"),
    "structural-append-values": (
        lambda: AppendRowsWithValues(f"{SID}!A1:B1", [["x", "y"]]), "append_values"),
    "merge": (lambda: MergeCells(f"{SID}!A5:C5"), "merge_cells"),
    "unmerge": (lambda: UnmergeCells(f"{SID}!A5:C5"), "unmerge_cells"),
    "tab-add": (lambda: AddTab("New"), "batch_update_sheets"),
    "tab-copy": (lambda: CopyTab(SID, "Src copy"), "batch_update_sheets"),
    "tab-delete": (lambda: DeleteTab("dead99"), "batch_update_sheets"),
}

#: The exception classes an apply step can raise, with their expected classification. This
#: table IS the AC1/AC2/AC3 contract in one place.
_EXCEPTIONS = {
    "lark-code-90204": (_api_90204, Refusal.API_ERROR, "refused", False),
    "lark-code-90202": (
        lambda: LarkAPIError("wrong range: Code: 90202", code=90202, msg="wrong range"),
        Refusal.API_ERROR, "refused", False),
    "rate-limit": (
        lambda: LarkRateLimitError("rate limited: Code: 99991400", code=99991400,
                                   msg="too many requests"),
        Refusal.RATE_LIMITED, "refused", True),
    "transport": (
        lambda: LarkAPIError("PUT /open-apis/sheets/v2/... failed: <urlopen error timed out>"),
        Refusal.TRANSPORT_FAILURE, "failed", True),
    "config": (
        lambda: LarkConfigError("write range must not be empty"),
        Refusal.INVALID_REQUEST, "refused", False),
    "unknown-lark": (
        lambda: LarkDocIOError("unknown structural op 'nope'"),
        Refusal.UNEXPECTED_ERROR, "failed", True),
    "unknown-builtin": (
        lambda: KeyError("revision"), Refusal.UNEXPECTED_ERROR, "failed", True),
}


def _fresh_gateway(**kwargs):
    """A gateway with everything every family needs: a populated grid, a merge to dissolve,
    and a victim tab to delete/copy."""
    values = {f"{SID}!A{r}:A{r}": [[f"a{r}"]] for r in range(1, 8)}
    values.update({f"{SID}!C{r}:C{r}": [[f"c{r}"]] for r in range(1, 8)})
    values[f"{SID}!A5:C5"] = [["a5", "b5", "c5"]]
    values[f"{SID}!A1:B1"] = [["a1", "b1"]]
    values[f"{SID}!A1:C10"] = [["x"] * 3 for _ in range(10)]
    values[f"{SID}!A2:C3"] = [["x"] * 3 for _ in range(2)]
    values[f"{SID}!B1:C10"] = [["x"] * 2 for _ in range(10)]
    kwargs.setdefault("revision", 5)
    kwargs.setdefault("values", values)
    kwargs.setdefault("sheet_merges", {SID: []})
    kwargs.setdefault("tabs", [_victim_tab()])
    return InjectingGateway(**kwargs)


def _padded_batch(kind, position):
    """A 3-entry batch with ``kind`` at ``position`` and plain value writes padding it.

    Returns ``(requests, index, prior_same_seam)`` — ``prior_same_seam`` counts the padding
    writes that use the SAME client seam before the target, which is how the injection queue
    is positioned (the padding is always a ``put_values`` value write).
    """
    builder, seam = _KINDS[kind]
    pad = [ValueWriteRequest.for_a1(f"{SID}!A{r}:A{r}", [[f"pad-{r}"]]) for r in (6, 7)]
    index = {"first": 0, "mid": 1, "last": 2}[position]
    requests = pad[:index] + [builder()] + pad[index:]
    prior_same_seam = index if seam == "put_values" else 0
    return requests, index, prior_same_seam


def _run_matrix_case(kind, position, exc_name):
    """Drive ONE (kind × position × exception) cell and return ``(plan, log, gateway)``."""
    _builder, seam = _KINDS[kind]
    make_exc = _EXCEPTIONS[exc_name][0]
    requests, index, prior = _padded_batch(kind, position)
    g = _fresh_gateway(inject={seam: [None] * prior + [make_exc()]}, user_ids=set())
    plan = dry_run(requests, g, TOKEN)
    assert all(e.is_resolved for e in plan.entries), f"{kind}: plan should resolve cleanly"
    log = apply(plan, g)
    # ANTI-VACUITY: the injected exception must actually have fired. Without this a seam
    # renamed out from under the table would make the whole matrix pass on nothing.
    assert not g.inject[seam], (
        f"{kind}/{position}/{exc_name}: the injected exception on {seam!r} never fired — "
        f"seam calls were {g.calls}"
    )
    return plan, log, g, index


# =========================================================================== #
# AC1 — THE INVARIANT, structurally: EVERY entry kind × EVERY failure position  #
# × EVERY exception class → apply() RETURNS, and the log is complete.           #
# =========================================================================== #

@pytest.mark.parametrize("exc_name", sorted(_EXCEPTIONS))
@pytest.mark.parametrize("position", ["first", "mid", "last"])
@pytest.mark.parametrize("kind", sorted(_KINDS))
def test_no_exception_escapes_apply_for_any_kind_position_or_exception(kind, position, exc_name):
    """``apply()`` returns an :class:`ApplyLog` — never raises — for all
    18 kinds (LD-149 added `formula`) × 3 positions × 7 exception classes, and
    **every input entry** has a
    disposition in it (AC1 + AC4 together, since a complete log is what makes not-raising
    worth anything)."""
    plan, log, _g, index = _run_matrix_case(kind, position, exc_name)

    assert len(log.entries) == len(plan.entries) == 3
    unknown = [e.outcome for e in log.entries if e.outcome not in _OUTCOME_VOCAB]
    assert not unknown, f"{kind}/{position}/{exc_name}: unknown outcome(s) {unknown}"
    # A non-applied disposition ALWAYS names its typed reason — "it did not happen" with no
    # reason is the incomplete-log half of the T27 Blocker.
    assert all(e.refusal is not None for e in log.entries if e.outcome != "applied")


@pytest.mark.parametrize("exc_name", sorted(_EXCEPTIONS))
@pytest.mark.parametrize("position", ["first", "mid", "last"])
@pytest.mark.parametrize("kind", sorted(_KINDS))
def test_every_injected_exception_becomes_its_declared_typed_disposition(kind, position, exc_name):
    """The classification table is the contract: each injected exception class produces its
    declared refusal reason + apply-log outcome on the failing entry — never a propagated
    exception, never an untyped record."""
    _reason_maker, expected_reason, expected_outcome, _systemic = _EXCEPTIONS[exc_name]
    _plan, log, _g, index = _run_matrix_case(kind, position, exc_name)

    hit = log.entries[index]
    assert hit.outcome == expected_outcome, f"{kind}/{position}/{exc_name}: {hit.outcome}"
    assert hit.refusal is not None and hit.refusal.reason == expected_reason
    assert hit.refusal.detail, "every disposition carries a WHY (LD-131 mandatory detail)"


@pytest.mark.parametrize("exc_name", sorted(_EXCEPTIONS))
@pytest.mark.parametrize("position", ["first", "mid", "last"])
@pytest.mark.parametrize("kind", sorted(_KINDS))
def test_entry_scoped_continues_and_systemic_halts_for_every_kind(kind, position, exc_name):
    """AC2 + AC3 across the whole matrix: an entry-scoped failure leaves the OTHER entries
    processed normally; a systemic failure halts and logs every remaining entry
    ``not-attempted`` — with the halt itself disclosed on the log."""
    _maker, _reason, _outcome, systemic = _EXCEPTIONS[exc_name]
    _plan, log, _g, index = _run_matrix_case(kind, position, exc_name)
    after = log.entries[index + 1:]

    if systemic:
        assert log.halted, f"{kind}/{position}/{exc_name}: a systemic failure must halt"
        assert log.halt["index"] == index
        assert log.halt["not_attempted"] == len(after)
        assert [e.outcome for e in after] == ["not-attempted"] * len(after)
        assert all(e.refusal.reason == Refusal.NOT_ATTEMPTED for e in after)
    else:
        assert not log.halted, f"{kind}/{position}/{exc_name}: entry-scoped must NOT halt"
        assert [e.outcome for e in after] == ["applied"] * len(after)
    # The entries BEFORE the failure are unaffected in either case.
    assert [e.outcome for e in log.entries[:index]] == ["applied"] * index


#: The COMPLETE apply-log outcome vocabulary. A new outcome must be added here deliberately —
#: an undeclared one reddens the matrix above.
_OUTCOME_VOCAB = {
    "applied", "applied-unverified", "stale", "refused", "failed", "not-attempted",
}


def test_the_outcome_vocabulary_is_exactly_what_the_engine_can_emit():
    """The vocabulary this module asserts against is the same one the classification table
    can produce — so the matrix cannot be checking a stale list."""
    from larkdocio.sheets import disposition as D
    emitted = {d.outcome for d in (
        D._UNVERIFIED, D._RATE_LIMITED, D._API_ERROR, D._TRANSPORT,
        D._INVALID_REQUEST, D._UNEXPECTED,
    )}
    assert emitted <= _OUTCOME_VOCAB
    # …and every declared outcome resolves to a real ApplyLogEntry shape.
    for outcome in _OUTCOME_VOCAB:
        assert isinstance(outcome, str) and outcome


# =========================================================================== #
# AC1 (the structural half) — the boundary wraps the WHOLE per-entry step,       #
# proven by making the step itself raise, not just a client seam.                #
# =========================================================================== #

_EXOTIC = [
    RuntimeError("boom"),
    KeyError("revision"),
    TypeError("NoneType is not subscriptable"),
    ValueError("bad literal"),
    AttributeError("'NoneType' object has no attribute 'get'"),
    IndexError("list index out of range"),
    ZeroDivisionError("division by zero"),
    RecursionError("maximum recursion depth exceeded"),
    LarkDocIOError("unknown structural op 'nope'"),
    LarkConfigError("write range must not be None"),
    LarkAPIError("no code here"),
    LarkAPIError("coded", code=1310213, msg="permission denied"),
    LarkRateLimitError("throttled", code=99991400, msg="too many requests"),
]


@pytest.mark.parametrize("exc", _EXOTIC, ids=lambda e: type(e).__name__ + "-" + str(e)[:18])
def test_any_exception_from_the_per_entry_step_is_dispositioned_not_raised(monkeypatch, exc):
    """Patch ``_apply_one`` itself to raise — so the assertion is about the **boundary**, not
    about any particular op leg's internals. Whatever the step raises, ``apply()`` returns a
    complete log. This is the "no code path can raise past apply()" proof."""
    def _boom(entry, client, token, expected_revision):
        raise exc

    g = _fresh_gateway(user_ids=set())
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["x"]]),
                    ValueWriteRequest.for_a1(f"{SID}!A2:A2", [["y"]])], g, TOKEN)
    monkeypatch.setattr(sheets_ops, "_apply_one", _boom)

    log = apply(plan, g)
    assert len(log.entries) == 2
    assert log.entries[0].refusal is not None and log.entries[0].refusal.detail
    assert log.entries[0].outcome in _OUTCOME_VOCAB


def test_the_boundary_deliberately_does_not_swallow_baseexception(monkeypatch):
    """The carve-out, pinned. ``KeyboardInterrupt`` / ``SystemExit`` are the interpreter or
    the operator tearing the process down — swallowing one into a log entry would be a WORSE
    bug than the one LD-148 fixes, so the boundary catches ``Exception``, not
    ``BaseException``. Documented in ``sheets/disposition.py``; asserted here so it stays a
    decision rather than an accident."""
    def _interrupt(entry, client, token, expected_revision):
        raise KeyboardInterrupt()

    g = _fresh_gateway(user_ids=set())
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["x"]])], g, TOKEN)
    monkeypatch.setattr(sheets_ops, "_apply_one", _interrupt)

    with pytest.raises(KeyboardInterrupt):
        apply(plan, g)


def test_apply_wraps_its_per_entry_step_in_an_exception_boundary_ast():
    """A source-level guard: ``apply``'s per-entry loop body contains a ``try`` whose handler
    catches ``Exception``. A future refactor that moves the client call OUT of the boundary
    (exactly how T27 happened) reddens here even if no test happens to inject at that seam."""
    tree = ast.parse(Path(sheets_ops.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "apply")
    loops = [n for n in ast.walk(fn) if isinstance(n, ast.For)]
    assert loops, "apply() must iterate the plan's entries"
    handlers = [h for loop in loops for n in ast.walk(loop)
                if isinstance(n, ast.Try) for h in n.handlers]
    caught = {ast.unparse(h.type) for h in handlers if h.type is not None}
    assert "Exception" in caught, (
        f"apply()'s per-entry loop must wrap the step in `except Exception` — found {caught}"
    )
    # …and the dispatch it protects must be INSIDE that try (not merely nearby).
    protected = {
        ast.unparse(node)
        for loop in loops for n in ast.walk(loop) if isinstance(n, ast.Try)
        for stmt in n.body for node in ast.walk(stmt) if isinstance(node, ast.Call)
    }
    assert any("_apply_one" in call for call in protected), (
        f"the per-entry apply step must sit inside the boundary; guarded calls: {protected}"
    )


# =========================================================================== #
# AC3 — the systemic arm in detail: halt semantics + the amplifier's cases.      #
# =========================================================================== #

def test_systemic_error_after_an_entry_scoped_refusal_halts_and_logs_the_rest():
    """The amplifier's case: entry 0 refuses entry-scoped (batch continues), entry 1 hits a
    rate limit (batch halts), entries 2-3 are logged ``not-attempted``."""
    reqs = [ValueWriteRequest.for_a1(f"{SID}!A{r}:A{r}", [[f"v{r}"]]) for r in (1, 2, 3, 4)]
    g = _fresh_gateway(
        user_ids=set(),
        inject={"put_values": [
            _api_90204(),
            LarkRateLimitError("throttled", code=99991400, msg="too many requests"),
        ]},
    )
    log = apply(dry_run(reqs, g, TOKEN), g)

    assert [e.outcome for e in log.entries] == [
        "refused", "refused", "not-attempted", "not-attempted"]
    assert log.entries[0].refusal.reason == Refusal.API_ERROR
    assert log.entries[1].refusal.reason == Refusal.RATE_LIMITED
    assert log.halt["index"] == 1 and log.halt["reason"] == Refusal.RATE_LIMITED
    assert log.halt["not_attempted"] == 2
    assert len(log.not_attempted) == 2
    assert g.writes == [], "neither entry landed, so nothing should be recorded as written"


def test_two_entry_scoped_failures_both_refuse_and_the_batch_still_finishes():
    """The amplifier's "where TWO fail" case — both refuse, everything else applies, and the
    batch does not halt."""
    reqs = [ValueWriteRequest.for_a1(f"{SID}!A{r}:A{r}", [[f"v{r}"]]) for r in (1, 2, 3, 4)]
    g = _fresh_gateway(
        user_ids=set(),
        inject={"put_values": [_api_90204(), None, _api_90204(), None]},
    )
    log = apply(dry_run(reqs, g, TOKEN), g)

    assert [e.outcome for e in log.entries] == ["refused", "applied", "refused", "applied"]
    assert not log.halted
    assert [a1 for (k, a1) in g.writes if k == "put"] == [f"{SID}!A2:A2", f"{SID}!A4:A4"]


def test_not_attempted_entries_name_where_and_why_the_batch_halted():
    """A ``not-attempted`` record is only useful if it says what stopped the batch."""
    reqs = [ValueWriteRequest.for_a1(f"{SID}!A{r}:A{r}", [[f"v{r}"]]) for r in (1, 2, 3)]
    g = _fresh_gateway(user_ids=set(), inject={"put_values": [
        LarkAPIError("PUT failed: <urlopen error timed out>")]})
    log = apply(dry_run(reqs, g, TOKEN), g)

    assert log.entries[0].outcome == "failed", "a transport failure is INDETERMINATE"
    assert log.entries[0].refusal.reason == Refusal.TRANSPORT_FAILURE
    assert "INDETERMINATE" in log.entries[0].refusal.detail
    for tail in log.entries[1:]:
        assert tail.outcome == "not-attempted"
        assert "halted at entry #0" in tail.refusal.detail
        assert Refusal.TRANSPORT_FAILURE in tail.refusal.detail
        assert "nothing on the spreadsheet changed" in tail.refusal.detail
    assert log.indeterminate == (log.entries[0],)


def test_dry_run_read_failures_are_left_to_raise():
    """**The deliberate scope boundary.** ``dry_run`` performs ZERO writes, so a failed
    plan-time read is unambiguous — no plan, no writes, no partial state, nothing to
    disclose — and it keeps raising. The invariant LD-148 ships is about ``apply``, where a
    partially-applied batch with no record was the actual harm. (The one plan-time call that
    is guarded is the @mention **check**: a failed check must never fail the plan.)"""
    g = _fresh_gateway(user_ids=set(), inject={"read_revision": [_api_90204()]})
    with pytest.raises(LarkAPIError):
        dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["x"]])], g, TOKEN)
    assert g.writes == []


def test_a_post_write_failure_is_applied_unverified_not_a_refusal():
    """The honesty case the write-watch exists for: the ``put_values`` **returned** (the value
    IS on the sheet) and the post-write ``revision`` read-back then died. Reporting that as a
    refusal would be a log that lies about a real change."""
    reqs = [ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["v1"]]),
            ValueWriteRequest.for_a1(f"{SID}!A2:A2", [["v2"]])]
    g = _fresh_gateway(user_ids=set())
    g.omit_put_revision = True   # forces the metainfo fallback read after the write
    # read_revision calls: 1 = dry_run anchor, 2 = pre-write compare-and-swap, 3 = post-write.
    g.inject = {"read_revision": [None, None, _api_90204()]}

    log = apply(dry_run(reqs, g, TOKEN), g)

    hit = log.entries[0]
    assert hit.outcome == "applied-unverified"
    assert hit.is_applied, "the change IS on the sheet — is_applied must say so"
    assert not hit.is_verified
    assert hit.revision is None, "the post-write anchor is exactly what could not be read"
    assert hit.refusal.reason == Refusal.UNVERIFIED_WRITE
    assert "IS on the spreadsheet" in hit.refusal.detail
    assert ("put", f"{SID}!A1:A1") in g.writes, "the write really did land"
    # A verification gap makes the anchor untrustworthy → HALT.
    assert log.halted and log.halt["reason"] == Refusal.UNVERIFIED_WRITE
    assert log.halt["landed"] == "yes"
    assert log.entries[1].outcome == "not-attempted"
    assert log.applied == (hit,), "applied must include the unverified-but-landed write"


def test_a_failed_post_write_geometry_reread_is_also_applied_unverified():
    """The structural twin: the row insert **returned**, and the MANDATORY post-write geometry
    re-read (D2/D3) then failed. The row is on the sheet; the log says applied-unverified."""
    g = _fresh_gateway(user_ids=set())
    plan = dry_run([InsertRowsAt(SID, before_row=2, count=1),
                    ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["x"]])], g, TOKEN)
    # geometry reads: 1 = pre-write baseline, 2 = the mandatory post-write re-read.
    g.inject = {"read_sheet_geometry": [None, LarkAPIError("boom", code=1310213, msg="denied")]}

    log = apply(plan, g)
    hit = log.entries[0]
    assert hit.outcome == "applied-unverified" and hit.is_applied
    assert hit.refusal.reason == Refusal.UNVERIFIED_WRITE
    assert "insert_dimension_range" in hit.refusal.detail, "the detail names the seam that ran"
    assert ("insert", SID) in g.writes
    assert log.halted and log.entries[1].outcome == "not-attempted"


def test_omit_put_revision_alone_still_applies_cleanly_control():
    """The control for the test above: with no injection the same metainfo-fallback path is a
    plain ``applied`` — so the ``applied-unverified`` outcome is caused by the failure, not by
    the fallback."""
    g = _fresh_gateway(user_ids=set())
    g.omit_put_revision = True
    log = apply(dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["v1"]])], g, TOKEN), g)
    assert log.entries[0].outcome == "applied" and log.entries[0].revision is not None


# =========================================================================== #
# AC4 — THE APPLY-LOG COMPLETENESS INVARIANT, as its own test.                  #
# =========================================================================== #

def _random_batch(rng, n):
    """A randomized batch drawn from every entry kind (order and mix vary)."""
    names = sorted(_KINDS)
    return [_KINDS[rng.choice(names)][0]() for _ in range(n)]


@pytest.mark.parametrize("seed", list(range(24)))
def test_apply_log_is_1to1_with_the_plan_under_randomized_failure_modes(seed):
    """**The completeness invariant.** For a randomized batch with a randomized injection on
    a randomized seam: ``len(log.entries) == len(plan.entries)``, in order, with a
    disposition on every entry — no matter which mode fired, how early, or how systemic.

    This is the property the whole undo / disclosure story rests on, so it is asserted as a
    property over random inputs rather than only on hand-picked shapes.
    """
    rng = random.Random(seed)
    n = rng.randint(1, 6)
    requests = _random_batch(rng, n)
    seam = rng.choice(sorted(_SEAM_METHODS))
    exc_name = rng.choice(sorted(_EXCEPTIONS))
    depth = rng.randint(0, 3)
    g = _fresh_gateway(user_ids=set())
    plan = dry_run(requests, g, TOKEN)
    # The injection is armed AFTER planning on purpose: `dry_run` performs ZERO writes, so a
    # failed plan-time read is unambiguous (no plan, no writes, nothing to disclose) and is
    # deliberately left to raise — see `test_dry_run_read_failures_are_left_to_raise`. The
    # invariant this property protects is about `apply`, where partial state is possible.
    g.inject = {seam: [None] * depth + [_EXCEPTIONS[exc_name][0]()]}
    log = apply(plan, g)

    assert len(log.entries) == len(plan.entries) == n, (
        f"seed {seed}: log/plan length parity broken ({len(log.entries)} vs {n})"
    )
    for i, (planned, logged) in enumerate(zip(plan.entries, log.entries)):
        assert logged.outcome in _OUTCOME_VOCAB, f"seed {seed} entry {i}: {logged.outcome}"
        if logged.outcome != "applied":
            assert logged.refusal is not None and logged.refusal.detail, (
                f"seed {seed} entry {i}: a non-applied disposition with no WHY")
        # Identity parity: a logged entry addresses the SAME target as its plan entry.
        assert (logged.target is None) == (planned.target is None)
        if planned.target is not None:
            assert logged.target.a1() == planned.target.a1()


def test_apply_log_completeness_holds_when_the_very_first_entry_dies_systemically():
    """The extreme shape: the batch dies on entry 0, so **every** disposition in the log is
    something other than a write result — and there are still exactly N of them."""
    reqs = [ValueWriteRequest.for_a1(f"{SID}!A{r}:A{r}", [[f"v{r}"]]) for r in range(1, 8)]
    g = _fresh_gateway(user_ids=set(), inject={"read_revision": [None, KeyError("boom")]})
    log = apply(dry_run(reqs, g, TOKEN), g)

    assert len(log.entries) == 7
    assert log.entries[0].outcome == "failed"
    assert [e.outcome for e in log.entries[1:]] == ["not-attempted"] * 6
    assert g.writes == []


def test_a_plan_time_refusal_and_an_apply_time_disposition_coexist_in_one_log():
    """A refusal decided at ``dry_run`` and a disposition decided at ``apply`` are both in the
    log, each with its own reason — the log is the single record of both phases."""
    reqs = [
        ValueWriteRequest.for_a1(f"{SID}!A1:A1", [[{"type": "url", "text": "x"}]]),  # rich → refused at plan
        ValueWriteRequest.for_a1(f"{SID}!A2:A2", [["v2"]]),
    ]
    g = _fresh_gateway(user_ids=set(), inject={"put_values": [_api_90204()]})
    log = apply(dry_run(reqs, g, TOKEN), g)

    assert [e.outcome for e in log.entries] == ["refused", "refused"]
    assert log.entries[0].refusal.reason == Refusal.RICH_CELL_TARGET
    assert log.entries[1].refusal.reason == Refusal.API_ERROR


# =========================================================================== #
# AC5 — PLAN-TIME MENTION VALIDATION (the 90204 class refuses at dry-run).       #
# =========================================================================== #

def test_a_bad_mention_open_id_refuses_at_dry_run_naming_the_id():
    g = _fresh_gateway(user_ids={BAD_OPEN_ID})
    plan = dry_run([
        ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["ok"]]),
        RichCellWriteRequest.mention(f"{SID}!A2:A2", BAD_OPEN_ID),
    ], g, TOKEN)

    assert plan.mention_validation == "active"
    bad = plan.entries[1]
    assert not bad.is_resolved
    assert bad.refusal.reason == Refusal.UNKNOWN_MENTION == "unknown-mention"
    assert BAD_OPEN_ID in bad.refusal.detail
    assert plan.mention_validation_ids["invalid"] == [BAD_OPEN_ID]
    # …and it never reaches the transport.
    log = apply(plan, g)
    assert log.entries[1].refusal.reason == Refusal.UNKNOWN_MENTION
    assert [a1 for (k, a1) in g.writes if k == "put"] == [f"{SID}!A1:A1"]


def test_a_good_mention_open_id_passes_dry_run_and_applies():
    g = _fresh_gateway(user_ids=set())
    plan = dry_run([RichCellWriteRequest.mention(f"{SID}!A2:A2", GOOD_OPEN_ID)], g, TOKEN)

    assert plan.mention_validation == "active"
    assert plan.entries[0].is_resolved
    assert plan.mention_validation_ids["checked"] == [GOOD_OPEN_ID]
    assert plan.mention_validation_ids["invalid"] == []
    assert apply(plan, g).entries[0].outcome == "applied"


def test_a_real_id_that_returns_no_display_name_is_not_treated_as_nonexistent():
    """The live-probed trap: an app without the contact DETAIL scope gets ``code 0`` +
    ``items: []`` for a **real** id. "No name" must never be read as "no such user"."""
    g = _fresh_gateway(user_ids=set())     # resolved is empty, invalid is empty
    plan = dry_run([RichCellWriteRequest.mention(f"{SID}!A2:A2", GOOD_OPEN_ID)], g, TOKEN)
    assert plan.mention_validation_ids["resolved"] == {}
    assert plan.entries[0].is_resolved, "an unnamed but existing id must NOT be refused"


def test_mention_validation_spends_exactly_one_read_call_for_the_whole_batch():
    g = _fresh_gateway(user_ids=set())
    dry_run([
        RichCellWriteRequest.mention(f"{SID}!A1:A1", GOOD_OPEN_ID),
        RichCellWriteRequest.mention(f"{SID}!A2:A2", GOOD_OPEN_ID),
        RichCellWriteRequest.mention(f"{SID}!A3:A3", BAD_OPEN_ID),
        ValueWriteRequest.for_a1(f"{SID}!A4:A4", [["plain"]]),
    ], g, TOKEN)
    assert len(g.user_id_calls) == 1, f"expected ONE lookup, got {g.user_id_calls}"
    assert g.user_id_calls[0] == [GOOD_OPEN_ID, BAD_OPEN_ID], "distinct ids, first-seen order"


def test_a_batch_with_no_mention_spends_no_lookup_and_says_not_applicable():
    g = _fresh_gateway(user_ids=set())
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["x"]])], g, TOKEN)
    assert g.user_id_calls == []
    assert plan.mention_validation == "not-applicable"
    assert "no read call was spent" in plan.mention_validation_detail


def test_validation_unavailable_is_disclosed_when_the_lookup_raises():
    """AC5's graceful half — the never-silent pattern. A denied / unreachable lookup must be
    DISCLOSED in the plan, and must NOT refuse the entry (that would break legitimate writes)
    and must NOT silently pass as validated."""
    g = _fresh_gateway(user_ids=None)      # the validator raises 99991672 no-permission
    plan = dry_run([RichCellWriteRequest.mention(f"{SID}!A2:A2", BAD_OPEN_ID)], g, TOKEN)

    assert plan.mention_validation == "unavailable"
    assert "UNVERIFIED" in plan.mention_validation_detail
    assert "99991672" in plan.mention_validation_detail, "the plan must carry Lark's own WHY"
    assert plan.entries[0].is_resolved, "an unavailable CHECK must not refuse the write"


def test_validation_unavailable_is_disclosed_when_the_client_has_no_validator():
    g = _fresh_gateway(no_validator=True)
    plan = dry_run([RichCellWriteRequest.mention(f"{SID}!A2:A2", BAD_OPEN_ID)], g, TOKEN)

    assert plan.mention_validation == "unavailable"
    assert "validate_user_ids" in plan.mention_validation_detail
    assert plan.entries[0].is_resolved


def test_an_unvalidated_bad_mention_still_cannot_crash_apply():
    """The two halves meet: when validation is unavailable the id reaches apply — and there
    it is a typed per-entry refusal, never the T27 crash."""
    g = _fresh_gateway(no_validator=True, inject={"put_values": [_api_90204(), None]})
    log = apply(dry_run([
        RichCellWriteRequest.mention(f"{SID}!A1:A1", BAD_OPEN_ID),
        ValueWriteRequest.for_a1(f"{SID}!A2:A2", [["after"]]),
    ], g, TOKEN), g)

    assert [e.outcome for e in log.entries] == ["refused", "applied"]
    assert log.entries[0].refusal.reason == Refusal.API_ERROR


def test_the_plan_json_always_carries_the_mention_validation_disclosure():
    """A consumer reading only the serialized plan can tell a validated batch from an
    unvalidated one — the same never-silent contract as ``revision_guard``."""
    for gateway, expected in (
        (_fresh_gateway(user_ids=set()), "active"),
        (_fresh_gateway(user_ids=None), "unavailable"),
        (_fresh_gateway(no_validator=True), "unavailable"),
    ):
        plan = dry_run(
            [RichCellWriteRequest.mention(f"{SID}!A2:A2", GOOD_OPEN_ID)], gateway, TOKEN)
        wire = json.loads(plan.to_json())
        assert wire["mention_validation"] == expected
        assert wire["mention_validation_detail"]
        assert set(wire["mention_validation_ids"]) == {"checked", "resolved", "invalid"}
        assert json.loads(json.dumps(wire)) == wire


def test_a_mention_riding_inside_a_styled_run_array_is_also_validated():
    """The check reads the mention wire shape out of the payload, so it is family-agnostic —
    not keyed on ``RichCellWriteRequest.mention`` being the request type."""
    cell = [{"type": "text", "text": "cc "},
            {"type": "mention", "text": BAD_OPEN_ID, "textType": "openId"}]
    g = _fresh_gateway(user_ids={BAD_OPEN_ID})
    plan = dry_run([RichCellWriteRequest(
        parse_write_range(f"{SID}!A2:A2"), cell, RichCellWriteRequest.STYLED_RUNS)], g, TOKEN)

    assert plan.mention_validation_ids["checked"] == [BAD_OPEN_ID]
    assert plan.entries[0].refusal.reason == Refusal.UNKNOWN_MENTION


def test_a_mention_in_an_append_rows_payload_is_also_validated():
    """Same, for a **structural** append whose rows carry a mention — the entry has no A1
    target, and the refusal still keeps its structural descriptor."""
    rows = [[{"type": "mention", "text": BAD_OPEN_ID, "textType": "openId"}, "x"]]
    g = _fresh_gateway(user_ids={BAD_OPEN_ID})
    plan = dry_run([AppendRowsWithValues(f"{SID}!A1:B1", rows)], g, TOKEN)

    assert plan.mention_validation_ids["invalid"] == [BAD_OPEN_ID]
    entry = plan.entries[0]
    assert entry.refusal.reason == Refusal.UNKNOWN_MENTION
    assert entry.structural is not None, "a refused structural entry keeps its descriptor"
    assert apply(plan, g).entries[0].refusal.reason == Refusal.UNKNOWN_MENTION


def test_a_plan_that_carries_no_validation_record_cannot_look_validated():
    """The structural half of AC5: the disclosure is DERIVED in ``Plan.__init__``, so even a
    plan built by a future preview leg that forgets to validate states the truth."""
    from larkdocio.sheets.plan import _PLAN_TOKEN, Plan as RawPlan
    mention_entry = dry_run(
        [RichCellWriteRequest.mention(f"{SID}!A2:A2", GOOD_OPEN_ID)],
        _fresh_gateway(no_validator=True), TOKEN).entries[0]

    forgetful = RawPlan([mention_entry], revision=3, spreadsheet_token=TOKEN,
                        _token=_PLAN_TOKEN)
    assert forgetful.mention_validation == "unavailable"
    assert "UNVERIFIED" in forgetful.mention_validation_detail

    plain = RawPlan([], revision=3, spreadsheet_token=TOKEN, _token=_PLAN_TOKEN)
    assert plain.mention_validation == "not-applicable"


# =========================================================================== #
# Structural guards — the write/read seam split must stay exhaustive.            #
# =========================================================================== #

def _public_client_methods() -> set:
    public = set()
    for name, member in inspect.getmembers(SheetsWriteClient):
        if name.startswith("_"):
            continue
        if isinstance(SheetsWriteClient.__dict__.get(name), (classmethod, staticmethod)):
            continue
        if inspect.isfunction(member) or inspect.ismethod(member):
            public.add(name)
    return public


def test_every_public_write_client_method_is_declared_read_or_write():
    """The write-watch keys on :data:`WRITE_SEAMS`. A new write op that forgets to register
    there would make a disposition claim "nothing landed" about a call that landed something —
    the exact class of lie LD-148 exists to prevent. So the split is pinned against the real
    client surface, bidirectionally.

    LD-176 adds a THIRD category rather than widening the first: the file-lifecycle pair
    (create/delete the whole spreadsheet) mutates the FILE, not a range inside it, and the
    apply engine never calls either — so declaring them writes would put a seam the
    write-watch keys on into a set the engine cannot reach, which reads as a claim that is
    not true of them."""
    public = _public_client_methods()

    declared = WRITE_SEAMS | READ_SEAMS | FILE_LIFECYCLE_SEAMS
    assert not (public - declared), (
        f"SheetsWriteClient methods {sorted(public - declared)} are in none of WRITE_SEAMS / "
        f"READ_SEAMS / FILE_LIFECYCLE_SEAMS — declare them in "
        f"larkdocio/sheets/disposition.py so the write-watch can tell a landed change from "
        f"a failed one."
    )
    assert not (declared - public), (
        f"disposition.py declares seams {sorted(declared - public)} that are not methods on "
        f"SheetsWriteClient — remove them or fix the name."
    )
    assert not (WRITE_SEAMS & READ_SEAMS), "a seam cannot be both a read and a write"


def test_the_file_lifecycle_seams_are_their_own_category():
    """LD-176: the lifecycle pair is declared, disjoint from both engine seam sets, and it
    is exactly the client's own ``LIFECYCLE_OPS`` — one list, not two.

    Disjointness is the load-bearing half. ``WRITE_SEAMS`` is what the per-entry write-watch
    proxies to decide whether a plan entry's change landed; a workbook create/delete is
    never a plan entry, so listing it there would make the seam split describe something the
    engine does not do."""
    from larkdocio.sheets.write_client import LIFECYCLE_OPS

    assert FILE_LIFECYCLE_SEAMS == set(LIFECYCLE_OPS) == {
        "create_spreadsheet", "delete_spreadsheet"}
    assert not (FILE_LIFECYCLE_SEAMS & WRITE_SEAMS)
    assert not (FILE_LIFECYCLE_SEAMS & READ_SEAMS)
    assert FILE_LIFECYCLE_SEAMS <= _public_client_methods()


def test_the_engine_never_calls_a_file_lifecycle_seam():
    """LD-176: run every op family through the engine and assert it touches NEITHER
    lifecycle call. A plan-gated write must not be able to create or trash a workbook —
    that is a caller's explicit act, never a side effect of applying a plan."""
    g = _fresh_gateway(user_ids=set())
    plan = dry_run([builder() for builder, _seam in _KINDS.values()], g, TOKEN)
    apply(plan, g)
    assert not (set(g.calls) & FILE_LIFECYCLE_SEAMS), (
        f"the engine reached a file-lifecycle seam: "
        f"{sorted(set(g.calls) & FILE_LIFECYCLE_SEAMS)}")


def test_the_engine_only_ever_calls_declared_seams():
    """The other direction: run every op family through the engine and assert every client
    method it touched is a declared seam (so the split is not merely plausible)."""
    g = _fresh_gateway(user_ids=set())
    plan = dry_run([builder() for builder, _seam in _KINDS.values()], g, TOKEN)
    apply(plan, g)
    touched = set(g.calls)
    assert touched, "the matrix should have exercised the client"
    assert touched <= (WRITE_SEAMS | READ_SEAMS), (
        f"the engine called undeclared client method(s) {sorted(touched - (WRITE_SEAMS | READ_SEAMS))}"
    )


def test_the_write_watch_distinguishes_issued_from_completed():
    """The write-watch's own unit: a write that RAISED did not land; one that RETURNED did."""
    g = _fresh_gateway(user_ids=set())
    ok = WriteWatch(g)
    ok.put_values(TOKEN, f"{SID}!A1:A1", [["x"]])
    assert ok.wrote and ok.issued == ("put_values",) and ok.completed == ("put_values",)

    boom = WriteWatch(_fresh_gateway(user_ids=set(), inject={"put_values": [_api_90204()]}))
    with pytest.raises(LarkAPIError):
        boom.put_values(TOKEN, f"{SID}!A1:A1", [["x"]])
    assert boom.issued == ("put_values",)
    assert boom.completed == () and not boom.wrote

    # A READ never marks the watch as having written.
    reader = WriteWatch(_fresh_gateway(user_ids=set()))
    reader.read_revision(TOKEN)
    assert not reader.wrote


def test_the_write_watch_forwards_duck_typed_absence():
    """``getattr(client, "query_tabs", None)`` must still answer ``None`` through the proxy —
    the engine's optional-seam probing depends on it."""
    class Minimal:
        def read_revision(self, spreadsheet_token):
            return 1

    watch = WriteWatch(Minimal())
    assert getattr(watch, "query_tabs", None) is None
    assert callable(getattr(watch, "read_revision", None))


@pytest.mark.parametrize("exc,expected_scope,expected_reason", [
    (LarkRateLimitError("x", code=99991400), SYSTEMIC, Refusal.RATE_LIMITED),
    (LarkAPIError("x", code=90204), ENTRY_SCOPED, Refusal.API_ERROR),
    (LarkAPIError("x"), SYSTEMIC, Refusal.TRANSPORT_FAILURE),
    (LarkConfigError("x"), ENTRY_SCOPED, Refusal.INVALID_REQUEST),
    (RuntimeError("x"), SYSTEMIC, Refusal.UNEXPECTED_ERROR),
])
def test_classification_table_is_the_documented_scope_split(exc, expected_scope, expected_reason):
    d = classify_apply_exception(exc, wrote=False)
    assert d.scope == expected_scope and d.reason == expected_reason
    assert d.continues == (expected_scope == ENTRY_SCOPED)
    assert d.halts == (expected_scope == SYSTEMIC)


@pytest.mark.parametrize("exc", [
    LarkAPIError("x", code=90204), LarkRateLimitError("x", code=99991400),
    LarkAPIError("x"), LarkConfigError("x"), RuntimeError("x"),
])
def test_a_completed_write_overrides_every_classification(exc):
    """``wrote=True`` wins over the exception's own class — once the change is on the sheet the
    only truthful record is ``applied-unverified``, and the batch must halt because the
    compare-and-swap anchor is unknown."""
    d = classify_apply_exception(exc, wrote=True)
    assert d.reason == Refusal.UNVERIFIED_WRITE
    assert d.outcome == "applied-unverified" and d.landed == "yes" and d.halts


def test_every_disposition_reason_has_actionable_wording():
    """Each disposition's detail answers the three questions a consumer has: what failed,
    whether the sheet changed, and what the batch did."""
    from larkdocio.sheets import disposition as D
    for disposition in (D._UNVERIFIED, D._RATE_LIMITED, D._API_ERROR, D._TRANSPORT,
                        D._INVALID_REQUEST, D._UNEXPECTED):
        refusal = D.disposition_refusal(
            disposition, LarkAPIError("boom", code=1, msg="m"),
            where="value on s1!A1:A1", wrote_seams=("put_values",))
        assert refusal.reason == disposition.reason
        assert len(refusal.detail) > 60, refusal.detail
        assert "boom" in refusal.detail
        assert any(w in refusal.detail for w in
                   ("CONTINUED", "HALTED")), f"no batch-fate wording: {refusal.detail}"


def test_a_disposition_detail_survives_an_exception_whose_str_explodes():
    """Defense in depth on the one path whose whole job is not raising."""
    from larkdocio.sheets import disposition as D

    class Nasty(Exception):
        def __str__(self):
            raise ValueError("cannot render me")

    refusal = D.disposition_refusal(D._UNEXPECTED, Nasty(), where="value on s1!A1:A1")
    assert "unprintable Nasty" in refusal.detail


def test_a_nasty_exception_from_the_apply_step_still_yields_a_complete_log(monkeypatch):
    """End to end for the same hardening: an exception that cannot even be stringified is
    still dispositioned rather than escaping."""
    class Nasty(Exception):
        def __str__(self):
            raise ValueError("cannot render me")

    def _boom(entry, client, token, expected_revision):
        raise Nasty()

    g = _fresh_gateway(user_ids=set())
    plan = dry_run([ValueWriteRequest.for_a1(f"{SID}!A1:A1", [["x"]])], g, TOKEN)
    monkeypatch.setattr(sheets_ops, "_apply_one", _boom)

    log = apply(plan, g)
    assert log.entries[0].outcome == "failed"
    assert "unprintable Nasty" in log.entries[0].refusal.detail


# =========================================================================== #
# The vocabulary itself — LD-147 (e) quotes these names VERBATIM.                #
# =========================================================================== #

def test_the_shipped_disposition_vocabulary_is_exactly_these_names():
    """The names LD-147 documents. Pinned so a rename is a deliberate, visible act that
    reddens here (and so the docs cannot quietly drift from the code)."""
    assert Refusal.UNKNOWN_MENTION == "unknown-mention"
    assert Refusal.API_ERROR == "api-error"
    assert Refusal.INVALID_REQUEST == "invalid-request"
    assert Refusal.RATE_LIMITED == "rate-limited"
    assert Refusal.TRANSPORT_FAILURE == "transport-failure"
    assert Refusal.UNEXPECTED_ERROR == "unexpected-error"
    assert Refusal.NOT_ATTEMPTED == "not-attempted"
    assert Refusal.UNVERIFIED_WRITE == "unverified-write"
    assert ENTRY_SCOPED == "entry-scoped" and SYSTEMIC == "systemic"
    assert MENTION_VALIDATION_ACTIVE == "active"
    assert MENTION_VALIDATION_UNAVAILABLE == "unavailable"
    assert MENTION_VALIDATION_NOT_APPLICABLE == "not-applicable"


def test_every_new_refusal_reason_is_reachable_through_a_factory_with_a_detail():
    """No new reason may be constructible without a WHY (the LD-131 discipline extended)."""
    factories = {
        Refusal.UNKNOWN_MENTION: lambda: Refusal.unknown_mention(open_id=BAD_OPEN_ID),
        Refusal.API_ERROR: lambda: Refusal.api_error("d"),
        Refusal.INVALID_REQUEST: lambda: Refusal.invalid_request("d"),
        Refusal.RATE_LIMITED: lambda: Refusal.rate_limited("d"),
        Refusal.TRANSPORT_FAILURE: lambda: Refusal.transport_failure("d"),
        Refusal.UNEXPECTED_ERROR: lambda: Refusal.unexpected_error("d"),
        Refusal.UNVERIFIED_WRITE: lambda: Refusal.unverified_write("d"),
        Refusal.NOT_ATTEMPTED: lambda: Refusal.not_attempted(halted_at=0, reason="x"),
    }
    for reason, make in factories.items():
        refusal = make()
        assert refusal.reason == reason
        assert refusal.detail, f"{reason} built with no detail"
        assert Refusal.from_dict(refusal.to_dict()) == refusal


def test_apply_log_json_round_trips_every_new_outcome():
    entries = (
        ApplyLogEntry.failed(refusal=Refusal.transport_failure("d")),
        ApplyLogEntry.not_attempted(refusal=Refusal.not_attempted(halted_at=1, reason="r")),
        ApplyLogEntry.applied_unverified(refusal=Refusal.unverified_write("d")),
    )
    log = ApplyLog(entries=entries, halt={"index": 1, "reason": "transport-failure",
                                          "detail": "d", "landed": "indeterminate",
                                          "not_attempted": 1})
    wire = json.loads(log.to_json())
    assert json.loads(json.dumps(wire)) == wire
    assert [e["outcome"] for e in wire["entries"]] == [
        "failed", "not-attempted", "applied-unverified"]
    assert wire["halt"]["reason"] == "transport-failure"
    for original, d in zip(entries, wire["entries"]):
        assert ApplyLogEntry.from_dict(d) == original
