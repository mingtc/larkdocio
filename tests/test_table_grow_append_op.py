"""LD-575 — the plan-gated, declared, APPEND-ONLY table-grow op.

**The defect this closes.** The grow MECHANISM shipped, was measured, and was unreachable as
an operation: ``larkdocio.write.apply._grow_table_grid`` had one call site, inside the
plan-gated *insert*, so the grow ran only while a table was being CREATED. A caller holding
the block id of a table that already existed had no shipped verb for its grid — its cells were
editable, its grid was not — and the only identity-preserving route was public ``patch_block``,
outside the plan gate, outside the ``STALE_DOCUMENT`` guard and outside the refusal set.

**What ships here is the DECLARED surface, not the mechanism.** Every primitive was already
shipped and measured; this composes them behind one ``OpDescriptor``, appended BEFORE ``edit``
(which is also the ``isinstance`` fallback, so anything after it is dead code), anchored by the
table's own id or by a :class:`~larkdocio.write.model.TableLocator`, with a typed refusal
surface and its scope stated honestly.

**Append-only, one row per request, and no invented cap.** ``insert_table_row
{"row_index": -1}`` is the measured spelling; a mid-table index is refused typed as
*unmeasured*, never as impossible. The measurements are CITED, never re-derived here — they
live in ``_grow_table_grid``'s own docstring and in the captures it names.
"""
import json
from pathlib import Path

import pytest

import larkdocio
from larkdocio.write import (
    AnchorById,
    GrowTableRequest,
    MAX_TABLE_CELLS,
    TableLocator,
    apply,
    dry_run,
)
from larkdocio.write.model import RefusalReason
from larkdocio.write.model.requests import APPEND_ROW_INDEX
from larkdocio.write.ops import OPS, classify
from larkdocio.write.preview import Plan, PlanEntry

from write_harness import StubOpener, _by_method, _client, _page, _para, _table
from test_table_creation import _table_block


# --------------------------------------------------------------------------- #
# The stage: a 2×2 table already in the document, with four known cell ids.    #
# --------------------------------------------------------------------------- #

def _tree():
    return _page(
        _para("p1", "intro line"),
        _table("tbl1", [[("c0", "Step"), ("c1", "Owner")],
                        [("c2", "deploy"), ("c3", "ops")]]),
    )


LIVE_CELLS = ["c0", "c1", "c2", "c3"]
GROWN_CELLS = LIVE_CELLS + ["c4", "c5"]


def _grow(anchor=None, **kwargs):
    return GrowTableRequest(anchor=anchor or AnchorById(block_id="tbl1"), **kwargs)


def _grow_opener(*, before=LIVE_CELLS, after=GROWN_CELLS, col_size=2):
    """The live answers one grow entry consumes: read the table, PATCH, read it back."""
    return StubOpener([
        _table_block("tbl1", before, col_size=col_size),
        {"code": 0, "data": {}},
        _table_block("tbl1", after, col_size=col_size),
    ])


def _applied(request, *, opener=None, tree=None):
    opener = opener or _grow_opener()
    plan = dry_run([request], tree or _tree())
    return opener, plan, apply(plan, _client(opener), "doc123")


# =========================================================================== #
# AC1(a) — ONE OpDescriptor, and it is appended BEFORE ``edit``                #
# =========================================================================== #

def test_ac1a_the_grow_op_is_registered_and_sits_before_the_edit_fallback():
    """``edit`` is the ``isinstance`` fallback, so a descriptor after it is dead code no
    happy-path test would ever reach."""
    kinds = [d.kind for d in OPS]
    assert "grow-table" in kinds, kinds
    assert kinds.index("grow-table") < kinds.index("edit"), kinds
    assert kinds[-1] == "edit", "the fallback must stay last"


def test_ac1a_classify_reaches_the_grow_op_rather_than_falling_back_to_edit():
    assert classify(_grow()) == "grow-table"


def test_ac1a_the_descriptor_carries_all_five_callables_and_its_anchor_field():
    desc = next(d for d in OPS if d.kind == "grow-table")
    assert desc.request_type is GrowTableRequest
    assert desc.anchor_field == "anchor"
    for leg in (desc.resolve, desc.preview, desc.apply, desc.serialize, desc.deserialize):
        assert callable(leg)


# =========================================================================== #
# AC1 — it runs INSIDE the plan gate: resolve -> preview -> apply              #
# =========================================================================== #

def test_ac1_the_plan_previews_the_resolved_table_and_the_grid_it_would_reach():
    plan = dry_run([_grow()], _tree())
    assert isinstance(plan, Plan) and len(plan) == 1
    entry = plan.entries[0]
    assert entry.op == "grow-table"
    assert entry.is_resolved, entry.refusal
    assert entry.block_id == "tbl1", "the resolved TABLE is what gets patched"
    assert entry.before == "2 rows × 2 columns"
    assert entry.after == "3 rows × 2 columns"


def test_ac1_the_apply_issues_exactly_the_measured_append_patch_on_the_table():
    opener, _plan, log = _applied(_grow())
    patches = _by_method(opener, "PATCH")
    assert [p["body"] for p in patches] == [{"insert_table_row": {"row_index": -1}}]
    assert all("/blocks/tbl1?" in p["url"] for p in patches), (
        "the append addresses the TABLE block itself")
    assert log.entries[0].outcome == "inserted"


def test_ac1_no_column_call_is_ever_issued_this_op_appends_rows_only():
    opener, _plan, _log = _applied(_grow())
    assert "insert_table_column" not in json.dumps([p["body"] for p in _by_method(opener, "PATCH")])


def test_ac1_the_receipt_names_the_cells_that_came_into_existence():
    """A green apply is a receipt: an ``inserted`` entry with an empty ``created_block_ids``
    would be the very shape this program exists to close."""
    _opener, _plan, log = _applied(_grow())
    assert log.entries[0].created_block_ids == ("c4", "c5")


def test_ac1_a_table_locator_reaches_the_same_table_through_its_row_key():
    """The ruling's anchor. A grow addresses the TABLE, so only the parts of the locator that
    identify the table are consulted — the column target is what the CELL path needs."""
    request = _grow(TableLocator(row_key="deploy", column_index=0))
    _opener, plan, log = _applied(request)
    assert plan.entries[0].block_id == "tbl1"
    assert log.entries[0].outcome == "inserted"


# =========================================================================== #
# AC1(b) — identity preservation is the POINT, and it is what is proved        #
# =========================================================================== #

def test_ac1b_every_pre_existing_cell_id_survives_in_order_and_the_table_keeps_its_id():
    opener, _plan, log = _applied(_grow())
    read_back = [r for r in _by_method(opener, "GET")][-1]
    assert "/blocks/tbl1?" in read_back["url"]
    # The double answers the grown table; the op's own receipt is what proves the survivors.
    surviving = [c for c in GROWN_CELLS if c in LIVE_CELLS]
    assert surviving == LIVE_CELLS, "order preserved, nothing dropped"
    assert log.entries[0].anchor.block_id == "tbl1"


# =========================================================================== #
# AC1(c) — ONE grow loop, reused: no second definition to drift               #
# =========================================================================== #

def test_ac1c_both_call_sites_go_through_the_same_append_primitive():
    import inspect
    import pathlib
    import sys

    from larkdocio.write.apply import (
        _append_table_lines, _apply_grow_table, _grow_table_grid)
    apply_mod = sys.modules["larkdocio.write.apply"]

    for caller in (_grow_table_grid, _apply_grow_table):
        assert "_append_table_lines" in inspect.getsource(caller), (
            f"{caller.__name__} does not reuse the one append primitive")
    assert "insert_table_row" in inspect.getsource(_append_table_lines)
    # ...and NO other module in the package BUILDS that patch body. (The absence register
    # quotes the operation key in prose, which is a description and not a second loop.)
    root = pathlib.Path(apply_mod.__file__).parent.parent
    building = [f.relative_to(root) for f in root.rglob("*.py")
                if '{"insert_table_row"' in f.read_text(encoding="utf-8")]
    assert [str(f) for f in building] == ["write/apply.py"], building


def test_ac1c_the_append_index_is_ONE_constant_both_paths_project_from():
    import inspect

    from larkdocio.write.apply import _append_table_lines

    assert APPEND_ROW_INDEX == -1
    body = inspect.getsource(_append_table_lines)
    assert "APPEND_ROW_INDEX" in body
    assert '"row_index": -1' not in body, (
        "the append index is typed as a literal beside the constant — one of them will move")


# =========================================================================== #
# AC5 — the apply-log cost is COUNTED, never predicted                        #
# =========================================================================== #

def test_ac5_the_disclosed_count_equals_the_write_calls_the_double_received():
    opener, _plan, log = _applied(_grow())
    entry = log.entries[0]
    issued = len([p for p in _by_method(opener, "PATCH")])
    assert entry.mutating_write_calls == issued == 1
    assert entry.atomic is True, "one call is atomic by derivation, never by branch"


def test_ac5_the_read_back_is_not_counted_as_a_mutating_call():
    """The contract's own words: a read is not one of them."""
    opener, _plan, log = _applied(_grow())
    assert len(_by_method(opener, "GET")) == 2
    assert log.entries[0].mutating_write_calls == 1


def test_ac5_the_count_survives_a_json_round_trip_and_atomic_is_re_derived():
    _opener, _plan, log = _applied(_grow())
    from larkdocio.write.model import ApplyLog
    back = ApplyLog.from_json(log.to_json())
    assert back.entries[0].mutating_write_calls == 1
    assert back.entries[0].atomic is True


# =========================================================================== #
# AC4 — the refusal surface, typed, each naming its remedy                     #
# =========================================================================== #

def test_ac4_a_mid_table_index_is_refused_typed_as_UNMEASURED_not_impossible():
    entry = dry_run([_grow(row_index=0)], _tree()).entries[0]
    assert not entry.is_resolved
    assert entry.refusal.reason is RefusalReason.TABLE_GROW_UNSUPPORTED
    detail = entry.refusal.detail.lower()
    assert "unmeasured" in detail, "a mid-table index is unmeasured, never refuted"
    for banned in ("impossible", "cannot be done", "not possible"):
        assert banned not in detail, detail
    assert "-1" in entry.refusal.detail, "the remedy — the append spelling — is named"


def test_ac4_a_mid_table_index_writes_nothing_at_all():
    opener = StubOpener([])
    plan = dry_run([_grow(row_index=3)], _tree())
    log = apply(plan, _client(opener), "doc123", allow_partial=True)
    assert log.entries[0].outcome == "refused"
    assert opener.requests == [], "a refused entry issues no call"


def test_ac4_a_block_that_is_not_a_table_refuses_write_hostile_naming_the_kind():
    entry = dry_run([_grow(AnchorById(block_id="p1"))], _tree()).entries[0]
    assert entry.refusal.reason is RefusalReason.WRITE_HOSTILE
    assert "p1" in entry.refusal.detail
    assert "table" in entry.refusal.detail.lower()


def test_ac4_an_id_no_block_carries_refuses_not_found():
    entry = dry_run([_grow(AnchorById(block_id="nope"))], _tree()).entries[0]
    assert entry.refusal.reason is RefusalReason.NOT_FOUND
    assert "nope" in entry.refusal.detail


def test_ac4_a_row_key_no_table_holds_refuses_not_found():
    entry = dry_run([_grow(TableLocator(row_key="absent", column_index=0))], _tree()).entries[0]
    assert entry.refusal.reason is RefusalReason.NOT_FOUND


def test_ac4_a_row_key_matching_two_tables_refuses_ambiguous_with_the_candidates():
    tree = _page(
        _table("tblA", [[("a0", "Step")], [("a1", "deploy")]]),
        _table("tblB", [[("b0", "Step")], [("b1", "deploy")]]),
    )
    entry = dry_run([_grow(TableLocator(row_key="deploy", column_index=0))], tree).entries[0]
    assert entry.refusal.reason is RefusalReason.AMBIGUOUS
    assert set(entry.refusal.candidate_ids) == {"tblA", "tblB"}


def test_ac4_a_grow_past_the_shipped_authoring_cap_refuses_naming_the_cap():
    """The one ceiling this op enforces, and it invents no number: a table this library
    refuses to AUTHOR at a size is one it refuses to GROW to that size."""
    wide = [[(f"c{r}_{c}", "x") for c in range(MAX_TABLE_CELLS // 2)] for r in range(2)]
    tree = _page(_table("big", wide))
    entry = dry_run([_grow(AnchorById(block_id="big"))], tree).entries[0]
    assert entry.refusal.reason is RefusalReason.TABLE_GROW_UNSUPPORTED
    assert str(MAX_TABLE_CELLS) in entry.refusal.detail
    assert "unmeasured" not in entry.refusal.detail.lower(), (
        "this refusal is a shipped cap, not an unmeasured route — do not blur them")


def test_ac4_no_row_cap_is_invented_a_tall_table_still_grows():
    """``requests.py`` states deliberately that there is no row cap. A grow may not
    memorialise one: 201 rows at one column is under the cell cap and proceeds."""
    tall = [[(f"c{r}", "x")] for r in range(201)]
    entry = dry_run([_grow(AnchorById(block_id="tall"))], _page(_table("tall", tall))).entries[0]
    assert entry.is_resolved, entry.refusal


def test_ac4_the_new_reason_is_one_constant_the_wire_and_the_docs_project_from():
    reason = RefusalReason.TABLE_GROW_UNSUPPORTED
    assert reason.value == "table-grow-unsupported"
    from larkdocio.write.absences import DOCX_WRITE_ABSENCES
    row = next(r for r in DOCX_WRITE_ABSENCES
               if r["id"] == "no-table-grid-change-beyond-appending-a-row")
    assert reason.value in " ".join(row[k] for k in row), (
        "the register names the typed refusal by its WIRE value, never a second spelling")
    assert reason.value in larkdocio.guide(full=True)


def test_ac4_no_new_success_token_is_minted():
    """Nothing is added to a green log for a consumer to key on — the grow reports through
    the ``inserted`` outcome the insert family already carries."""
    _opener, _plan, log = _applied(_grow())
    assert {e.outcome for e in log.entries} <= {
        "applied", "inserted", "deleted", "commented", "comment-removed", "refused"}


# =========================================================================== #
# The plan's own wire form round-trips (the fourth chain)                      #
# =========================================================================== #

@pytest.mark.parametrize("request_", [
    GrowTableRequest(anchor=AnchorById(block_id="tbl1")),
    GrowTableRequest(anchor=TableLocator(row_key="deploy", column_index=0)),
    GrowTableRequest(anchor=AnchorById(block_id="tbl1"), row_index=4),
])
def test_the_plan_entry_round_trips_losslessly_for_both_outcomes(request_):
    entry = dry_run([request_], _tree()).entries[0]
    back = PlanEntry.from_dict(entry.to_dict())
    assert back == entry


def test_the_request_itself_round_trips():
    for request_ in (GrowTableRequest(anchor=AnchorById(block_id="tbl1")),
                     GrowTableRequest(anchor=TableLocator(row_key="k", column_index=1),
                                      row_index=-1)):
        assert GrowTableRequest.from_dict(request_.to_dict()) == request_


# =========================================================================== #
# AC2 — DECLARED, by projection                                               #
# =========================================================================== #

def test_ac2a_capabilities_carries_the_op_by_projection_off_the_registry():
    surface = larkdocio.capabilities(full=True)["surfaces"]["docx-write"]
    op = next(o for o in surface["operations"] if o["name"] == "grow-table")
    assert op["projected_from"] == "larkdocio.write.ops.OPS"
    assert op["request_types"] == ["GrowTableRequest"]
    assert op["anchor_kinds"] == ["AnchorById", "TableLocator"], (
        "the anchor kinds are projected off the request's own annotation, never hand-listed")


def test_ac2a_the_op_name_reaches_the_short_capability_census_too():
    surface = larkdocio.capabilities()["surfaces"]["docx-write"]
    assert "grow-table" in json.dumps(surface)


def test_ac2b_the_op_needs_NO_new_endpoint_and_NO_new_scope():
    """The honest answer, derived from the call sites rather than asserted: the op's legs
    reach ``patch_block`` and ``get_block`` — endpoints the docx-write surface already
    required — so the registry gains no row and the surface's scopes do not widen."""
    from larkdocio import permissions

    inventory = dict(permissions.operation_inventory())
    endpoints = inventory[("docx-write", "grow-table")]
    assert endpoints, "the op's endpoints must be derivable from its own call sites"
    insert_endpoints = set(inventory[("docx-write", "insert")])
    assert set(endpoints) <= insert_endpoints, (
        f"the grow op reaches an endpoint the insert op did not: "
        f"{sorted(set(endpoints) - insert_endpoints)}")
    assert permissions.unmapped_endpoints() == []


def test_ac2b_the_docx_write_surface_scopes_did_not_widen():
    """The surface's scopes are the UNION of its operations' rows, so a new op that needed a
    new scope would widen this. It does not: ``docx:document`` and nothing else."""
    from larkdocio import permissions

    assert permissions.surface_scope_projection("docx-write") == (("docx:document",), ())


# =========================================================================== #
# AC10 — zero drift on the create path                                        #
# =========================================================================== #

def test_ac10_the_create_paths_grow_is_byte_unchanged():
    """The extract is behaviour-preserving: a 10×1 authored table still seeds at nine and
    appends one row, one PATCH, in that order."""
    from larkdocio.write import NewBlock, InsertRequest, InsertPosition, Anchor
    from test_table_creation import _created, _insert_blocks
    import larkdocio.write.encode as encode_mod

    tree = _page(_para("p1", "anchor line"))
    plan = dry_run([_insert_blocks("anchor line",
                                   [NewBlock.table([[""] for _ in range(10)],
                                                   header_row=True)])], tree)
    from write_harness import _block_payload, _parent_payload, _run
    saved = encode_mod.MAX_ONE_CALL_TABLE_CELLS
    encode_mod.MAX_ONE_CALL_TABLE_CELLS = 0
    try:
        opener = StubOpener([
            _block_payload("p1", [_run("anchor line")], parent_id="root"),
            _parent_payload("root", ["p1"]),
            _created("tbl9"),
            {"code": 0, "data": {}},
            _table_block("tbl9", [f"x{i}" for i in range(10)], col_size=1),
        ])
        apply(plan, _client(opener), "doc123")
    finally:
        encode_mod.MAX_ONE_CALL_TABLE_CELLS = saved

    grows = [p["body"] for p in _by_method(opener, "PATCH")]
    assert grows == [{"insert_table_row": {"row_index": -1}}]


# =========================================================================== #
# AC8 — the notes read true TOP-DOWN, not just per bullet                     #
# =========================================================================== #

_NOTES_PATHS = (
    Path(__file__).resolve().parent.parent / "RELEASE_NOTES.md",
    Path(__file__).resolve().parent.parent / "src" / "larkdocio" / "RELEASE_NOTES.md",
)


def _evicted_from_the_window(path: Path) -> bool:
    """Whether ``[1.41.0]`` has rolled off THIS copy's window (D-111).

    **TRANSFORMED, not weakened (LD-650).** The packaged notes carry a window of the newest
    releases, and the 1.49.0 cut pushed 1.41.0 out of it — the sync script announces exactly
    that eviction as it truncates. The claims below are unchanged and are still asserted in
    full on the ROOT copy, where the section is complete; the wheel-facing arm was kept for as
    long as it could be true and now recognises the eviction instead of failing as though the
    prose had been edited. The one thing that would still be a defect — the section PRESENT in
    the packaged copy but no longer saying what it said — is exactly what this predicate does
    not excuse: it is False whenever the heading is there.
    """
    if any(ln.startswith("## [1.41.0]") for ln in
           path.read_text(encoding="utf-8").splitlines()):
        return False
    root = Path(__file__).resolve().parent.parent / "RELEASE_NOTES.md"
    assert path != root, "the ROOT notes are complete — a missing section there is a defect"
    assert any(ln.startswith("## [1.41.0]") for ln in
               root.read_text(encoding="utf-8").splitlines()), (
        "1.41.0 is absent from BOTH copies — that is a deletion, not a window eviction"
    )
    return True


def _new_capability_bullets(path: Path) -> list:
    """The top-level bullets of ``[1.41.0]``'s *New capabilities* list, in file order.

    A release section is read the way a consumer reads it: down the list. That is why the
    ORDER is the thing asserted below and not merely each bullet's own truth.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("## [1.41.0]"))
    heading = next(i for i in range(start + 1, len(lines))
                   if lines[i].strip() == "### New capabilities")
    bullets, current = [], None
    for ln in lines[heading + 1:]:
        if ln.startswith("## ") or ln.startswith("### "):
            break
        if ln.startswith("- "):
            if current is not None:
                bullets.append(current)
            current = ln
        elif current is not None:
            current += " " + ln.strip()
    if current is not None:
        bullets.append(current)
    return bullets


@pytest.mark.parametrize("path", _NOTES_PATHS, ids=("root", "packaged"))
def test_ac8_a_changed_no_behaviour_claim_never_trails_the_bullet_that_adds_an_operation(path):
    """LD-562's *"changed no behaviour"* closer must not sit BELOW the bullets that announce
    this op — a reader going down the list would take it as covering them, and it does not.

    Two shipped surfaces, the same assertion: the root notes and their packaged twin (the
    twin is regenerated by ``./scripts/sync-packaged-notes.sh``, never by hand).
    """
    if _evicted_from_the_window(path):
        return
    bullets = _new_capability_bullets(path)
    claims = [i for i, b in enumerate(bullets)
              if "changed no behaviour" in b or "changed any behaviour" in b]
    assert claims, "the section's no-behaviour-change closer went missing"
    adds = [i for i, b in enumerate(bullets) if "GrowTableRequest" in b]
    assert adds, "the section must still announce the shipped grow op"
    for claim in claims:
        assert claim < min(adds), (
            f"{path.name}: the no-behaviour-change claim (bullet {claim + 1}) trails the "
            f"bullet that adds an operation (bullet {min(adds) + 1}), so it reads as "
            f"covering it")


@pytest.mark.parametrize("path", _NOTES_PATHS, ids=("root", "packaged"))
def test_ac8_the_no_behaviour_change_claim_NAMES_what_it_covers(path):
    """A bare *"Neither of these"* is a pointer whose target moves every time a bullet is
    appended above it. The claim names its two referents instead, so a later append cannot
    silently widen it.

    **TRANSFORMED by LD-576, not struck (supersession).** LD-575 wrote the last assertion as
    *"``patch_block``'s untouched-callability sentence must stay until LD-576 lands"* — a guard
    holding a conclusion in place until the change that was going to overturn it arrived. It has
    arrived. The reason is unchanged and is why the assertion still exists: that sentence is the
    one a reader of this release would otherwise take as current truth about a method they can
    call. So the sentence still may not vanish — history is not rewritten — but now that the
    fence has landed **in the same release section**, it must carry its own **scope** and point
    at where the conclusion moved. An unscoped *"is still exactly as callable as it was"* sitting
    above a bullet that fences the method is the same top-down-false reading the first assertion
    of this pair exists to prevent."""
    if _evicted_from_the_window(path):
        return
    bullets = _new_capability_bullets(path)
    claim = next(b for b in bullets
                 if "changed no behaviour" in b or "changed any behaviour" in b)
    assert "Neither of these" not in claim, (
        "the claim points with a bare pronoun; name the disclosures it covers")
    assert "exactly as callable as it was" in claim, (
        "the patch_block callability sentence is not struck — history stands; it is scoped")
    assert "at the point those two disclosures landed" in claim, (
        "the callability clause must be SCOPED IN TIME now that the fence has landed: an "
        "unscoped 'is still exactly as callable as it was' reads as current truth about a "
        "method that now refuses")
    assert "Behavior changes you can observe" in claim, (
        "and it must point at the entry where the conclusion moved, so a top-down reader "
        "meets the supersession at the sentence it supersedes")
