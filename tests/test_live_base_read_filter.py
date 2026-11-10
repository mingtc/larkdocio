"""LD-314 — THE DIFFERENTIAL LIVE ARM for the read filter and the sort (AC2, AC4).

``@pytest.mark.live``, deselected by default. Run it with::

    pytest -m live

**Read-only, against the configured Scratch Base.** This arm makes ``records/search`` calls and
nothing else — no write client is imported, no field is created, no record is touched. That is
what makes the Scratch Base a legitimate target here: it is a READ fixture
(``base_write_harness`` refuses it as a write target by allow-list), and this arm only reads.

**Why every assertion is a COMPARISON of two reads.** ``records/search`` silently ignores every
body key it does not recognise (R12), so ``code:0`` is not evidence that a filter was honoured —
an ignored filter returns ``code:0`` and the whole table. Nothing here reads a code. Each claim
is made by comparing a narrowed read against an unnarrowed read of the **same table in the same
run**:

* **the subset test** — every id a filtered read returned is in the unfiltered set, and the
  filter's own predicate holds for every row that came back;
* **the match-nothing test** — the sharpest R12 tell there is. Under R12 an ignored filter
  returns *everything*; a filter that cannot match returns ``n=0``, which an ignored filter
  cannot produce on a non-empty table;
* **the R12 control** — the same table read with a filter this library cannot express is not
  available (the client refuses unknown keys locally, by construction), so the control here is
  the **unfiltered read itself**, taken in the same run: it is what "the whole table" looks
  like, and it is the number every ignored parameter would have returned.

**Sort is proven by ORDER, and collation is not assumed.** ``desc`` is asserted to be the exact
reverse of ``asc`` over the same ids — a statement that holds under *any* collation, unlike
comparing Lark's ordering to Python's. The two captured refusals (``1254016`` for an unknown
field name and for a ``fld…`` id where a name belongs) are re-run too; the id one is refused
locally by this library, so the arm asserts the local refusal and cites the capture for the
server's.

**Gentle.** Around a dozen ``records/search`` calls, all through the client's own limiter at
1.2 s spacing. Rate limits are not probed.

**Skips loudly, never silently.**
"""
import canary_support
import pytest

from larkdocio.base.client import BaseReadClient
from larkdocio.base.view_filters import (
    BaseFilterRefusal,
    Condition,
    FieldId,
    FieldName,
    FilterSpec,
    SortKey,
    search_filter,
)

pytestmark = pytest.mark.live
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

canary_support.load_env()

#: A value no cell in a Base can hold, so a filter for it can only ever return nothing. Long,
#: unlikely, and deliberately not a value the fixture might grow.
IMPOSSIBLE_VALUE = "ld314-no-cell-anywhere-holds-this-value-0f3a"


@pytest.fixture(scope="module")
def scratch():
    reason = canary_support.base_missing_reason()
    if reason:
        pytest.skip(reason)
    return canary_support.parse_base_url(canary_support.scratch_base_url())


#: Filled by the ``table`` fixture: the app + table revisions BEFORE the arm ran, so the
#: read-only claim is a comparison rather than an assertion of the obvious.
BASELINE = {}


@pytest.fixture(scope="module")
def table(scratch):
    """The first table that has both rows and a text column to filter on."""
    domain, app_token = scratch
    read = BaseReadClient.from_read_credentials(domain)
    BASELINE["app_revision"] = read.get_app(app_token).revision
    BASELINE["tables"] = {t.table_id: t.revision for t in read.list_tables(app_token)}
    for candidate in read.list_tables(app_token):
        records = read.search_records(app_token, candidate.table_id)
        if not records:
            continue
        fields = read.list_fields(app_token, candidate.table_id)
        text = next((f.field_name for f in fields if f.type == 1), None)
        if text:
            return read, app_token, candidate.table_id, text, records
    pytest.skip("the Scratch Base has no populated table with a text column to filter on")


def _cell_text(record, column):
    """The plain text of ``column`` in ``record``, from the ``search`` encoding."""
    value = (record.fields or {}).get(column)
    if isinstance(value, list):
        return "".join(part.get("text", "") for part in value if isinstance(part, dict))
    return "" if value is None else str(value)


def test_THE_FILTER_IS_HONOURED_a_strict_correct_subset_and_a_MATCH_NOTHING_zero(table):
    """AC2, all three legs in one arm so the comparison is against one run's own control."""
    read, app_token, table_id, column, _ = table

    unfiltered = read.search_records(app_token, table_id)
    all_ids = [r.record_id for r in unfiltered]
    assert len(all_ids) >= 2, (
        "a one-row table cannot show a strict subset; this arm needs a populated fixture")
    wanted = _cell_text(unfiltered[0], column)
    assert wanted, "the chosen text column's first cell is empty — pick a populated fixture"

    # ---- (a) a strict, correct subset -------------------------------------- #
    filtered = read.search_records(app_token, table_id, filter=search_filter(
        FilterSpec(conditions=(Condition(FieldName(column), "is", (wanted,)),))))
    filtered_ids = [r.record_id for r in filtered]
    print(f"\nAC2 subset :: unfiltered n={len(all_ids)} filtered n={len(filtered_ids)} "
          f"column={column!r} value={wanted!r}")
    print(f"AC2 subset :: unfiltered ids={all_ids}")
    print(f"AC2 subset :: filtered   ids={filtered_ids}")
    assert filtered_ids, "the filter matched a value taken from the table's own first row"
    assert set(filtered_ids) < set(all_ids), (
        "a filtered read must return a STRICT subset of the unfiltered read; it returned "
        f"{len(filtered_ids)} of {len(all_ids)}, which is what an IGNORED filter returns")
    for record in filtered:
        assert _cell_text(record, column) == wanted, (
            f"row {record.record_id} came back under `is {wanted!r}` with "
            f"{_cell_text(record, column)!r} — the predicate does not hold")

    # ---- (b) the match-nothing filter: the sharpest R12 tell ---------------- #
    nothing = read.search_records(app_token, table_id, filter=search_filter(
        FilterSpec(conditions=(Condition(FieldName(column), "is", (IMPOSSIBLE_VALUE,)),))))
    print(f"AC2 match-nothing :: n={len(nothing)} (an IGNORED filter would return "
          f"{len(all_ids)})")
    assert nothing == [], (
        f"a filter that can match nothing returned {len(nothing)} rows. Under R12 an ignored "
        f"filter returns the whole table ({len(all_ids)}), which is exactly this result's shape")

    # ---- (c) the control, taken last, in the same run ----------------------- #
    control = read.search_records(app_token, table_id)
    print(f"AC2 control :: unfiltered again n={len(control)}")
    assert [r.record_id for r in control] == all_ids, (
        "the unfiltered control moved during the run; the differential is not sound")


def test_THE_CONJUNCTION_travels_too_or_returns_MORE_than_and(table):
    """A second, independent differential: the same two conditions under ``and`` and under
    ``or`` cannot both be ignored and still differ."""
    read, app_token, table_id, column, records = table
    first = _cell_text(records[0], column)
    second = next((_cell_text(r, column) for r in records[1:]
                   if _cell_text(r, column) and _cell_text(r, column) != first), None)
    if not second:
        pytest.skip("the fixture has no second distinct value in its text column")
    conditions = (Condition(FieldName(column), "is", (first,)),
                  Condition(FieldName(column), "is", (second,)))
    both_and = read.search_records(app_token, table_id, filter=search_filter(
        FilterSpec(conditions=conditions, conjunction="and")))
    both_or = read.search_records(app_token, table_id, filter=search_filter(
        FilterSpec(conditions=conditions, conjunction="or")))
    print(f"\nAC2 conjunction :: and n={len(both_and)} or n={len(both_or)} "
          f"values=({first!r}, {second!r})")
    assert len(both_and) == 0, "one cell cannot be two different values at once"
    assert len(both_or) == 2, "`or` over two distinct row values must return both rows"


def test_THE_SORT_IS_OBSERVED_desc_is_exactly_the_reverse_of_asc(table):
    """AC4's order assertion, made collation-free: ``desc`` reverses ``asc`` under any ordering
    the server uses, and neither may drop or add a row."""
    read, app_token, table_id, column, records = table
    values = [_cell_text(r, column) for r in records]
    if len(set(values)) < 2:
        pytest.skip("a column with one distinct value cannot show an order change")

    asc = read.search_records(app_token, table_id, sort=(SortKey(FieldName(column)),))
    desc = read.search_records(app_token, table_id,
                               sort=(SortKey(FieldName(column), desc=True),))
    asc_ids = [r.record_id for r in asc]
    desc_ids = [r.record_id for r in desc]
    print(f"\nAC4 sort :: asc  values={[_cell_text(r, column) for r in asc]}")
    print(f"AC4 sort :: desc values={[_cell_text(r, column) for r in desc]}")
    assert set(asc_ids) == set(r.record_id for r in records), (
        "a sort must reorder the answer, never change which rows are in it")
    assert desc_ids == list(reversed(asc_ids)), (
        "desc is not the reverse of asc — either the sort was ignored (R12) or it is not an "
        "order at all")
    assert desc_ids != asc_ids, (
        "asc and desc returned the same order, which is what an IGNORED sort looks like")


def test_A_SORT_BY_A_NONEXISTENT_FIELD_IS_REFUSED_BY_LARK_not_silently_ignored(table):
    """AC4's refusal half, live. This is the second reason to believe ``sort`` is read at all:
    a key the server ignores cannot also refuse a bad value in it."""
    from larkdocio.errors import LarkAPIError

    read, app_token, table_id, _column, _ = table
    with pytest.raises(LarkAPIError) as excinfo:
        read.search_records(app_token, table_id,
                            sort=(SortKey(FieldName("ld314-no-such-column")),))
    code = getattr(excinfo.value, "code", None)
    print(f"\nAC4 refusal :: sort on a nonexistent field -> code={code}")
    assert code == 1254016, (
        f"expected the captured `1254016 InvalidSort`; got {code}. A sort key the server "
        "*validates* is a sort key the server *reads*")


def test_A_SORT_BY_FIELD_ID_IS_REFUSED_LOCALLY_before_any_call(table):
    """The other captured refusal (``p1-q3-01`` step 7) is answered by this library instead of
    by Lark — so the arm asserts the local refusal and spends no call on it."""
    with pytest.raises(BaseFilterRefusal) as excinfo:
        SortKey(FieldId("fldbbSDMOY"))
    assert "1254016" in str(excinfo.value)


def test_THE_ARM_MOVED_NOTHING_in_the_scratch_base(table):
    """The read-only fence, asserted on the fixture's own revision rather than assumed."""
    read, app_token, table_id, _column, _ = table
    after_tables = {t.table_id: t.revision for t in read.list_tables(app_token)}
    after_app = read.get_app(app_token).revision
    print(f"\nAC10 :: app.revision {BASELINE['app_revision']} -> {after_app}")
    print(f"AC10 :: table revisions {BASELINE['tables']} -> {after_tables}")
    assert after_app == BASELINE["app_revision"], (
        "the Scratch Base's app revision moved across a READ-ONLY arm")
    assert after_tables == BASELINE["tables"], (
        "a table revision moved across a READ-ONLY arm — the one reliable write detector")
